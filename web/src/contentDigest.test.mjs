import {test} from 'node:test';
import assert from 'node:assert/strict';
import {createHash,randomBytes,webcrypto} from 'node:crypto';
import {contentDigest} from './contentDigest.ts';

test('HTTP fallback matches standard SHA-256 across UTF-8 and block/padding boundaries',async()=>{
  const original=Object.getOwnPropertyDescriptor(globalThis,'crypto');
  Object.defineProperty(globalThis,'crypto',{value:{},configurable:true});
  try {
    const texts=['','abc','川序 😀\u0000','a'.repeat(1000000),JSON.stringify({reason:'核对原请求',requests:2})];
    for(const n of [1,55,56,57,63,64,65,119,120,127,128,129,1024])texts.push(randomBytes(n).toString('hex').slice(0,n));
    for(const text of texts)assert.equal(await contentDigest(text),createHash('sha256').update(text).digest('hex'));
    await assert.rejects(contentDigest('a'.repeat(16*1024*1024+1)),/digest size limit/);
  } finally {
    if(original)Object.defineProperty(globalThis,'crypto',original);else delete globalThis.crypto;
  }
});

test('native SubtleCrypto retains the same digest and its receiver',async()=>{
  const original=Object.getOwnPropertyDescriptor(globalThis,'crypto');
  Object.defineProperty(globalThis,'crypto',{value:webcrypto,configurable:true});
  try {assert.equal(await contentDigest('川序'),createHash('sha256').update('川序').digest('hex'));}
  finally {if(original)Object.defineProperty(globalThis,'crypto',original);else delete globalThis.crypto;}
});
