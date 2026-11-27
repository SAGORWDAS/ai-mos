// SQLite storage (built into Node). One file: data/marketing.db
const fs = require('node:fs');
const path = require('node:path');
const { DatabaseSync } = require('node:sqlite');

// Online (HOST set to a public address), keep data in the home folder so redeploys don't wipe it.
// Online, keep data outside the app folder so redeploys don't wipe it. Hosts differ in which folders survive a
// redeploy, so we try several, leave a marker in each, and use the first that already holds our database.
const hosted = process.env.HOST && !['127.0.0.1', 'localhost'].includes(process.env.HOST);
const app = path.join(__dirname, '..');
const candidates = process.env.DATA_DIR ? [process.env.DATA_DIR] : hosted
  ? [path.join(app, '..', 'ai-marketing-data'), path.join(app, '..', '..', 'ai-marketing-data'), path.join(require('node:os').homedir(), 'ai-marketing-data')]
  : [path.join(app, 'data')];
const storage = [];
for (const d of candidates) {
  try {
    fs.mkdirSync(d, { recursive: true });
    const marker = path.join(d, 'starts.txt');
    const starts = fs.existsSync(marker) ? fs.readFileSync(marker, 'utf8').split('\n').filter(Boolean).length : 0;
    fs.appendFileSync(marker, new Date().toISOString() + '\n');
    storage.push({ dir: path.resolve(d), starts: starts + 1, db: fs.existsSync(path.join(d, 'marketing.db')) });
  } catch (e) { storage.push({ dir: path.resolve(d), error: e.code || e.message }); }
}
const dir = (storage.find((s) => s.db) || storage.find((s) => !s.error) || {}).dir;
if (!dir) throw new Error('No writable data folder. Set DATA_DIR to a folder the app can write to.');
console.log('Data folder:', dir, '| checked:', JSON.stringify(storage));
const db = new DatabaseSync(path.join(dir, 'marketing.db'));

db.exec(`
PRAGMA journal_mode = WAL;
CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT);
CREATE TABLE IF NOT EXISTS plans (id INTEGER PRIMARY KEY, created TEXT DEFAULT (datetime('now')), goal TEXT, body TEXT);
CREATE TABLE IF NOT EXISTS content (id INTEGER PRIMARY KEY, created TEXT DEFAULT (datetime('now')), channel TEXT, topic TEXT, body TEXT);
CREATE TABLE IF NOT EXISTS leads (
  id INTEGER PRIMARY KEY, created TEXT DEFAULT (datetime('now')),
  name TEXT, email TEXT UNIQUE COLLATE NOCASE, company TEXT, role TEXT, website TEXT, notes TEXT,
  score INTEGER, score_reason TEXT,
  status TEXT DEFAULT 'new', -- new | contacted | replied | interested | won | lost | unsubscribed
  last_contacted TEXT, followups INTEGER DEFAULT 0
);
CREATE TABLE IF NOT EXISTS messages (
  id INTEGER PRIMARY KEY, created TEXT DEFAULT (datetime('now')),
  lead_id INTEGER REFERENCES leads(id) ON DELETE CASCADE,
  direction TEXT, -- out | in
  kind TEXT,      -- first | followup | reply | inbound
  subject TEXT, body TEXT,
  status TEXT,    -- draft | sent | failed | received | handled
  intent TEXT, summary TEXT,
  message_id TEXT UNIQUE, in_reply_to TEXT, sent_at TEXT, error TEXT
);
CREATE TABLE IF NOT EXISTS usage (id INTEGER PRIMARY KEY, created TEXT DEFAULT (datetime('now')), task TEXT, model TEXT, tin INTEGER, tout INTEGER, cost REAL);
`);
db.exec('PRAGMA foreign_keys = ON');
db.exec("CREATE TABLE IF NOT EXISTS activity (id INTEGER PRIMARY KEY, created TEXT DEFAULT (datetime('now')), kind TEXT, text TEXT)");
const cols = db.prepare('PRAGMA table_info(leads)').all().map((c) => c.name);
if (!cols.includes('source')) db.exec("ALTER TABLE leads ADD COLUMN source TEXT DEFAULT 'manual'");
if (!cols.includes('phone')) db.exec('ALTER TABLE leads ADD COLUMN phone TEXT');
if (!cols.includes('audit')) db.exec('ALTER TABLE leads ADD COLUMN audit TEXT');
db.exec(`CREATE TABLE IF NOT EXISTS sources (id INTEGER PRIMARY KEY, created TEXT DEFAULT (datetime('now')), url TEXT, categories TEXT, active INTEGER DEFAULT 1, last_run TEXT, found INTEGER DEFAULT 0);
CREATE TABLE IF NOT EXISTS seen (url TEXT PRIMARY KEY);
CREATE TABLE IF NOT EXISTS signals (id INTEGER PRIMARY KEY, created TEXT DEFAULT (datetime('now')), url TEXT UNIQUE, platform TEXT, need TEXT,
  title TEXT, summary TEXT, location TEXT, posted TEXT, name TEXT, website TEXT, reply TEXT, status TEXT DEFAULT 'new', lead_id INTEGER);`);

const DEFAULTS = {
  model: 'gpt-4o-mini',
  price_in: '0.15',   // USD per 1M input tokens
  price_out: '0.60',  // USD per 1M output tokens
  daily_cap: '30',
  followup_days: '3',
  max_followups: '2',
  sender_name: '',
  gmail_user: '',
  gmail_pass: '',
  openai_key: '',
  footer: "Not relevant? Just reply \"unsubscribe\" and I won't email again.",
  auto_inbox: '1',
  autopilot: '0',
  booking_link: '',
  report_to: '',
  daily_new_leads: '10',
  target: 'both',
  web_search: '1',
  min_score: '50',
  work_start: '9',
  work_end: '17',
  // High-value buyers of a website, searched one niche × place at a time.
  niches: ['Dentists', 'Cosmetic & skin clinics', 'Physiotherapists', 'Law firms', 'Accountants & financial planners', 'Mortgage brokers',
    'Builders & renovators', 'Architects', 'Real estate agencies', 'Solar & air-conditioning installers', 'Veterinary clinics', 'Wedding venues'].join('\n'),
  places: ['Adelaide SA', 'Melbourne VIC', 'Sydney NSW', 'Brisbane QLD', 'Perth WA'].join('\n'),
  market_cursor: '0',
  timezone: 'Australia/Adelaide',
  signature: '', // added under every email; empty = name, business, website
  signals: '1', // daily search for public posts asking for a website
};

const getSetting = (k) => {
  const r = db.prepare('SELECT value FROM settings WHERE key=?').get(k);
  return r ? r.value : DEFAULTS[k] ?? '';
};
const setSetting = (k, v) =>
  db.prepare('INSERT INTO settings(key,value) VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value').run(k, String(v ?? ''));
const allSettings = () => Object.fromEntries(Object.keys(DEFAULTS).map((k) => [k, getSetting(k)]));

const getJSON = (k, d) => { try { return JSON.parse(getSetting(k)) ?? d; } catch { return d; } };
const setJSON = (k, v) => setSetting(k, JSON.stringify(v));

const all = (sql, ...p) => db.prepare(sql).all(...p);
const get = (sql, ...p) => db.prepare(sql).get(...p);
const run = (sql, ...p) => db.prepare(sql).run(...p);

const log = (kind, text) => { db.prepare('INSERT INTO activity(kind,text) VALUES(?,?)').run(kind, text); console.log(new Date().toLocaleTimeString(), kind, text); };

module.exports = { dir, storage, log, db, all, get, run, getSetting, setSetting, allSettings, getJSON, setJSON };
