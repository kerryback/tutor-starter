import test from 'node:test';
import assert from 'node:assert/strict';
import { encodeWav } from '../../static/wav.js';

const text = (b, i, n) => String.fromCharCode(...b.slice(i, i + n));

test('the header describes 16 kHz mono 16-bit PCM', () => {
  const b = encodeWav(new Float32Array(10), 16000);
  const v = new DataView(b.buffer, b.byteOffset, b.byteLength);
  assert.equal(text(b, 0, 4), 'RIFF');
  assert.equal(v.getUint32(4, true), 36 + 20);
  assert.equal(text(b, 8, 4), 'WAVE');
  assert.equal(text(b, 12, 4), 'fmt ');
  assert.equal(v.getUint32(16, true), 16);       // fmt chunk size
  assert.equal(v.getUint16(20, true), 1);        // PCM
  assert.equal(v.getUint16(22, true), 1);        // mono
  assert.equal(v.getUint32(24, true), 16000);    // sample rate
  assert.equal(v.getUint32(28, true), 32000);    // byte rate
  assert.equal(v.getUint16(32, true), 2);        // block align
  assert.equal(v.getUint16(34, true), 16);       // bits per sample
  assert.equal(text(b, 36, 4), 'data');
  assert.equal(v.getUint32(40, true), 20);
});

test('the length is 44 bytes plus 2 per sample', () => {
  assert.equal(encodeWav(new Float32Array(0), 16000).length, 44);
  assert.equal(encodeWav(new Float32Array(16000), 16000).length, 44 + 32000);
});

test('samples are little-endian 16-bit, and values outside -1..1 are clipped', () => {
  const b = encodeWav(Float32Array.from([0, 0.5, -0.5, 1, -1, 3, -3, NaN]), 16000);
  const v = new DataView(b.buffer, b.byteOffset, b.byteLength);
  const s = [...Array(8)].map((_, i) => v.getInt16(44 + 2 * i, true));
  assert.deepEqual(s, [0, 16383, -16384, 32767, -32768, 32767, -32768, 0]);
});

test('another sample rate sets the rate fields', () => {
  const b = encodeWav(new Float32Array(1), 48000);
  const v = new DataView(b.buffer, b.byteOffset, b.byteLength);
  assert.equal(v.getUint32(24, true), 48000);
  assert.equal(v.getUint32(28, true), 96000);
});
