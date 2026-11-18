import test from 'node:test';
import assert from 'node:assert/strict';
import { literal, parse, evaluate, snapshot, show, cellText } from '../../static/sheet.js';

// Stand-ins with Excel's behavior; the page uses Formula.js.
const fns = {
  SUM: (...a) => a.flat().reduce((s, x) => s + x, 0),
  NPV: (r, ...a) => a.flat().reduce((s, x, i) => s + x / (1 + r) ** (i + 1), 0),
  ROUND: (x, d) => Math.round(x * 10 ** d) / 10 ** d,
  BAD: () => Object.assign(new Error('#NUM!')),
};
const ev = (cells) => evaluate(cells, fns);

test('literals: numbers, percents, dollars and text', () => {
  assert.equal(literal('5%'), 0.05);
  assert.equal(literal('$1,000'), 1000);
  assert.equal(literal('-100'), -100);
  assert.equal(literal(''), null);
  assert.equal(literal('Cash flow'), 'Cash flow');
});

test('arithmetic follows Excel precedence', () => {
  const v = ev({ A1: '=2+3*4', A2: '=-2^2', A3: '=(1+5%)^10', A4: '=10/4%', A5: '=1/0' });
  assert.equal(v.A1, 14);
  assert.equal(v.A2, 4);                 // unary minus binds tighter than ^, as in Excel
  assert.equal(show(v.A3), '1.628894627');
  assert.equal(v.A4, 250);
  assert.equal(v.A5, '#DIV/0!');
});

test('references, ranges and functions; empty cells in a range are skipped', () => {
  const v = ev({ A1: '10%', B1: '-100', B2: '20', B3: '', B4: '30',
    C1: '=B1+NPV(A1,B2:B4)', C2: '=SUM(B1:B4)', C3: '=npv(a1, b2, b4)' });
  assert.equal(show(v.C1), String(Number((-100 + 20 / 1.1 + 30 / 1.21).toPrecision(10))));
  assert.equal(v.C2, -50);
  assert.equal(v.C3, v.C1 + 100);         // lower case works; NPV's first value is one period out
});

test('errors: unknown function, circular reference, bad syntax, out of the grid', () => {
  const v = ev({ A1: '=FOO(1)', A2: '=A3', A3: '=A2', A4: '=1+', A5: '=Z99', A6: '=BAD()', A7: '=A1+1' });
  assert.equal(v.A1, '#NAME?');
  assert.equal(v.A2, '#CIRC!');
  assert.equal(v.A4, '#ERROR!');
  assert.equal(v.A5, '#REF!');
  assert.equal(v.A6, '#NUM!');
  assert.equal(v.A7, '#NAME?');          // an error flows through
});

test('the tutor gets formulas with their values, in reading order', () => {
  const cells = { B1: '=ROUND(A1*2,1)', A1: '1.26', A2: '' };
  assert.equal(snapshot(cells, ev(cells)), 'A1: 1.26\nB1: =ROUND(A1*2,1)  → 2.5');
  assert.equal(snapshot({}, {}), '');
});

test('a parse tree for a function call with ranges', () => {
  assert.deepEqual(parse('NPV(A1,B2:B4)'),
    { k: 'call', f: 'NPV', args: [{ k: 'ref', v: 'A1' }, { k: 'range', a: 'B2', b: 'B4' }] });
});

test('cells show up to 6 significant digits; typed percents stay percents', () => {
  assert.equal(cellText(14.0706981018, '=B2+NPV(B1,B3:B7)'), '14.0707');
  assert.equal(cellText(0.1533048965, '=IRR(B2:B7)'), '0.153305');
  assert.equal(cellText(0.1, '10%'), '10%');
  assert.equal(cellText(0.075, '7.5%'), '7.5%');
  assert.equal(cellText(-100, '-100'), '-100');
  assert.equal(cellText('#NAME?', '=FOO()'), '#NAME?');
});
