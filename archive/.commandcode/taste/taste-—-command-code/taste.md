# Taste — Command Code
- Wants major planning deliverables as a polished PDF in a corporate-office style: strong typography, no colors (monochrome/greyscale only), heavily structured with clear sections, phases and tables. Confidence: 0.8
- Planning documents should be written to be machine-decodable — structured enough that any AI chat can pick it up and proceed with implementation. Confidence: 0.7
- Build-facing docs should be optimized for low token cost while coding: one small self-contained unit per task (files it touches, what to do, stop condition) so each step is easy to understand and nothing large must be loaded to answer a small question. Confidence: 0.75
- Targets extremely low AI operating cost — targets under ~$1/month for model inference and corrects estimates that assume more; budget ceilings should be set as runaway guards, well above expected normal spend. Confidence: 0.75
- For quick side questions, wants short answers — "answer in few words" — not a wall of context. Confidence: 0.55
- Wants honest realism over optimism — wants assumptions, weak points and failure modes stated plainly rather than reassurance that everything will work; self-describes as "a realistic man with good vision". Confidence: 0.8
- Completion claims must be backed by evidence: don't treat placeholder/fixture tests as real-world validation, don't claim something works or is done without verification output, and keep coverage/status reports honest rather than flattering. Confidence: 0.7
- Prefers autonomous progress over blocking: keep working with placeholders and controlled fixtures when real credentials or business details are missing, and ask only when something is genuinely essential. Confidence: 0.65
- When he asks for a code review, he wants read-only feedback — suggestions and findings only, no edits to his files; even when asking for concrete code, drafts should be handed over separately ("nothing in your repo changes") rather than applied. Confidence: 0.7
