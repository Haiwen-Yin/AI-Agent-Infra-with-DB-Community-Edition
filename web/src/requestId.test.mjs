import test from 'node:test';
import assert from 'node:assert/strict';
import { newRequestId } from './requestId.ts';

const descriptor = Object.getOwnPropertyDescriptor(globalThis, 'crypto');
function withCrypto(value, run) {
  Object.defineProperty(globalThis, 'crypto', {configurable: true, value});
  try { run(); } finally { Object.defineProperty(globalThis, 'crypto', descriptor); }
}
test('uses the native method with its original receiver', () => {
  const source = {randomUUID() {assert.equal(this, source); return 'native-id';}};
  withCrypto(source, () => assert.equal(newRequestId(), 'native-id'));
});
test('HTTP fallback produces an RFC UUID v4 from secure random bytes', () => {
  const source = {getRandomValues(bytes) {assert.equal(this, source); bytes.fill(255); return bytes;}};
  withCrypto(source, () => assert.equal(newRequestId(), 'ffffffff-ffff-4fff-bfff-ffffffffffff'));
});
test('fallback preserves fresh randomness and does not use Math.random', () => {
  const original = Math.random;
  Math.random = () => {throw new Error('weak randomness used');};
  try {
    let next = 0;
    withCrypto({getRandomValues(bytes) {bytes.fill(next++); return bytes;}}, () => {
      const a = newRequestId(), b = newRequestId();
      assert.match(a, /^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/);
      assert.notEqual(a, b);
    });
  } finally { Math.random = original; }
});
test('missing random capability gives a controlled error', () => {
  for (const source of [undefined, {}]) withCrypto(source, () => assert.throws(newRequestId, /Secure browser randomness is unavailable/));
});
