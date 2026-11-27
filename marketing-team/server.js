// Load KEY=VALUE lines from .env if present (some hosts provide settings this way).
try {
  for (const line of require('node:fs').readFileSync(require('node:path').join(__dirname, '.env'), 'utf8').split(/\r?\n/)) {
    const m = line.match(/^\s*([A-Z_][A-Z0-9_]*)\s*=\s*(.*?)\s*$/i);
    if (m && !(m[1] in process.env)) process.env[m[1]] = m[2].replace(/^(['"])(.*)\1$/, '$2');
  }
} catch { /* no .env */ }

// AI Marketing Team — starter. Run: node server.js  →  http://localhost:3000
// Opens the port first (hosts like Hostinger require listen() within seconds), then loads the app.
const http = require('node:http');
const PORT = process.env.PORT || 3000; // a number, or a socket path on some hosts
const HOST = process.env.HOST || '127.0.0.1';
let app = null, failed = null;

const server = http.createServer((req, res) => {
  if (app) return app.handler(req, res);
  res.writeHead(failed ? 500 : 503, { 'Content-Type': 'text/plain; charset=utf-8', 'Retry-After': '3' });
  res.end(failed ? 'The app could not start: ' + failed.message : 'Starting up, refresh in a few seconds…');
});

const onListen = () => {
  console.log(`\n  AI Marketing Team is running → http://localhost:${PORT}\n  (keep this window open; press Ctrl+C to stop)\n`);
  setImmediate(() => {
    try { const a = require('./lib/app'); a.start(); app = a; }
    catch (e) { failed = e; console.error('Startup failed:', e); }
  });
};
/^\d+$/.test(String(PORT)) ? server.listen(+PORT, HOST, onListen) : server.listen(PORT, onListen);
