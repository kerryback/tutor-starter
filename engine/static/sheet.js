// The spreadsheet on the whiteboard: a small grid that takes Excel formulas.
//
// The student opens it with the Sheet button. Formulas use Excel's syntax and
// Excel's functions (NPV, IRR, PMT, FV, PV, RATE, NPER, SUM, AVERAGE, ...),
// evaluated by Formula.js, which follows Excel (its NPV, like Excel's,
// discounts the first value it is given by one period). When the student
// sends a message, the app sends the sheet with it, so the tutor sees the
// formulas and what they show (see sheet_note.py).
//
// The parser and evaluator below are pure, so they can be tested in node:
//   evaluate(cells, fns)  {A1: '=NPV(B1,B2:B6)', ...} -> {A1: value, ...}
//   snapshot(cells, values)  the text the tutor gets, or '' for an empty sheet
// A value is a number, a string, or an error string such as '#NAME?'.
// mountSheet() builds the grid in the page.

export const COLS = 8;    // A to H
export const ROWS = 20;
const FORMULAJS = 'https://cdn.jsdelivr.net/npm/@formulajs/formulajs@4.4.9/lib/browser/formula.min.js';

export const colName = (i) => String.fromCharCode(65 + i);
export const cellName = (c, r) => colName(c) + (r + 1);

const isErr = (v) => typeof v === 'string' && v.startsWith('#');

class SheetError extends Error {
  constructor(code) { super(code); this.code = code; }
}

// A cell's own content when it is not a formula: "", a number ("5%", "$1,000",
// "-100") or text.
export function literal(raw) {
  const s = String(raw ?? '').trim();
  if (s === '') return null;
  const m = s.replace(/[$,\s]/g, '').match(/^([-+]?(?:\d+\.?\d*|\.\d+)(?:e[-+]?\d+)?)(%?)$/i);
  if (m) return Number(m[1]) / (m[2] ? 100 : 1);
  return s;
}

// --- tokens ------------------------------------------------------------------

