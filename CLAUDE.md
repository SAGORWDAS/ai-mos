# AI Marketing Team — Golden Lining Solution

Sells https://goldenliningsolution.com (website redesign, new sites, custom features, WordPress speed, content, UI design; Adelaide) on autopilot, using only an OpenAI key and the owner's Gmail.

**Live:** https://app.goldenliningsolution.com (Hostinger Node app, password login).
**Repo:** SAGORWDAS/ai-mos. Branch `app` = this folder = what is deployed. PR #2 adds it to `main` as `marketing-team/` (Auto-fix on). Never push to `main` directly.

## Flow (every weekday, Adelaide 9–5)
Find leads (web search: niche × city, plus optional directories) → audit their site, skip modern ones → score → short human email pitching the one service that fits + free website review → 2 follow-ups → read Gmail replies, answer, send booking link → alert owner when meeting-ready → daily report.
Also daily: "Website requests" (public posts asking for a new site/redesign) → poster's business email found → emailed automatically. Never post on platforms.

## Code
- `server.js` opens the port first (Hostinger needs listen() < 3s), then loads `lib/app.js` (routes, login, background jobs, static files with hashed asset URLs).
- `lib/db.js` SQLite (`node:sqlite`) + settings defaults. Hosted data dir: `~/ai-marketing-data` (= `/home/u144242772/domains/app.goldenliningsolution.com/ai-marketing-data`), survives redeploys.
- `lib/engine.js` autopilot tick, send rules, signature, time zone clock. `lib/agents.js` all AI prompts (HUMAN writing rules). `lib/finder.js` web search + email finding. `lib/signals.js` website requests. `lib/sources.js` directories. `lib/audit.js` site check.
- `public/` vanilla JS SPA, no build.
- Test: `npm test` (OpenAI + Gmail mocked). Run locally: `npm start` → http://localhost:3000.

## Deploy (zip upload; GitHub deploy is disabled in admin-access mode)
1. `npm test`, commit, `git push origin master:app`
2. `git archive -o ai-marketing-team.zip HEAD package.json package-lock.json server.js lib public README.md`
3. hPanel → app.goldenliningsolution.com → Deployments → Settings and redeploy → "Upload new files". **The owner uploads the zip.**
4. Click "Save and redeploy" (a Hostinger tip box often covers it: click the button via JS), wait ~20 s, verify `/api/state`.
Env on Hostinger: `HOST=0.0.0.0`, `APP_PASSWORD` (never write it down). Cron job: every 10 min `wget -q -O /dev/null https://app.goldenliningsolution.com/`.

## Live settings (Nov 2026)
gpt-4.1-mini, 5 leads/day, cap 30/day, Australia/Adelaide, Autopilot on, signature set (uses `{name}`), 12 niches × 5 capital cities.
Owner still to add: their name, OpenAI key, Gmail App Password, booking link. Claude never types keys or passwords.

## Owner preferences
- Cost is the main concern (~$2/month now). Explain costs before adding paid calls.
- Answers short, flows as arrows (A → B → C).
- Emails must read human: short, specific, no clichés, signature added automatically.
- Ask before big or risky changes; small fixes can just be done, then tested and deployed.

## Gotchas
- `String.replace` with `$$` in replacement strings eats a `$`; use split/join in patch scripts.
- hPanel File Manager opens as a popup (blocked in the browser pane); use Runtime logs or `/api/state` `storage`.
- Check in ~2 weeks: if Website requests rarely finds emails, turn it off to save ~$0.65/month; ramp leads 5 → 10 → 20 if no bounces.
