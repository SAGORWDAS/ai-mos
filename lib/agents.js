// The "team": each role is a short prompt over a compact brand brief (keeps tokens low).
const { ask } = require('./ai');
const { getJSON } = require('./db');

const RULES = 'Never invent facts, prices, stats, clients or testimonials not in the brief. Plain, human, specific language. No hype words (revolutionary, game-changer, unlock, leverage, synergy).';

function brief() {
  const b = getJSON('brand', {});
  if (!b.name) throw new Error('Fill in your Brand first (Brand page) so the team knows what you sell.');
  return [
    `Business: ${b.name}${b.website ? ` (${b.website})` : ''}`,
    b.offer && `Offer: ${b.offer}`,
    b.audience && `Ideal customer: ${b.audience}`,
    b.usp && `Why us: ${b.usp}`,
    b.pricing && `Pricing: ${b.pricing}`,
    b.proof && `Proof we can mention: ${b.proof}`,
    b.tone && `Voice: ${b.tone}`,
    b.avoid && `Never say: ${b.avoid}`,
    b.cta && `Main call to action: ${b.cta}`,
  ].filter(Boolean).join('\n');
}

async function brandFromWebsite(url) {
  if (!/^https?:\/\//i.test(url)) url = 'https://' + url;
  const res = await fetch(url, { headers: { 'User-Agent': 'Mozilla/5.0' }, signal: AbortSignal.timeout(20000) });
  if (!res.ok) throw new Error(`Could not open ${url} (${res.status})`);
  const html = await res.text();
  const text = html
    .replace(/<(script|style|noscript|svg)[\s\S]*?<\/\1>/gi, ' ')
    .replace(/<[^>]+>/g, ' ').replace(/&nbsp;/g, ' ').replace(/&amp;/g, '&')
    .replace(/\s+/g, ' ').trim().slice(0, 6000);
  const r = await ask({
    task: 'brand', json: true, maxTokens: 700,
    system: `You extract a marketing brief from website text. Return JSON with keys: name, offer, audience, usp, pricing, proof, tone, cta, search_hint (where to find buyers on the web: types of companies, industries, regions, signals such as "agencies in the US hiring marketers"). Each value is one or two short sentences, or "" if the text does not say. ${RULES}`,
    user: `URL: ${url}\n\n${text}`,
  });
  return { ...r, website: url };
}

const plan = (goal) => ask({
  task: 'strategy', maxTokens: 1800,
  system: `You are a senior CMO for a small business with a tiny budget. Write a practical 30-day marketing plan in Markdown. Sections: ## Goal & target, ## Best 3 channels (and why), ## Weekly plan (Week 1-4, concrete tasks), ## Email outreach angle (who to contact, 2 subject line ideas), ## Content ideas (8 bullets), ## What to measure. Keep it under 600 words. ${RULES}`,
  user: `${brief()}\n\nGoal for the next 30 days: ${goal || 'Get first paying customers'}`,
});

const CHANNEL_GUIDE = {
  LinkedIn: 'LinkedIn post, 80-180 words, strong first line, short paragraphs, 1 question at the end, max 3 hashtags.',
  'X / Twitter': 'Single tweet under 270 characters, punchy, max 1 hashtag.',
  Facebook: 'Facebook post, 40-120 words, friendly, clear call to action.',
  Instagram: 'Instagram caption, 50-120 words, line breaks, 5-8 relevant hashtags at the end, plus a one-line image idea in [brackets] at the top.',
  'Blog post': 'Blog post in Markdown, 500-700 words, SEO-friendly H1 and H2s, meta description on the first line as "Meta: ...".',
  Newsletter: 'Email newsletter: Subject line, preview text, then a 150-250 word body with one call to action.',
  'Google / Meta ad': 'Ad copy: 3 headlines (max 30 chars), 2 descriptions (max 90 chars), 1 primary text (max 125 chars).',
};

async function content(channel, topic, count = 3) {
  const guide = CHANNEL_GUIDE[channel] || channel;
  const r = await ask({
    task: 'content', json: true, maxTokens: channel === 'Blog post' ? 1600 : 1200,
    system: `You are a marketing copywriter. Write ${count} distinct variations. Format: ${guide} ${RULES} Return JSON: {"items": ["...", "..."]}.`,
    user: `${brief()}\n\nTopic / angle: ${topic || 'Introduce what we do and who it helps'}`,
  });
  return (r.items || []).filter(Boolean).slice(0, count);
}

async function scoreLeads(leads) {
  const r = await ask({
    task: 'score', json: true, maxTokens: 60 + leads.length * 60,
    system: 'You qualify B2B/B2C leads against the ideal customer. Score 0-100 (fit + likely need). Return JSON {"scores":[{"id":1,"score":80,"reason":"max 12 words"}]}. If info is thin, score around 50 and say so.',
    user: `${brief()}\n\nLeads:\n${leads.map((l) => `${l.id}. ${l.name || '?'} | ${l.role || ''} | ${l.company || ''} | ${l.website || ''} | ${l.notes || ''}`).join('\n')}`,
  });
  return r.scores || [];
}

function lead(l) {
  return `Name: ${l.name || 'unknown'}\nRole: ${l.role || ''}\nCompany: ${l.company || ''}\nWebsite: ${l.website || ''}\nNotes: ${l.notes || ''}`;
}

const EMAIL_RULES = 'Cold email best practice: 50-110 words, plain text, no links except the website if useful, personalise the first line using the lead info (do not fake familiarity), one clear low-friction ask, sign with the sender first name. Subject: 2-6 words, lowercase-friendly, no clickbait. Do not add an unsubscribe line (added automatically).';

const firstEmail = (l, sender) => ask({
  task: 'outreach', json: true, maxTokens: 400,
  system: `You write first-touch sales emails. ${EMAIL_RULES} ${RULES} Return JSON {"subject":"...","body":"..."}.`,
  user: `${brief()}\nSender: ${sender || 'the founder'}\n\nLead:\n${lead(l)}`,
});

const followUp = (l, thread, n, sender) => ask({
  task: 'followup', json: true, maxTokens: 300,
  system: `You write follow-up #${n} to a cold email that got no reply. 30-70 words, add one new useful point or angle, polite, easy yes/no ask. ${n >= 2 ? 'This is the last follow-up: say so kindly.' : ''} ${RULES} Return JSON {"body":"..."}.`,
  user: `${brief()}\nSender: ${sender || 'the founder'}\n\nLead:\n${lead(l)}\n\nPrevious emails:\n${thread}`,
});

const triage = (l, thread, incoming, sender, booking) => ask({
  task: 'reply', json: true, maxTokens: 500,
  system: `You are a sales rep handling a reply to our outreach, working on your own. Classify intent as one of: interested (wants a call/demo/meeting/trial/pricing to buy), question, not_now, not_interested, unsubscribe, out_of_office, other.
Write a 1-line summary. Then write our reply (40-120 words):
- interested: thank them, answer anything they asked, and invite them to book ${booking ? `using this link: ${booking}` : 'a call (ask for 2-3 times that suit them)'}.
- question: answer only with facts from the brief, then suggest a short call${booking ? ` (${booking})` : ''}.
- not_now: gracious, offer to check back later. no pressure.
- not_interested / unsubscribe / out_of_office: reply "".
Set needs_human true if: they ask something the brief cannot answer, ask for a custom deal/discount/contract/legal/security detail, are upset, or anything feels risky. ${RULES}
Return JSON {"intent":"...","summary":"...","reply":"...","needs_human":false}.`,
  user: `${brief()}\nSender: ${sender || 'the founder'}\n\nLead:\n${lead(l)}\n\nThread so far:\n${thread}\n\nTheir new message:\n${incoming}`,
});

module.exports = { brandFromWebsite, plan, content, scoreLeads, firstEmail, followUp, triage, CHANNELS: Object.keys(CHANNEL_GUIDE) };
