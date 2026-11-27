// End-to-end smoke test with OpenAI + Gmail faked. Run: npm test
const os = require('node:os'), fs = require('node:fs'), path = require('node:path'), assert = require('node:assert');
process.env.DATA_DIR = fs.mkdtempSync(path.join(os.tmpdir(), 'mkt-'));

const realFetch = global.fetch;
global.fetch = async (url, opt) => {
  url = String(url);
  if (url.includes('/v1/responses')) return new Response(JSON.stringify({ output: [{ content: [{ type: 'output_text', text: 'Here: [{"company":"Bolt Co","website":"https://boltco.io","contact_name":"Ben","email":"","why":"growing team"}]' }] }], usage: { input_tokens: 500, output_tokens: 200 } }));
  if (url.startsWith('https://dir.test')) {
    const pages = {
      '/': '<a href="/about/">About</a><a href="/categories/">Cats</a>',
      '/categories/': '<a href="/categories/plumbers/">Plumbers</a><a href="/categories/cafes/">Cafes</a>',
      '/categories/plumbers/': '<a href="/about/">About</a><a href="/fast-plumbing/">Fast</a><a href="/fast-plumbing">Fast</a><a href="/no-site-plumbing/">NoSite</a>',
      '/fast-plumbing/': '<h1>Fast Plumbing</h1><a href="https://facebook.com/x">fb</a><a href="https://fastplumb.com.au">site</a><a href="tel:0400111222">call</a>',
      '/no-site-plumbing/': '<h1>No Site Plumbing</h1><a href="tel:0400333444">call</a>',
      '/robots.txt': 'User-agent: *' + String.fromCharCode(10) + 'Disallow: /login',
    };
    const p = new URL(url).pathname;
    return pages[p] ? new Response(pages[p]) : new Response('nf', { status: 404 });
  }
  if (url.startsWith('https://fastplumb.com.au')) return new Response(url.endsWith('/contact') ? 'mail office@fastplumb.com.au' : '<html>© 2019 Fast</html>');
  if (url.startsWith('https://janedoe.design')) return new Response(url.endsWith('/about-me') ? 'Email me: jane.doe.design@gmail.com or hello@janedoe.design. logo@2x.png' : 'portfolio');
  if (url.startsWith('https://boltco.io')) return new Response(url.endsWith('/contact') ? '<a href="mailto:hello@boltco.io">x</a> privacy@boltco.io' : 'no email here');
  if (!url.includes('api.openai.com')) return realFetch(url, opt);
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
let n = 0;
mail.send = async (m) => { sent.push(m); return `<id${++n}@test>`; };
let inbox = [{ from: 'ann@acme.com', subject: 'Re: quick idea', text: 'Sounds good, let us talk', messageId: '<r1@acme>', date: new Date().toISOString() }];
mail.fetchFrom = async () => inbox;
require('node:dns').promises.resolveMx = async () => [{ exchange: 'mx' }];

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
  assert.equal(call('GET /api/leads')[0].status, 'meeting');
  assert.equal((await call('POST /api/inbox/check')).found, 0, 'no duplicate import');
  // unsubscribed leads are never emailed
  call('PATCH /api/leads/:id', { status: 'unsubscribed' }, 1);
  const r = await call('POST /api/messages/send', { ids: [drafts[0].id] });
  assert.equal(r.sent, 0);
  const st = call('GET /api/state');
  assert.ok(st.usage.total > 0 && !st.settings.openai_key.startsWith('sk'));
  // ---- autopilot ----
  const engine = require('../lib/engine');
  await call('POST /api/settings', { autopilot: '1', work_start: '0', work_end: '24', booking_link: 'https://cal.com/sam' });
  inbox = [];
  sent.length = 0;
  await engine.tick();
  const ben = call('GET /api/leads').find((l) => l.email === 'hello@boltco.io');
  assert.ok(ben, 'lead found via web search + contact page');
  assert.equal(ben.status, 'contacted', 'first email sent automatically');
  assert.equal(sent[0].to, 'hello@boltco.io');
  // Ben replies interested → auto reply + owner alert + status meeting
  inbox = [{ from: 'hello@boltco.io', subject: 'Re: quick idea', text: 'Yes keen to chat', messageId: '<b1@bolt>', date: new Date().toISOString() }];
  sent.length = 0;
  await engine.checkInbox();
  assert.equal(call('GET /api/leads').find((l) => l.id === ben.id).status, 'meeting');
  assert.ok(sent.some((m) => m.to === 'hello@boltco.io'), 'auto replied');
  assert.ok(sent.some((m) => m.to === 'me@gmail.com' && /Meeting-ready/.test(m.subject)), 'owner alerted');
  // bounce handling
  run("INSERT INTO leads(email,status) VALUES('gone@x.com','contacted')");
  inbox = [{ from: 'mailer-daemon@googlemail.com', subject: 'Delivery Status Notification', text: "Your message wasn't delivered to gone@x.com", messageId: '<d1>' }];
  await engine.checkInbox();
  assert.equal(call('GET /api/leads').find((l) => l.email === 'gone@x.com').status, 'bounced');
  assert.ok(/emails sent/.test(engine.report().subject));
  // individuals: personal address on their own site wins over generic inbox
  const { findEmail } = require('../lib/finder');
  assert.equal(await findEmail('janedoe.design', '', 'Jane Doe'), 'jane.doe.design@gmail.com');
  assert.equal(await findEmail('janedoe.design', 'guess@gmail.com', ''), 'hello@janedoe.design', 'never trusts unseen free-mail');
  // directories: category → listings → website email; no-website → call list
  const src = require('../lib/sources');
  const cats = await src.listCategories('https://dir.test/');
  assert.equal(cats.length, 2);
  run('INSERT INTO sources(url,categories) VALUES(?,?)', 'https://dir.test/', JSON.stringify([cats.find((c) => c.name === 'Plumbers')]));
  const res = await src.runSource(call('GET /api/sources')[0], 10);
  assert.deepEqual([res.emails, res.calls, res.checked], [1, 1, 2]);
  const fp = call('GET /api/leads').find((l) => l.email === 'office@fastplumb.com.au');
  assert.ok(fp && fp.company === 'Fast Plumbing' && fp.phone === '0400111222');
  assert.ok(call('GET /api/leads').some((l) => l.status === 'call' && l.company === 'No Site Plumbing'));
  assert.equal((await src.runSource(call('GET /api/sources')[0], 10)).checked, 0, 'never re-reads a listing');
  const { auditSite } = require('../lib/audit');
  assert.match(await auditSite('https://fastplumb.com.au'), /2019.*|mobile/);
  console.log('smoke test passed ✓');
  process.exit(0);
})().catch((e) => { console.error(e); process.exit(1); });
