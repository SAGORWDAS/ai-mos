import hashlib
import re

from fastapi import HTTPException
from sqlalchemy import select

from app.growth.models import BrandChunk, BrandDocument


def digest(value):
    return hashlib.sha256(value.encode()).hexdigest()


async def index_document(session, org_id, brand_id, title, content, source="human-entry"):
    checksum = digest(content)
    existing = await session.scalar(
        select(BrandDocument).where(
            BrandDocument.organization_id == org_id,
            BrandDocument.brand_id == brand_id,
            BrandDocument.checksum == checksum,
        )
    )
    if existing:
        return existing
    document = BrandDocument(
        organization_id=org_id, brand_id=brand_id, title=title, checksum=checksum, source_uri=source
    )
    session.add(document)
    await session.flush()
    paragraphs = [content[i : i + 1000] for i in range(0, len(content), 1000)]
    for i, paragraph in enumerate(paragraphs):
        session.add(
            BrandChunk(
                organization_id=org_id,
                document_id=document.id,
                brand_id=brand_id,
                ordinal=i,
                content=paragraph,
            )
        )
    await session.flush()
    return document


async def claim_sources(session, brand):
    citations = []
    for claim in brand.approved_claims:
        document = await index_document(
            session, brand.organization_id, brand.id, "Approved claim", claim, "brand-profile"
        )
        chunk = await session.scalar(
            select(BrandChunk)
            .where(
                BrandChunk.organization_id == brand.organization_id,
                BrandChunk.document_id == document.id,
            )
            .order_by(BrandChunk.ordinal)
        )
        citations.append({"text": claim, "brand_chunk_id": chunk.id})
    return citations


async def retrieve(session, org_id, brand_id, query, limit=5):
    rows = (
        await session.scalars(
            select(BrandChunk).where(
                BrandChunk.organization_id == org_id, BrandChunk.brand_id == brand_id
            )
        )
    ).all()
    terms = set(re.findall(r"\w+", query.lower()))
    ranked = []
    for chunk in rows:
        overlap = terms & set(re.findall(r"\w+", chunk.content.lower()))
        if overlap:
            ranked.append(
                {
                    "chunk_id": chunk.id,
                    "document_id": chunk.document_id,
                    "content": chunk.content,
                    "score": len(overlap) / max(len(terms), 1),
                }
            )
    return sorted(ranked, key=lambda row: row["score"], reverse=True)[:limit]


async def guard(session, brand, body, claims, *, chunks=None):
    banned = brand.prohibited_claims + brand.voice.get("banned_phrases", [])
    if any(phrase.strip() and phrase.lower() in body.lower() for phrase in banned):
        raise HTTPException(422, "prohibited_claim_or_phrase")
    if chunks is None:
        identifiers = list({claim.get("brand_chunk_id") for claim in claims})
        chunks = {}
        for offset in range(0, len(identifiers), 500):
            rows = (
                await session.scalars(
                    select(BrandChunk).where(
                        BrandChunk.id.in_(identifiers[offset : offset + 500]),
                        BrandChunk.organization_id == brand.organization_id,
                        BrandChunk.brand_id == brand.id,
                    )
                )
            ).all()
            chunks.update({chunk.id: chunk for chunk in rows})
    for claim in claims:
        chunk = chunks.get(claim.get("brand_chunk_id"))
        if (
            not chunk
            or chunk.organization_id != brand.organization_id
            or chunk.brand_id != brand.id
            or claim.get("text") not in brand.approved_claims
            or claim.get("text") not in chunk.content
            or claim.get("text") not in body
        ):
            raise HTTPException(422, "ungrounded_claim")
    # Drafts must retain every current approved assertion they cite.
    if not claims:
        raise HTTPException(422, "grounding_required")


def safe_subjects(brand):
    return [
        f"A question from {brand.name}"[:90],
        f"Following up from {brand.name}"[:90],
        f"A question about {brand.name}"[:90],
    ]


def draft_text(brand, lead, claims):
    personalisation = (
        (lead.personalisation + "\n\n")
        if lead.personalisation and lead.personalisation_evidence
        else ""
    )
    return (
        f"Hello {lead.name},\n\n{personalisation}{brand.name}: {claims[0]['text']}\n\n"
        "Would it be useful to discuss whether this fits your needs? "
        "You are welcome to say no. Reply unsubscribe if you would prefer "
        "not to hear from us again."
    )


async def guard_draft(session, brand, lead, subject, body, claims):
    await guard(session, brand, body, claims)
    if not 30 <= len(body.split()) <= 140:
        raise HTTPException(422, "outreach_word_limit")
    if subject not in safe_subjects(brand):
        raise HTTPException(422, "use_a_grounded_subject_template")
    # Uncited assertions cannot hide outside a model's self-reported claims array.
    remaining = body
    allowed = [
        "Thanks for your reply.",
        f"Hello {lead.name},",
        f"{brand.name}:",
        "Would it be useful to discuss whether this fits your needs?",
        "You are welcome to say no.",
        "Reply unsubscribe if you would prefer not to hear from us again.",
    ]
    if lead.personalisation and lead.personalisation_evidence:
        allowed.append(lead.personalisation)
    for phrase in sorted([entry["text"] for entry in claims] + allowed, key=len, reverse=True):
        remaining = remaining.replace(phrase, "")
    if remaining.strip():
        raise HTTPException(422, "uncited_outreach_text_add_facts_to_brand_first")


async def guard_content(session, brand, title, expected_title, body, claims, *, chunks=None):
    await guard(session, brand, title + "\n" + body, claims, chunks=chunks)
    if title != expected_title:
        raise HTTPException(422, "content_title_must_match_approved_topic")
    remaining = body
    for source in sorted(
        [brand.positioning, brand.name] + [item["text"] for item in claims], key=len, reverse=True
    ):
        if source:
            remaining = remaining.replace(source, "")
    if remaining.strip():
        raise HTTPException(422, "uncited_content_text")


def classify(body):
    lower = body.lower()
    if re.search(
        r"\b(unsubscribe|remove me|take me off|leave me alone|"
        r"stop(?: emailing| contacting| messaging)?|opt[ -]?out|"
        r"do not (?:contact|email|message)|don't (?:contact|email|message)|"
        r"no more (?:emails|messages))\b",
        lower,
    ):
        return {"label": "unsubscribe", "confidence": 1.0, "escalate": False}
    if re.search(r"\b(spam|legal action|report you|complaint)\b", lower):
        return {"label": "complaint", "confidence": 1.0, "escalate": True}
    rules = [
        ("auto_reply", r"out of (the )?office|automatic reply|on vacation", False),
        ("bounce_notice", r"delivery failed|undeliverable|mailbox not found", False),
        ("pricing_question", r"\b(price|pricing|cost|discount|refund)\b", True),
        ("meeting_request", r"\b(meeting|call|schedule|book a demo)\b", False),
        ("not_interested", r"not interested|no thanks", False),
        ("not_now", r"not now|next (month|quarter)|later this", False),
        ("referral", r"speak (to|with)|contact my colleague", True),
        ("wrong_person", r"wrong person|not my (role|department)", True),
        ("interested", r"\b(interested|tell me more|more details|can you tell me how)\b", False),
    ]
    found = [(label, escalate) for label, pattern, escalate in rules if re.search(pattern, lower)]
    if len(found) == 1:
        label, escalate = found[0]
        return {"label": label, "confidence": 0.85, "escalate": escalate}
    return {"label": "needs_human", "confidence": 0.0, "escalate": True}
