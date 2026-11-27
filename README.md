# AI Marketing Team

A low-cost AI marketing team that runs on your own computer. You need just two things: an **OpenAI API key** and a **Gmail account**.

| Role | What it does |
|---|---|
| **CMO** | Writes a 30-day marketing plan for your goal |
| **Copywriter** | LinkedIn, X, Facebook, Instagram, blog, newsletter and ad copy in your brand voice |
| **Lead qualifier** | Scores each lead's fit (0–100) against your ideal customer |
| **SDR** | Writes a personal first email for each lead and sends it from your Gmail |
| **Follow-up** | Drafts polite follow-ups when there's no reply, and stops as soon as someone replies |
| **Reply handler** | Reads replies, tags them (interested, question, not now, unsubscribe…) and drafts your answer |

You approve every email before it is sent. There is a daily send limit (default 30) to protect your Gmail account, an unsubscribe line on every outreach email, and anyone who unsubscribes is never emailed again.

**Cost:** with the default `gpt-4o-mini` model, one email costs well under $0.001, so $5 of OpenAI credit lasts a long time. Spend is shown in the sidebar.

## Start (Windows)

1. Install **Node.js LTS** from https://nodejs.org (one time only).
2. Double-click **`start.bat`**. Your browser opens at http://localhost:3000.
3. Follow the **Getting started** checklist on the Home page.

Mac/Linux: `npm install` and then `npm start`.

## The two keys

- **OpenAI key:** go to platform.openai.com → API keys → Create, and add a few dollars of credit.
- **Gmail App Password:** go to myaccount.google.com → Security → turn on 2-Step Verification → search for "App passwords" → create one. Paste the 16-letter code into Settings. This is **not** your normal password.

Use the **Test** buttons in Settings to confirm both work.

## Daily routine (about 5 minutes)

1. **Leads:** import a CSV (it needs an `email` column; name, company, title, website and notes are optional) → click **AI score fit** → select the best leads → click **Write emails**.
2. **Outreach:** read and edit the drafts, then click **Send**.
3. **Home:** click **Draft due follow-ups**. Replies are checked every 10 minutes, and the drafted answers wait in Outreach.

## Notes

- All data, including your keys, stays in the `data/` folder on this PC. Delete that folder to reset.
- The app only accepts connections from this computer (localhost).
- The AI does not invent contact emails. Bring your own leads from LinkedIn, Apollo, Google Maps, events or your customer list.
- To use a different model, change it in Settings and use **Test OpenAI** to check it. Update the two price fields so the cost tracking stays accurate.
- `npm test` runs an end-to-end check with OpenAI and Gmail faked.
- The original planning documents (blueprint, spec, PDFs) are in `archive/`.
