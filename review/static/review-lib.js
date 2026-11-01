// The review page's pure functions: warnings for spoken text, and the edits to save.

const SYMBOLS = ['%', '$', '=', '+', '/', 'σ', 'μ', 'Δ', '√'];

// One message per problem in text the voice will read aloud.
export function spokenWarnings(text) {
  const out = [];
  if (/\d/.test(text)) out.push('Has digits: the voice may read them oddly. Write numbers in words.');
  for (const s of SYMBOLS) if (text.includes(s)) out.push(`Has the symbol ${s}: write it in words.`);
  return out;
}

// Module fields the page may change (as in review/plan.py), besides each tool's mistakes.
const FIELDS = ['examples', 'status', 'notes'];
// Top-level fields the page may change.
const TOP = ['notes', 'intro_status'];
const same = (a, b) => JSON.stringify(a) === JSON.stringify(b);

// The changed editable fields of current against original, in the shape /api/save takes.
export function collectEdits(original, current) {
  const edits = { modules: {} };
  for (const f of TOP) if (!same(original[f], current[f])) edits[f] = current[f];
  current.modules.forEach((m, i) => {
    const o = original.modules[i];
    const changed = {};
    for (const f of FIELDS) if (!same(o[f], m[f])) changed[f] = m[f];
    const mistakes = {};
    (m.tools || []).forEach((t, k) => {
      if (!same(o.tools[k].mistakes, t.mistakes)) mistakes[t.name] = t.mistakes;
    });
    if (Object.keys(mistakes).length) changed.mistakes = mistakes;
    if (Object.keys(changed).length) edits.modules[m.n] = changed;
  });
  return edits;
}

export function isDirty(original, current) {
  const e = collectEdits(original, current);
  return TOP.some((f) => f in e) || Object.keys(e.modules).length > 0;
}

// What the page says after "Run the tests".  A pinned prompt hash fails after
// any edit to the intros or objectives, by design: Claude re-pins it.
export function testsMessage(ok, summary) {
  if (ok) return 'All tests pass.';
  const failed = summary.split('\n').filter((l) => l.startsWith('FAILED'));
  if (failed.length && failed.every((l) => l.includes('test_voice_prompt_unchanged')))
    return 'Only the prompt check fails. That is expected after you edit the intros or objectives: '
      + 'the tutor\'s prompt changed, and Claude re-pins it when you say you are done.';
  return 'Some tests fail. Tell Claude.';
}
