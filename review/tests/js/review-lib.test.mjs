import test from 'node:test';
import assert from 'node:assert/strict';
import { spokenWarnings, collectEdits, isDirty } from '../../static/review-lib.js';

const DIGITS = 'Has digits: the voice may read them oddly. Write numbers in words.';

test('plain words get no warnings', () => {
  assert.deepEqual(spokenWarnings('about two percent'), []);
});

test('digits and symbols are named', () => {
  const w = spokenWarnings('a 60/40 mix');
  assert.ok(w.includes(DIGITS));
  assert.ok(w.includes('Has the symbol /: write it in words.'));
  assert.equal(w.length, 2);
});

test('each symbol is named once', () => {
  assert.deepEqual(spokenWarnings('σ and σ and %'),
    ['Has the symbol %: write it in words.', 'Has the symbol σ: write it in words.']);
});

const plan = () => ({
  notes: '',
  intro_status: 'open',
  modules: [
    { n: 1, examples: [], status: 'open', notes: '',
      tools: [{ name: 't', mistakes: [{ did: 'a', ask: 'b' }] }] },
    { n: 2, examples: [], status: 'open', notes: '', tools: [] },
  ],
});

test('an unchanged copy has no edits', () => {
  assert.deepEqual(collectEdits(plan(), plan()), { modules: {} });
  assert.equal(isDirty(plan(), plan()), false);
});

test('a changed field is the only edit', () => {
  const cur = plan(); cur.modules[1].notes = 'x';
  assert.deepEqual(collectEdits(plan(), cur), { modules: { 2: { notes: 'x' } } });
  assert.equal(isDirty(plan(), cur), true);
});

test('changed mistakes are sent by tool name, and top-level notes too', () => {
  const cur = plan(); cur.modules[0].tools[0].mistakes[0].ask = 'c'; cur.notes = 'hi';
  assert.deepEqual(collectEdits(plan(), cur),
    { notes: 'hi', modules: { 1: { mistakes: { t: [{ did: 'a', ask: 'c' }] } } } });
});

test('the Introduction\'s status is a top-level edit', () => {
  const cur = plan(); cur.intro_status = 'reviewed';
  assert.deepEqual(collectEdits(plan(), cur), { intro_status: 'reviewed', modules: {} });
  assert.equal(isDirty(plan(), cur), true);
});

test('read-only fields are never sent', () => {
  const cur = plan(); cur.modules[0].title = 'changed';
  assert.deepEqual(collectEdits(plan(), cur), { modules: {} });
});

import { testsMessage } from '../../static/review-lib.js';

test('a failing prompt hash alone is explained as expected', () => {
  const m = testsMessage(false, 'FAILED binomial/tests/test_prompt.py::test_voice_prompt_unchanged - AssertionError\n1 failed, 156 passed');
  assert.match(m, /expected after you edit/);
});

test('other failures are reported as failures', () => {
  assert.match(testsMessage(false, 'FAILED x/tests/test_tools.py::test_price - AssertionError\n1 failed'), /^Some tests fail/);
  assert.match(testsMessage(true, '157 passed'), /^All tests pass/);
});
