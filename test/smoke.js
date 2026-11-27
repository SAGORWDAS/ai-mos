// End-to-end smoke test with OpenAI + Gmail faked. Run: npm test
const os = require('node:os'), fs = require('node:fs'), path = require('node:path'), assert = require('node:assert');
process.env.DATA_DIR = fs.mkdtempSync(path.join(os.tmpdir(), 'mkt-'));

const realFetch = global.fetch;
global.fetch = async (url, opt) => {
  if (!String(url).includes('api.openai.com')) return realFetch(url, opt);
  const sys = JSON.parse(opt.body).messages[0].content;
  const out = sys.includes('30-day') ? '## Goal\n- win' :
    sys.includes('variations') ? '{"items":["post A","post B"]}' :
    sys.includes('qualify') ? '{"scores":[{"id":1,"score":82,"reason":"good fit"}]}' :
    sys.includes('first-touch') ? '{"subject":"quick idea","body":"Hi Ann, ..."}' :
    sys.includes('follow-up') ? '{"body":"Following up"}' :
    '{"intent":"interested","summary":"Wants a call","reply":"Great, how about Tuesday?"}';
  return new Response(JSON.stringify({ choices: [{ message: { content: out } }], usage: { prompt_tokens: 100, completion_tokens: 50 } }));
};
const mail = require('../lib/mail');
const sent = [];
mail.send = async (m) => { sent.push(m); return `<id${sent.length}@test>`; };
mail.fetchFrom = async () => [{ from: 'ann@acme.com', subject: 'Re: quick idea', text: 'Sounds good, let us talk', messageId: '<r1@acme>', date: new Date().toISOString() }];

const { routes } = require('../server');
const { run } = require('../lib/db');
const call = (k, b = {}, id = 0, q = '') => routes[k](b, id, new URLSearchParams(q));

(async () => {
  await call('POST /api/settings', { openai_key: 'sk-test', gmail_user: 'me@gmail.com', gmail_pass: 'abcd', sender_name: 'Sam Lee' });
  await call('POST /api/brand', { name: 'Acme Cakes', offer: 'cakes' });
  assert.ok((await call('POST /api/plans', { goal: '10 clients' }))[0].body.includes('Goal'));
  assert.equal((await call('POST /api/content', { channel: 'LinkedIn', count: 2 })).length, 2);
  assert.equal(call('POST /api/leads', { leads: [{ email: 'ann@acme.com', name: 'Ann' }, { email: 'bad' }] }).added, 1);
  await call('POST /api/leads/score', {});
  assert.equal(call('GET /api/leads')[0].score, 82);
  assert.equal((await call('POST /api/outreach/draft', { ids: [1] })).drafted, 1);
  const d = call('GET /api/messages', {}, 0, 'status=draft')[0];
  assert.equal((await call('POST /api/messages/send', { ids: [d.id] })).sent, 1);
  assert.ok(sent[0].text.includes('unsubscribe'));
  // follow-up becomes due after N days
  run("UPDATE leads SET last_contacted=datetime('now','-5 days')");
  assert.equal((await call('POST /api/outreach/followups')).drafted, 1);
  // reply arrives: triaged, follow-up draft removed, reply draft created
  assert.equal((await call('POST /api/inbox/check')).found, 1);
  const drafts = call('GET /api/messages', {}, 0, 'status=draft');
  assert.deepEqual(drafts.map((m) => m.kind), ['reply']);
  assert.equal(call('GET /api/leads')[0].status, 'interested');
  assert.equal((await call('POST /api/inbox/check')).found, 0, 'no duplicate import');
  // unsubscribed leads are never emailed
  call('PATCH /api/leads/:id', { status: 'unsubscribed' }, 1);
  const r = await call('POST /api/messages/send', { ids: [drafts[0].id] });
  assert.equal(r.sent, 0);
  const st = call('GET /api/state');
  assert.ok(st.usage.total > 0 && !st.settings.openai_key.startsWith('sk'));
  console.log('smoke test passed ✓');
  process.exit(0);
})().catch((e) => { console.error(e); process.exit(1); });
