import test from 'node:test';
import assert from 'node:assert/strict';
import { complete, parseCompletion, providerSettings } from '../provider.js';

test('HTTPS endpoint normalization never accepts embedded credentials or URL payloads', () => {
  assert.equal(providerSettings('https://api.deepseek.com/', 'deepseek-flash', '').endpoint, 'https://api.deepseek.com/chat/completions');
  assert.equal(providerSettings('https://model.example/v1', 'compatible-model', '').endpoint, 'https://model.example/v1/chat/completions');
  assert.equal(providerSettings('https://model.example/v1/chat/completions', 'model', '').endpoint, 'https://model.example/v1/chat/completions');
  for (const url of ['http://model.example', 'https://name:password@model.example', 'https://model.example/?token=sensitive', 'https://model.example/#key', 'https://model.example\\path', 'https://model.example bad', 'javascript:alert(1)']) assert.throws(() => providerSettings(url, 'model', ''));
  assert.throws(() => providerSettings('https://model.example', 'model\nname', ''));
  assert.throws(() => providerSettings('https://model.example', 'model', 'secret\nvalue'));
});

test('completion parser uses content JSON and bounded integer usage only', () => {
  const data = { title: 'GPU', nodes: [{ id: 'n1' }] };
  const result = parseCompletion(JSON.stringify({ choices: [{ finish_reason: 'stop', message: { content: JSON.stringify(data), reasoning_content: 'not a structure' } }], usage: { total_tokens: 8, password: 'bad', completion_tokens: -1, prompt_tokens: false } }), 'model');
  assert.deepEqual(result, { data, usage: { total_tokens: 8 }, model: 'model' });
  for (const content of ['not JSON', '{}', '[]', 'null']) assert.throws(() => parseCompletion(JSON.stringify({ choices: [{ message: { content } }] }), 'model'));
  assert.throws(() => parseCompletion(JSON.stringify({ choices: [{ finish_reason: 'length', message: { content: '{"title":"GPU"}' } }] }), 'model'), /上限/);
});

test('BYOK request is sent to configured host without redirects, cookies or vendor fields on compatible endpoint', async () => {
  const original = globalThis.fetch;
  try {
    const settings = providerSettings('https://model.example/v1', 'model', 'example-test-key');
    let request;
    globalThis.fetch = async (url, options) => { request = { url, options }; return new Response(JSON.stringify({ choices: [{ message: { content: '{"title":"GPU"}' } }] }), { status: 200 }); };
    await complete([{ role: 'user', content: 'GPU' }], settings, new AbortController().signal);
    assert.equal(request.url, settings.endpoint);
    assert.equal(request.options.redirect, 'error'); assert.equal(request.options.credentials, 'omit'); assert.equal(request.options.referrerPolicy, 'no-referrer');
    const body = JSON.parse(request.options.body); assert.equal(body.model, 'model'); assert.equal(body.thinking, undefined); assert.equal(body.response_format.type, 'json_object');
    assert.equal(request.options.headers.Authorization, 'Bearer example-test-key');
  } finally { globalThis.fetch = original; }
});

test('HTTP and transport failures never expose upstream body or error text', async () => {
  const original = globalThis.fetch;
  try {
    const settings = providerSettings('https://api.deepseek.com', 'deepseek-flash', 'example-test-key');
    for (const status of [400, 401, 402, 403, 404, 429, 500]) {
      globalThis.fetch = async () => new Response('upstream-secret-example-test-key', { status });
      await assert.rejects(complete([], settings), (error) => !error.message.includes('example-test-key') && !error.message.includes('upstream-secret'));
    }
    globalThis.fetch = async () => { throw new Error('upstream-secret-example-test-key'); };
    await assert.rejects(complete([], settings), (error) => !error.message.includes('example-test-key'));
    globalThis.fetch = async () => new Response('x'.repeat(2 * 1024 * 1024 + 1), { status: 200 });
    await assert.rejects(complete([], settings), /过大/);
  } finally { globalThis.fetch = original; }
});

test('cancelled request is distinguishable from a service failure', async () => {
  const original = globalThis.fetch;
  try {
    const controller = new AbortController(); controller.abort();
    globalThis.fetch = async () => { throw new TypeError('network-secret'); };
    await assert.rejects(complete([], providerSettings('https://api.deepseek.com', 'deepseek-flash', 'example-test-key'), controller.signal), (error) => error.name === 'AbortError' && !error.message.includes('network-secret'));
  } finally { globalThis.fetch = original; }
});
