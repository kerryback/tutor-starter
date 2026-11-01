import test from 'node:test';
import assert from 'node:assert/strict';
import { frameKey, sliderText, startIndices, addSliders } from '../../static/plot-sliders.js';

test('the frame key joins the positions', () => {
  assert.equal(frameKey([3, 6]), '3,6');
  assert.equal(frameKey([0]), '0');
});

test('a slider shows its label, or its value', () => {
  assert.equal(sliderText({ values: [0.01, 0.02], labels: ['1%', '2%'] }, 1), '2%');
  assert.equal(sliderText({ values: [0.5, 1] }, 0), '0.5');
});

test('start positions stay within the values', () => {
  assert.deepEqual(startIndices([{ values: [1, 2, 3], index: 7 }, { values: [1, 2], index: -1 }, { values: [1] }]), [2, 0, 0]);
});

// A small stand-in for the DOM: just enough for addSliders.
function el(tag) {
  return {
    tag, children: [], attrs: {}, listeners: {}, textContent: '', className: '',
    append(...k) { this.children.push(...k); }, appendChild(k) { this.children.push(k); },
    setAttribute(k, v) { this.attrs[k] = v; },
    addEventListener(t, f) { this.listeners[t] = f; },
  };
}

test('moving a slider redraws with that combination\'s frame and title', () => {
  globalThis.document = { createElement: el };
  const drawn = [];
  const P = { react: (area, data, layout) => drawn.push([data, layout.title.text]) };
  const fig = {
    sliders: [{ label: 'Alpha', values: [0, 0.05], labels: ['0%', '5%'], index: 1 },
              { label: 'Beta', values: [1, 2], index: 0 }],
    frames: { '1,0': { data: ['a'], title: 'A' }, '1,1': { data: ['b'], title: 'B' }, '0,1': { data: ['c'], title: 'C' } },
  };
  const box = el('div');
  const pos = addSliders(box, el('div'), fig, { title: { text: 'start' } }, P);
  assert.deepEqual(pos, [1, 0]);
  const [alpha, beta] = box.children[0].children.map((row) => row.children[1]);
  beta.value = '1'; beta.listeners.input();
  assert.deepEqual(drawn.at(-1), [['b'], 'B']);
  alpha.value = '0'; alpha.listeners.input();
  assert.deepEqual(drawn.at(-1), [['c'], 'C']);
  assert.equal(box.children[0].children[0].children[2].textContent, '0%');
  delete globalThis.document;
});
