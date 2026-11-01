import test from 'node:test';
import assert from 'node:assert/strict';
import { splitMath, fillMath, stripBold, markFormulaLines, rmsLoudness, UNLOCK_EVENTS } from '../../static/voice.js';

test('complete $$ blocks become placeholders on their own lines', () => {
  const { md, blocks } = splitMath('Here is q. $$q = \\frac{R-d}{u-d}$$ Next.');
  assert.deepEqual(blocks, ['q = \\frac{R-d}{u-d}']);
  assert.equal(md, 'Here is q. \n\n@@math0@@\n\n Next.');
});

test('multi-line blocks and several blocks keep their order', () => {
  const { md, blocks } = splitMath('A\n$$\nx\n$$\nB\n$$y$$');
  assert.deepEqual(blocks, ['x', 'y']);
  assert.ok(md.indexOf('@@math0@@') < md.indexOf('@@math1@@'));
});

test('an unclosed $$ while streaming hides the tail', () => {
  assert.equal(splitMath('Here is q. $$q = \\fr', true).md, 'Here is q. ');
  assert.equal(splitMath('Price is $', true).md, 'Price is ');
});

test('an unclosed $$ in a finished reply is kept as text', () => {
  assert.equal(splitMath('Cost $$5 total', false).md, 'Cost $$5 total');
});

test('fillMath replaces a whole placeholder paragraph with a board block', () => {
  const html = '<p>Hi</p>\n<p>@@math0@@</p>\n';
  const out = fillMath(html, ['x'], (tex) => `<span>${tex}</span>`);
  assert.equal(out, '<p>Hi</p>\n<div class="board math"><span>x</span></div>\n');
});

test('stripBold keeps the text of strong elements', () => {
  assert.equal(stripBold('<p>a <strong>key</strong> idea</p>'), '<p>a key idea</p>');
});

test('rmsLoudness maps silence to 0 and loud speech to 1', () => {
  assert.equal(rmsLoudness(new Float32Array(64)), 0);
  const loud = new Float32Array(64).fill(0.5);
  assert.equal(rmsLoudness(loud), 1);
  const normal = new Float32Array(64).map((_, i) => (i % 2 ? 0.1 : -0.1));
  const v = rmsLoudness(normal);
  assert.ok(v >= 0.4 && v <= 0.8, `normal speech ${v}`);
});

test('stripBold also removes b elements, with or without attributes', () => {
  assert.equal(stripBold('<p><b>x</b> <b class="k">y</b> <br> <strong>z</strong></p>'), '<p>x y <br> z</p>');
});

test('audio unlocks on taps too (iOS Safari sends touchend and click)', () => {
  for (const ev of ['pointerdown', 'keydown', 'touchend', 'click']) assert.ok(UNLOCK_EVENTS.includes(ev), ev);
});

import { splitSections } from '../../static/voice.js';

test('splitSections: "## Title" lines start sections', () => {
  const t = 'Intro words.\n## One-period call\n- Strike K = 100\nSay this.\n## Finding q\n$$q$$\n';
  assert.deepEqual(splitSections(t, true), [
    { title: null, body: 'Intro words.\n' },
    { title: 'One-period call', body: '- Strike K = 100\nSay this.\n' },
    { title: 'Finding q', body: '$$q$$\n' },
  ]);
});

test('splitSections: a heading counts only once its line is complete while streaming', () => {
  assert.deepEqual(splitSections('## One-per', false), []);
  assert.deepEqual(splitSections('Intro.\n## Fin', false), [{ title: null, body: 'Intro.\n' }]);
  assert.deepEqual(splitSections('## One-per', true), [{ title: 'One-per', body: '' }]);
  assert.deepEqual(splitSections('## Setup\n- S', false), [{ title: 'Setup', body: '- S' }]);
});

test('splitSections: no empty leading part; ### is not a section', () => {
  assert.deepEqual(splitSections('\n## A\nx', true), [{ title: 'A', body: 'x' }]);
  assert.deepEqual(splitSections('### Note\nx', true), [{ title: null, body: '### Note\nx' }]);
});

test('a prose paragraph with = goes on the board; other prose stays spoken only', () => {
  const html = '<p>Find: σ = 0.0126 × √252 = ?</p>\n<p>What do you get?</p>\n<p>@@math0@@</p>';
  assert.equal(markFormulaLines(html),
    '<p class="formula">Find: σ = 0.0126 × √252 = ?</p>\n<p>What do you get?</p>\n<p>@@math0@@</p>');
});
