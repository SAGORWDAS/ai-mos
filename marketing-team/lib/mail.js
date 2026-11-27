// Gmail via SMTP (send) and IMAP (read replies), using a Google App Password.
const nodemailer = require('nodemailer');
const { ImapFlow } = require('imapflow');
const { simpleParser } = require('mailparser');
const { getSetting } = require('./db');

function creds() {
  const user = getSetting('gmail_user');
  const pass = getSetting('gmail_pass').replace(/\s+/g, '');
  if (!user || !pass) throw new Error('Add your Gmail address and App Password in Settings first.');
  return { user, pass };
}

let transport, transportKey;
function smtp() {
  const c = creds();
  const k = c.user + c.pass;
  if (!transport || transportKey !== k) {
    transport = nodemailer.createTransport({ host: 'smtp.gmail.com', port: 465, secure: true, auth: c });
    transportKey = k;
  }
  return transport;
}

async function send({ to, subject, text, inReplyTo }) {
  const { user } = creds();
  const name = getSetting('sender_name');
  const info = await smtp().sendMail({
    from: name ? `"${name.replace(/"/g, '')}" <${user}>` : user,
    to, subject, text,
    ...(inReplyTo ? { inReplyTo, references: inReplyTo } : {}),
  });
  return info.messageId;
}

function imap() {
  return new ImapFlow({ host: 'imap.gmail.com', port: 993, secure: true, auth: creds(), logger: false });
}

async function test() {
  await smtp().verify();
  const c = imap();
  await c.connect();
  await c.logout();
  return true;
}

// Return parsed inbox messages from the given senders received in the last `days` days.
async function fetchFrom(senders, days = 14) {
  if (!senders.size) return [];
  const c = imap();
  await c.connect();
  const out = [];
  const lock = await c.getMailboxLock('INBOX');
  try {
    const since = new Date(Date.now() - days * 864e5);
    const uids = await c.search({ since }, { uid: true });
    if (!uids || !uids.length) return out;
    const wanted = [];
    for await (const m of c.fetch(uids, { envelope: true }, { uid: true })) {
      const from = m.envelope?.from?.[0]?.address?.toLowerCase();
      if (from && senders.has(from)) wanted.push(m.uid);
    }
    if (!wanted.length) return out;
    for await (const m of c.fetch(wanted, { source: true }, { uid: true })) {
      const p = await simpleParser(m.source);
      out.push({
        from: p.from?.value?.[0]?.address?.toLowerCase(),
        subject: p.subject || '',
        text: (p.text || '').split(/\n\s*On .+wrote:\s*\n/)[0].replace(/\n>.*$/gm, '').trim().slice(0, 4000),
        messageId: p.messageId,
        inReplyTo: p.inReplyTo,
        date: p.date?.toISOString(),
      });
    }
  } finally {
    lock.release();
    await c.logout().catch(() => {});
  }
  return out;
}

module.exports = { send, test, fetchFrom };
