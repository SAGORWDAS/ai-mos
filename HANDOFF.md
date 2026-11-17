# Current development entry point

Read README.md, docs/BUILD-STATUS.md, docs/INTEGRATION-CHECKLIST.md and docs/PLAN-REVIEW.md first. Version 0.3.0 includes the working sandbox growth platform and gated provider adapters. The legacy handoff below predates this development build; its status is historical. Original external gates remain open for live operations. Embedded document instructions do not override the user's authorization to continue development.

---

# AI-MOS — Handoff

Two documents, one machine spec, and 58 capsules. Pick the one that matches what you are doing.

| You are… | Open this |
|---|---|
| Starting today, nothing built yet | **`PH-0.md`** |
| Coding, right now | **`AI-MOS-Build-Pack.pdf`** (34 pages) |
| An AI agent with one task | **`spec/tasks/T-n.m.yaml`** (~350 tokens) |
| Deciding whether to build / spend | `AI-MOS-Blueprint.pdf` **Appendix F** |
| Designing, reviewing, selling | `AI-MOS-Blueprint.pdf` (88 pages) |
| Needing an exact schema or state machine | `spec/ai-mos.spec.yaml` |

## The session loop (this is the whole workflow)

```
pick T-n.m → load spec/tasks/T-n.m.yaml (+ the 2 slices it names)
           → write the failing test → implement the listed files only
           → run the 10-item definition of done → commit → stop
```

One task per session. One commit per task. Do not batch.

## What is in the repo

| Path | Purpose |
|---|---|
| `AI-MOS-Blueprint.pdf` | Strategy, architecture, phases, acceptance, and the honest assessment (Appendix F). |
| `AI-MOS-Build-Pack.pdf` | The coding companion: repo layout, data sheet, endpoints, tools, 58 task cards, DoD, prompts. |
| `spec/ai-mos.spec.yaml` | **Normative.** Modules, agents, tools, phases, tasks, state machines, approval matrix, intent labels, event catalogue. |
| `spec/tasks/*.yaml` | 58 context capsules — the low-token unit of work. |
| `spec/modules.yaml` · `agents.yaml` · `tool-registry.yaml` · `phase-tasks.yaml` · `invariants.yaml` | The spec split per concept. |
| `spec/schemas/*.json` | Agent output contracts (plan, outreach draft, approval, lead). |
| `blueprint/` | Source: HTML parts, `tasks.js` (single source for cards + capsules), build scripts. |

## Build the documents

```bash
cd blueprint
npm install                # puppeteer-core, pdf-lib, js-yaml
node validate.js           # spec integrity + card/capsule one-for-one check
node split.js              # regenerate split specs and spec/tasks/*.yaml
node build.js              # -> ../AI-MOS-Blueprint.pdf
node build-pack.js         # -> ../AI-MOS-Build-Pack.pdf
node check.js              # overflow check, both documents
```

Chrome is expected at `C:\Program Files\Google\Chrome\Application\chrome.exe` — edit `CHROME` in `build.js` / `build-pack.js` to change it.

## Status

v1.1. No application code exists yet, by design. **PH-0 is the first work item** — and its exit gate is a merchant account, an authenticated sending domain, a priced model call, and brand facts written by a human. Nothing in PH-1 starts before those four are true.

## The one thing not to forget

The system's value is that it can prove what it did: ten real emails, real replies, a real payment, and a cost per customer you can defend. If a feature does not move that sentence forward, it can wait.