const TOKEN = /\s*(?:(\d+\.?\d*(?:e[-+]?\d+)?|\.\d+(?:e[-+]?\d+)?)|(\$?[A-Za-z]{1,2}\$?\d+(?::\$?[A-Za-z]{1,2}\$?\d+)?)(?![A-Za-z0-9_.(])|([A-Za-z_][A-Za-z0-9_.]*)|("[^"]*")|(<>|<=|>=|[-+*/^%(),:<>=&]))/y;

export function tokenize(src) {
  const out = [];
  TOKEN.lastIndex = 0;
  let i = 0;
  while (i < src.length) {
    if (/^\s*$/.test(src.slice(i))) break;
    TOKEN.lastIndex = i;
    const m = TOKEN.exec(src);
    if (!m) throw new SheetError('#ERROR!');
    if (m[1] !== undefined) out.push({ t: 'num', v: Number(m[1]) });
    else if (m[2] !== undefined) out.push({ t: 'ref', v: m[2].replace(/\$/g, '').toUpperCase() });
    else if (m[3] !== undefined) out.push({ t: 'name', v: m[3].toUpperCase() });
    else if (m[4] !== undefined) out.push({ t: 'str', v: m[4].slice(1, -1) });
    else out.push({ t: 'op', v: m[5] });
    i = TOKEN.lastIndex;
  }
  return out;
}

// --- parser: Excel precedence, lowest first ----------------------------------
//   comparison (= <> < > <= >=), & , + -, * /, ^, unary minus, postfix %
// As in Excel, unary minus binds tighter than ^: -2^2 is 4.

export function parse(src) {
  const toks = tokenize(src);
  let p = 0;
  const peek = () => toks[p];
  const isOp = (...ops) => peek() && peek().t === 'op' && ops.includes(peek().v);
  const take = () => toks[p++];
  const expect = (v) => { if (!isOp(v)) throw new SheetError('#ERROR!'); take(); };

  const binary = (next, ops) => () => {
    let left = next();
    while (isOp(...ops)) { const op = take().v; left = { k: 'bin', op, a: left, b: next() }; }
    return left;
  };
  function unary() {
    if (isOp('-', '+')) { const op = take().v; return { k: 'neg', op, a: unary() }; }
    return postfix();
  }
  function postfix() {
    let e = primary();
    while (isOp('%')) { take(); e = { k: 'pct', a: e }; }
    return e;
  }
  function primary() {
    const tk = take();
    if (!tk) throw new SheetError('#ERROR!');
    if (tk.t === 'num') return { k: 'num', v: tk.v };
    if (tk.t === 'str') return { k: 'str', v: tk.v };
    if (tk.t === 'ref') {
      const [a, b] = tk.v.split(':');
      return b ? { k: 'range', a, b } : { k: 'ref', v: a };
    }
    if (tk.t === 'name') {
      if (tk.v === 'TRUE' || tk.v === 'FALSE') return { k: 'num', v: tk.v === 'TRUE' ? 1 : 0 };
      expect('(');
      const args = [];
      if (!isOp(')')) {
        do { args.push(isOp(',', ')') ? { k: 'blank' } : compare()); } while (isOp(',') && take());
      }
      expect(')');
      return { k: 'call', f: tk.v, args };
    }
    if (tk.v === '(') { const e = compare(); expect(')'); return e; }
    throw new SheetError('#ERROR!');
  }
  const power = binary(unary, ['^']);
  const product = binary(power, ['*', '/']);
  const sum = binary(product, ['+', '-']);
  const concat = binary(sum, ['&']);
  const compare = binary(concat, ['=', '<>', '<', '>', '<=', '>=']);

  const tree = compare();
  if (p !== toks.length) throw new SheetError('#ERROR!');
  return tree;
}

// --- evaluation ----------------------------------------------------------------

function refIndex(name) {
  const m = name.match(/^([A-Z]{1,2})(\d+)$/);
  if (!m) return null;
  const c = m[1].length === 1 ? m[1].charCodeAt(0) - 65 : 99;
  const r = Number(m[2]) - 1;
  return c >= 0 && c < COLS && r >= 0 && r < ROWS ? [c, r] : null;
}

export function evaluate(cells, fns) {
  const values = {}, state = {};   // state: 'busy' while a cell is evaluated

  function cell(name) {
    if (!refIndex(name)) throw new SheetError('#REF!');
    if (state[name] === 'done') return values[name];
    if (state[name] === 'busy') throw new SheetError('#CIRC!');
    state[name] = 'busy';
    let v;
    const raw = String(cells[name] ?? '').trim();
    try {
      v = raw.startsWith('=') ? scalar(node(parse(raw.slice(1)))) : literal(raw);
    } catch (e) {
      v = e instanceof SheetError ? e.code : '#ERROR!';
    }
    if (typeof v === 'number' && !Number.isFinite(v)) v = '#NUM!';
    values[name] = v; state[name] = 'done';
    return v;
  }

  function range(a, b) {
    const p = refIndex(a), q = refIndex(b);
    if (!p || !q) throw new SheetError('#REF!');
    const out = [];
    for (let r = Math.min(p[1], q[1]); r <= Math.max(p[1], q[1]); r++)
      for (let c = Math.min(p[0], q[0]); c <= Math.max(p[0], q[0]); c++) {
        const v = cell(cellName(c, r));
        if (isErr(v)) throw new SheetError(v);
        if (v !== null) out.push(v);   // Excel's functions skip empty cells in a range
      }
    return out;
  }

  const num = (v) => {
    if (isErr(v)) throw new SheetError(v);
    if (v === null) return 0;
    if (typeof v === 'number') return v;
    const n = literal(v);
    if (typeof n === 'number') return n;
    throw new SheetError('#VALUE!');
  };
  const scalar = (v) => {
    if (Array.isArray(v)) throw new SheetError('#VALUE!');
    return v === null ? 0 : v;
  };

  function node(e) {
    switch (e.k) {
      case 'num': case 'str': return e.v;
      case 'blank': return null;
      case 'ref': { const v = cell(e.v); if (isErr(v)) throw new SheetError(v); return v; }
      case 'range': return range(e.a, e.b);
      case 'pct': return num(scalar(node(e.a))) / 100;
      case 'neg': { const x = num(scalar(node(e.a))); return e.op === '-' ? -x : x; }
      case 'bin': {
        const a = scalar(node(e.a)), b = scalar(node(e.b));
        if (e.op === '&') return String(a ?? '') + String(b ?? '');
        if (['=', '<>', '<', '>', '<=', '>='].includes(e.op)) {
          const [x, y] = typeof a === 'number' || typeof b === 'number' ? [num(a), num(b)] : [a, b];
          return { '=': x === y, '<>': x !== y, '<': x < y, '>': x > y, '<=': x <= y, '>=': x >= y }[e.op] ? 1 : 0;
        }
        const x = num(a), y = num(b);
        if (e.op === '/' && y === 0) throw new SheetError('#DIV/0!');
        return { '+': x + y, '-': x - y, '*': x * y, '/': x / y, '^': x ** y }[e.op];
      }
      case 'call': {
        const f = fns && fns[e.f];
        if (typeof f !== 'function') throw new SheetError('#NAME?');
        const args = e.args.map((a) => {
          const v = node(a);
          if (isErr(v)) throw new SheetError(v);
          return v;
        });
        let v;
        try { v = f(...args); } catch { throw new SheetError('#VALUE!'); }
        if (v instanceof Error) throw new SheetError(v.message && v.message.startsWith('#') ? v.message : '#VALUE!');
        if (typeof v === 'boolean') return v ? 1 : 0;
        if (Array.isArray(v)) throw new SheetError('#VALUE!');
        return v ?? null;
      }
    }
    throw new SheetError('#ERROR!');
  }

  for (const name of Object.keys(cells)) cell(name);
  return values;
}

// How a value shows in a cell and in the tutor's copy: Excel's General format,
// near enough (up to 10 significant digits).
export function show(v) {
  if (v === null || v === undefined) return '';
  if (typeof v !== 'number') return String(v);
  if (Number.isInteger(v)) return String(v);
  return String(Number(v.toPrecision(10)));
}

// How a value shows in its cell, which is narrower: up to 6 significant
// digits, and a percent the student typed stays a percent.
export function cellText(v, raw = '') {
  if (typeof v !== 'number') return show(v);
  const s = String(raw).trim();
  if (!s.startsWith('=') && s.endsWith('%')) return String(Number((v * 100).toPrecision(6))) + '%';
  if (Number.isInteger(v) || Math.abs(v) >= 1e6) return show(v);
  return String(Number(v.toPrecision(6)));
}

// The sheet as the tutor gets it: one line per filled cell, in reading order.
export function snapshot(cells, values) {
  const lines = [];
  for (let r = 0; r < ROWS; r++)
    for (let c = 0; c < COLS; c++) {
      const name = cellName(c, r);
      const raw = String(cells[name] ?? '').trim();
      if (!raw) continue;
      lines.push(raw.startsWith('=') ? `${name}: ${raw}  → ${show(values[name])}` : `${name}: ${raw}`);
    }
  return lines.join('\n');
}

// --- the grid in the page ------------------------------------------------------

let loading = null;
function loadFormulas() {
  if (globalThis.formulajs) return Promise.resolve(globalThis.formulajs);
  if (!loading) loading = new Promise((resolve, reject) => {
    const s = document.createElement('script');
    s.src = FORMULAJS;
    s.onload = () => resolve(globalThis.formulajs);
    s.onerror = () => { loading = null; reject(new Error('could not load the spreadsheet functions')); };
    document.head.appendChild(s);
  });
  return loading;
}

// Build the grid inside el. onInput is called on every edit (the idle timer
// uses it). Returns {open(), close(), isOpen(), pending(), sent()}:
// pending() is the snapshot if the sheet changed since sent(), else null.
export function mountSheet(el, { onInput = () => {} } = {}) {
  const cells = {};
  let values = {}, fns = null, dirty = false;
  el.innerHTML = '';
  const bar = document.createElement('div'); bar.className = 'sheetbar';
  const title = document.createElement('span');
  title.textContent = 'Spreadsheet: type a number, or a formula that starts with =';
  const clear = document.createElement('button'); clear.type = 'button'; clear.textContent = 'Clear';
  bar.append(title, clear);
  const wrap = document.createElement('div'); wrap.className = 'sheetgrid';
  const table = document.createElement('table');
  const head = table.createTHead().insertRow();
  head.appendChild(document.createElement('th'));
  for (let c = 0; c < COLS; c++) { const th = document.createElement('th'); th.textContent = colName(c); head.appendChild(th); }
  const body = table.createTBody();
  const inputs = {};
  for (let r = 0; r < ROWS; r++) {
    const tr = body.insertRow();
    const th = document.createElement('th'); th.textContent = r + 1; tr.appendChild(th);
    for (let c = 0; c < COLS; c++) {
      const name = cellName(c, r);
      const input = document.createElement('input');
      input.setAttribute('aria-label', name);
      input.autocomplete = 'off'; input.spellcheck = false;
      input.setAttribute('autocapitalize', 'off');
      input.addEventListener('focus', () => { input.value = cells[name] ?? ''; input.select(); });
      input.addEventListener('input', () => { cells[name] = input.value; dirty = true; onInput(); });
      input.addEventListener('blur', () => { cells[name] = input.value; recalc(); });
      input.addEventListener('keydown', (e) => {
        if (e.key === 'Enter') {
          e.preventDefault();
          const next = inputs[cellName(c, Math.min(r + (e.shiftKey ? -1 : 1), ROWS - 1))]
            || inputs[cellName(c, Math.max(r - 1, 0))];
          (next && next !== input ? next : input).focus();
          if (next === input) input.blur();
        }
      });
      inputs[name] = input;
      tr.insertCell().appendChild(input);
    }
  }
  wrap.appendChild(table);
  el.append(bar, wrap);

  function recalc() {
    if (!fns && Object.values(cells).some((v) => String(v).trim().startsWith('='))) {
      loadFormulas().then((f) => { fns = f; recalc(); }).catch(() => {});
    }
    values = evaluate(cells, fns || {});
    for (const [name, input] of Object.entries(inputs)) {
      if (document.activeElement === input) continue;
      const v = values[name];
      input.value = v === undefined ? '' : cellText(v, cells[name]);
      input.classList.toggle('num', typeof v === 'number');
      input.classList.toggle('err', isErr(v));
    }
  }
  clear.addEventListener('click', () => {
    for (const k of Object.keys(cells)) delete cells[k];
    dirty = true; recalc(); onInput();
  });

  return {
    open() { el.hidden = false; loadFormulas().then((f) => { fns = f; recalc(); }).catch(() => {}); },
    close() { el.hidden = true; },
    isOpen: () => !el.hidden,
    pending() {
      if (!dirty) return null;
      if (document.activeElement && Object.values(inputs).includes(document.activeElement)) {
        const name = document.activeElement.getAttribute('aria-label');
        cells[name] = document.activeElement.value;
      }
      values = evaluate(cells, fns || {});
      return snapshot(cells, values);
    },
    sent() { dirty = false; },
  };
}
