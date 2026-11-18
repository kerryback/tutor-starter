import { test } from 'node:test';
import assert from 'node:assert/strict';
import { micMessage } from '../../static/voice.js';

const blocked = Object.assign(new Error('Permission denied'), { name: 'NotAllowedError' });
const CHROME_IOS = 'Mozilla/5.0 (iPhone; CPU iPhone OS 18_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) CriOS/131.0 Mobile/15E148 Safari/604.1';
const SAFARI_IPAD = 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/18.0 Safari/605.1.15';

test('a blocked microphone on iOS names the browser to fix in Settings', () => {
  const m = micMessage(blocked, CHROME_IOS, 5);
  assert.match(m, /Settings app, find Chrome/);
  assert.match(m, /reload this page/);
  assert.match(micMessage(blocked, SAFARI_IPAD, 5), /find Safari/);
});

test('a blocked microphone elsewhere points to the site settings', () => {
  assert.match(micMessage(blocked, 'Mozilla/5.0 (Macintosh) Chrome/131', 0), /for this site in your browser's settings/);
});

test('other failures say what happened', () => {
  assert.equal(micMessage(Object.assign(new Error('x'), { name: 'NotFoundError' }), '', 0), 'No microphone was found.');
  assert.equal(micMessage(new Error('Busy.'), '', 0), 'Could not use the microphone (Busy).');
});

test('a blocked microphone on Android points to the site permissions, then the app settings', () => {
  const m = micMessage(blocked, 'Mozilla/5.0 (Linux; Android 14; Pixel 8) AppleWebKit/537.36 Chrome/131 Mobile Safari/537.36', 5);
  assert.match(m, /icon to the left of the web address/);
  assert.match(m, /Settings app, tap Apps/);
});
