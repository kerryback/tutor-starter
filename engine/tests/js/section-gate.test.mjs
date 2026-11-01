import test from 'node:test';
import assert from 'node:assert/strict';
import { lastDueSection } from '../../static/voice.js';

test('a new section waits until the speech queued before it is spoken', () => {
  // The intro (gate 0) queued 5 clips; the next reply's heading came with 5 queued.
  assert.equal(lastDueSection([0, 5], 2), 0);
  assert.equal(lastDueSection([0, 5], 5), 1);
});

test('the first section is always due, and no sections gives -1', () => {
  assert.equal(lastDueSection([3], 0), 0);
  assert.equal(lastDueSection([], 0), -1);
});

test('several waiting sections open one at a time', () => {
  assert.equal(lastDueSection([0, 2, 4, 4], 3), 1);
  assert.equal(lastDueSection([0, 2, 4, 4], 4), 3);
});
