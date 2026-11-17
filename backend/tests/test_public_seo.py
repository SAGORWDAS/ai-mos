from html.parser import HTMLParser
from types import SimpleNamespace
from xml.etree import ElementTree

import pytest
from pydantic import ValidationError
from test_foundation import signup
from test_growth import approve, brand_and_lead, make_draft, rows
from test_knowledge_publication import publish

from app.config import Settings
from app.growth.publication import public_base


class Head(HTMLParser):
    def __init__(self, content):
        super().__init__()
        self.metadata, self.links = {}, {}
        self.feed(content)

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == "meta":
            self.metadata[attrs.get("name", attrs.get("property", ""))] = attrs.get("content", "")
        if tag == "link":
            self.links[attrs.get("rel")] = attrs.get("href")


def test_private_routes_and_local_publication_are_not_indexed(clients):
    a, b = clients
    owner = signup(a)
    brand, _ = brand_and_lead(a)
    item = publish(a, brand)
    path = f"/v1/public/{owner['organization']['id']}/{item['id']}"
    response = b.get(path)
    assert response.headers["x-robots-tag"] == "noindex, nofollow"
    assert Head(response.text).metadata["robots"] == "noindex, nofollow"
    assert "canonical" not in Head(response.text).links
    assert b.get(f"/v1/public/{owner['organization']['id']}/sitemap.xml").status_code == 404
    assert a.get("/v1/data/leads").headers["x-robots-tag"] == "noindex, nofollow"


def test_public_seo_is_scoped_escaped_and_uses_trusted_canonical(clients):
    a, b = clients
    owner = signup(a)
    other = signup(b, "other@example.test")
    settings = a.app.state.runtime.settings
    settings.public_api_url = "https://marketing.example.com/api"
    settings.public_indexing_enabled = True
    brand, _ = brand_and_lead(a)
    item = publish(a, brand)
    other_brand, _ = brand_and_lead(b)
    other_item = publish(b, other_brand)
    path = f"/v1/public/{owner['organization']['id']}/{item['id']}"
    response = b.get(path, headers={"host": "untrusted.example"})
    head = Head(response.text)
    expected = settings.public_api_url + path
    assert head.links["canonical"] == expected
    assert head.metadata["og:url"] == expected
    assert 1 <= len(head.metadata["description"]) <= 160
    assert head.metadata["og:description"] == head.metadata["description"]
    assert response.headers["x-robots-tag"] == "index, follow"
    sitemap = b.get(f"/v1/public/{owner['organization']['id']}/sitemap.xml")
    root = ElementTree.fromstring(sitemap.content)
    locations = [node.text for node in root.iter() if node.tag.endswith("}loc")]
    assert locations == [expected]
    assert other_item["id"] not in sitemap.text
    assert other["organization"]["id"] not in sitemap.text
    assert a.post(f"/v1/content/{item['id']}/unpublish").status_code == 200
    assert item["id"] not in b.get(f"/v1/public/{owner['organization']['id']}/sitemap.xml").text


def test_brand_edit_withdraws_publication_and_invalidates_related_approvals(clients):
    a, b = clients
    owner = signup(a)
    brand, lead = brand_and_lead(a)
    item = publish(a, brand)
    draft = make_draft(a, lead)
    approval = approve(a, draft)
    path = f"/v1/public/{owner['organization']['id']}/{item['id']}"
    fields = {
        name: value
        for name, value in brand.items()
        if name not in {"id", "created_at", "organization_id"}
    }
    assert a.put(f"/v1/brands/{brand['id']}", json=fields).status_code == 200
    assert b.get(path).status_code == 200  # An unchanged save does not withdraw a page.
    fields["approved_claims"] = []
    assert a.put(f"/v1/brands/{brand['id']}", json=fields).status_code == 200
    assert b.get(path).status_code == 404
    assert (
        next(x for x in rows(a, "approvals") if x["id"] == approval["id"])["status"]
        == "invalidated"
    )
    assert next(x for x in rows(a, "content_items") if x["id"] == item["id"])["status"] == "draft"


@pytest.mark.parametrize(
    "url",
    [
        "https://[bad",
        "https://user:secret@example.com",
        "https://example.com/?token=private",
        "javascript:alert(1)",
    ],
)
def test_invalid_public_base_fails_closed(url):
    assert public_base(SimpleNamespace(public_api_url=url)) == ""
    with pytest.raises(ValidationError) as error:
        Settings(public_api_url=url)
    assert url not in str(error.value)


def test_public_metadata_escapes_stored_text():
    from app.growth.publication import page

    attack = '"><script>alert(1)</script>'
    result = page(
        SimpleNamespace(name=attack),
        SimpleNamespace(id="content", organization_id="org", title=attack, body=attack),
        Settings(),
    )
    assert "<script>" not in result
    assert Head(result).metadata["description"] == attack


def test_sitemap_paginates_without_exposing_drafts(clients):
    from app.growth.models import Content
    from app.tenancy import tenant_scope

    a, b = clients
    owner = signup(a)
    brand, _ = brand_and_lead(a)
    published = publish(a, brand)
    settings = a.app.state.runtime.settings
    settings.public_api_url = "https://marketing.example.com/api"
    settings.public_indexing_enabled = True

    async def seed():
        async with a.app.state.factory() as session:
            await tenant_scope(session, organization_id=owner["organization"]["id"])
            session.add_all(
                [
                    Content(
                        organization_id=owner["organization"]["id"],
                        brand_id=brand["id"],
                        type="landing_page",
                        title=published["title"],
                        body=published["body"],
                        citations=published["citations"],
                        status="published_local",
                    )
                    for _ in range(1000)
                ]
            )
            await session.commit()

    a.portal.call(seed)
    path = f"/v1/public/{owner['organization']['id']}/sitemap.xml"
    index = ElementTree.fromstring(b.get(path).content)
    assert index.tag.endswith("}sitemapindex")
    assert len(list(index)) == 2
    last = ElementTree.fromstring(b.get(path + "?page=1").content)
    assert last.tag.endswith("}urlset")
    assert len(list(last)) == 1
    assert b.get(path + "?page=-2").status_code == 422
