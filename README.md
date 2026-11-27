# AI Marketing Team

A low-cost AI marketing team that runs on your own computer. You need just two things: an **OpenAI API key** and a **Gmail account**.

**Paste your website. It does the rest:**

```
learns your product → finds matching companies on the web daily → emails them from your Gmail
→ follows up → answers questions → interested? sends your booking link + emails you 🔥
→ daily report to your inbox
```

You only step in when someone is ready for a meeting, or when the AI isn't sure how to answer (it emails you instead of guessing).

**Safety:** sends only Mon–Fri during work hours, at most 30 emails a day (protects your Gmail), puts an unsubscribe line on every email, never emails anyone who unsubscribed or whose address bounced, and never makes claims beyond your brand page.

**Cost:** about $1–3 a month in OpenAI usage at the default settings (10 leads a day). Spend is shown in the sidebar.

## Start (Windows)

1. Install **Node.js LTS** from https://nodejs.org (one time only).
2. Double-click **`start.bat`**. Your browser opens at http://localhost:3000.
3. Follow the two setup steps on the Home page, add your booking link in Settings, and switch **Autopilot** on.
4. To keep it running without thinking about it, double-click **`autostart-on.bat`** once. The app then starts hidden every time you log in to Windows. `autostart-off.bat` undoes this.

> It works only while your PC is on and awake. Set Windows → Power → Sleep to "Never" when plugged in if you want it to work all day.

Mac/Linux: `npm install` and then `npm start`.

## The two keys

- **OpenAI key:** go to platform.openai.com → API keys → Create, and add a few dollars of credit.
- **Gmail App Password:** go to myaccount.google.com → Security → turn on 2-Step Verification → search for "App passwords" → create one. Paste the 16-letter code into Settings. This is **not** your normal password.

Use the **Test** buttons in Settings to confirm both work.

## What you do

- Read the 🔥 alert emails and take the meeting. When you close a deal, click **Won** on the Home page.
- Read the daily report. Reply to any "Needs you" emails, or approve the drafted answer on the Outreach page.

## Notes

- All data, including your keys, stays in the `data/` folder on this PC. Delete that folder to reset.
- The app only accepts connections from this computer (localhost).
- Leads come from public company websites (e.g. hello@, founder@, sales@). The AI never guesses emails. You can also import your own CSV.
- To use a different model, change it in Settings and use **Test OpenAI** to check it. Update the two price fields so the cost tracking stays accurate.
- `npm test` runs an end-to-end check with OpenAI and Gmail faked.
- The original planning documents (blueprint, spec, PDFs) are in `archive/`.
