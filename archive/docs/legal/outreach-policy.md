# Outreach policy — T-0.6

Fill the brackets. This is not a legal opinion; it is the operating rule the software will enforce. If a field below has no answer, the corresponding column in `contacts` stays empty and no send is permitted.

## 1. Jurisdictions we contact

| Jurisdiction | Lawful basis for B2B email | What must be recorded |
|---|---|---|
| [country/state] | [consent \| legitimate interest \| contract \| not required] | [evidence: source, date, page] |
| | | |

## 2. Rules the system enforces

**Lawful basis.** Every contact used for outreach carries `lawful_basis` and `basis_evidence` (source, date, jurisdiction). No basis recorded → the send tool refuses, regardless of approval.

**Opt-in jurisdictions.** [List any jurisdiction where prior consent is required.] A campaign whose segment contains contacts without consent in those jurisdictions must be blocked at creation, not at send.

**Suppression.** Organisation-wide, channel-specific, permanent. Written by: explicit opt-out, spam complaint, hard bounce, manual entry, legal request. Checked inside the send tool before every message.

**Unsubscribe.** One-click in bulk mail plus a monitored reply path. Honoured immediately at the tool level and within 24 hours operationally. An opt-out is never re-confirmed.

**Identification.** Every commercial message carries sender name, a working reply path, and a physical address: `[address]`. Domain verified before the sending account can be enabled.

**Data minimisation.** We store: name, business email, title, company, domain, source, lawful basis. We do not store: personal social profiles, home addresses, inferred personal data.

**Retention.** Contact records: active + 24 months. Message bodies: 24 months, redacted at 12. Suppressions: indefinite, including after a deletion request.

**Data subject requests.** Export and delete within [30] days. Deletion removes messages, enrichment and the contact record; the suppression entry survives.

**AI disclosure.** Automated replies disclose automation: [always / on request / for regulated segments only].

## 3. Volume limits

| Limit | Value | Why |
|---|---|---|
| Per mailbox per day | [40] | Provider quota and reputation |
| Per domain per day | [200] | Reputation isolation |
| Per campaign per day | [100] | Blast radius of a mistake |
| New domain warm-up | [weeks to reach full volume] | Deliverability is earned, not configured |

## 4. What we will not do

- Contact addresses from any source that prohibits it, or that required bypassing an access control.
- Email after an opt-out, on any channel, for any campaign.
- Claim a relationship, a referral or prior contact that did not happen.
- State a price, discount or contractual term that is not in `seed/brand.json`.

## 5. Owner

Policy owner: [name]. Reviewed at each phase exit, and whenever a jurisdiction is added.
