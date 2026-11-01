import test from 'node:test';
import assert from 'node:assert/strict';
import { createIdleDeadline, MAX_SEGMENT_MS } from '../../static/idle-deadline.js';

function clock() {
  let t = 1000;
  return { now: () => t, tick: (ms) => { t += ms; } };
}

test('expires idleMs after it is armed', () => {
  const c = clock();
  const d = createIdleDeadline({ idleMs: 45000, now: c.now });
  assert.equal(d.due(), null);           // not armed: never due
  d.arm();
  c.tick(44999); assert.equal(d.due(), null);
  c.tick(1); assert.equal(d.due(), 'idle');
});

test('misfires and empty transcripts do not postpone expiry', () => {
  const c = clock();
  const d = createIdleDeadline({ idleMs: 45000, now: c.now });
  d.arm();
  for (let i = 0; i < 9; i++) {
    c.tick(5000);
    d.speechStart(); c.tick(300); d.speechEnd();   // a misfire (noise burst)
    d.arm();                                        // listening resumes after an empty transcript
  }
  assert.equal(d.due(), 'idle');                    // 9 * 5.3 s > 45 s
});

test('speech start does not clear the deadline', () => {
  const c = clock();
  const d = createIdleDeadline({ idleMs: 10000, now: c.now });
  d.arm();
  c.tick(9000); d.speechStart();
  c.tick(1000);
  assert.equal(d.due(), 'idle');
});

test('a sent transcript starts a new deadline at the next arm', () => {
  const c = clock();
  const d = createIdleDeadline({ idleMs: 45000, now: c.now });
  d.arm();
  c.tick(40000);
  d.transcriptSent();
  assert.equal(d.due(), null);           // disarmed while the tutor answers
  c.tick(30000);                         // the tutor's turn
  d.arm();                               // listening after the turn
  c.tick(44000); assert.equal(d.due(), null);
  c.tick(1000); assert.equal(d.due(), 'idle');
});

test('disarm clears the deadline and any segment', () => {
  const c = clock();
  const d = createIdleDeadline({ idleMs: 1000, now: c.now });
  d.arm(); d.speechStart(); d.disarm();
  c.tick(120000);
  assert.equal(d.due(), null);
  assert.equal(d.msToNext(), null);
});

test('a 60 s speech segment is capped', () => {
  assert.equal(MAX_SEGMENT_MS, 60000);
  const c = clock();
  const d = createIdleDeadline({ idleMs: 600000, now: c.now });
  d.arm();
  c.tick(1000); d.speechStart();
  c.tick(59999); assert.equal(d.due(), null);
  assert.equal(d.msToNext(), 1);
  c.tick(1); assert.equal(d.due(), 'segment');
  d.speechEnd(); assert.equal(d.due(), null);
});

test('msToNext is the nearer of the deadline and the segment cap', () => {
  const c = clock();
  const d = createIdleDeadline({ idleMs: 45000, now: c.now });
  d.arm();
  assert.equal(d.msToNext(), 45000);
  c.tick(5000); d.speechStart();
  assert.equal(d.msToNext(), 40000);
  c.tick(50000);
  assert.equal(d.msToNext(), 0);         // overdue: check now
});
