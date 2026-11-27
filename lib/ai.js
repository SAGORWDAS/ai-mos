// Thin OpenAI client: one function, usage + cost logged per call.
const { getSetting, run } = require('./db');

const isReasoning = (m) => /^(o\d|gpt-5)/i.test(m);

async function ask({ task, system, user, json = false, maxTokens = 1200 }) {
  const key = getSetting('openai_key');
  if (!key) throw new Error('Add your OpenAI API key in Settings first.');
  const model = getSetting('model') || 'gpt-4o-mini';
  const body = {
    model,
    messages: [{ role: 'system', content: system }, { role: 'user', content: user }],
    max_completion_tokens: isReasoning(model) ? maxTokens + 2000 : maxTokens,
  };
  if (json) body.response_format = { type: 'json_object' };
  if (isReasoning(model)) body.reasoning_effort = 'low';

  const res = await fetch('https://api.openai.com/v1/chat/completions', {
    method: 'POST',
    headers: { Authorization: `Bearer ${key}`, 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
    signal: AbortSignal.timeout(120000),
  });
  const data = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(`OpenAI: ${data.error?.message || res.statusText}`);

  const u = data.usage || {};
  const cost = ((u.prompt_tokens || 0) * +getSetting('price_in') + (u.completion_tokens || 0) * +getSetting('price_out')) / 1e6;
  run('INSERT INTO usage(task,model,tin,tout,cost) VALUES(?,?,?,?,?)', task, model, u.prompt_tokens || 0, u.completion_tokens || 0, cost);

  const text = data.choices?.[0]?.message?.content?.trim() || '';
  if (!json) return text;
  try { return JSON.parse(text); } catch { throw new Error('AI returned an unreadable answer. Please try again.'); }
}

async function testKey(key, model) {
  const res = await fetch('https://api.openai.com/v1/models', { headers: { Authorization: `Bearer ${key}` }, signal: AbortSignal.timeout(20000) });
  const data = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(data.error?.message || 'Key rejected');
  const ids = (data.data || []).map((m) => m.id);
  if (!ids.includes(model)) {
    const hint = ids.filter((i) => /mini|nano/.test(i) && !/audio|realtime|tts|transcribe|search/.test(i)).slice(0, 6).join(', ');
    throw new Error(`Key works, but model "${model}" is not available to it. Try: ${hint}`);
  }
  return true;
}

module.exports = { ask, testKey };
