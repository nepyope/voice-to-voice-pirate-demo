import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import vm from 'node:vm';
import { buildDirectWsUrl } from '../ws/connection-url.js';
import { base64FromArrayBuffer, base64ToBytes, extractResponseTranscript } from '../ws/codec.js';

test('same-origin proxy uses the browser host and TLS scheme', () => {
  assert.equal(buildDirectWsUrl('/api/realtime', 'https://captain.example:8443/'), 'wss://captain.example:8443/api/realtime');
  assert.equal(buildDirectWsUrl('/api/realtime', 'http://localhost:7860/'), 'ws://localhost:7860/api/realtime');
});
test('direct URL preserves path and query, bare host gets realtime path', () => {
  assert.equal(buildDirectWsUrl('localhost:8765'), 'ws://localhost:8765/v1/realtime');
  assert.equal(buildDirectWsUrl('https://host.example/v1/realtime?token=abc'), 'wss://host.example/v1/realtime?token=abc');
});
test('large PCM chunks round-trip without clipping or byte-order changes', () => {
  const pcm = new Int16Array(96000);
  for (let i = 0; i < pcm.length; i++) pcm[i] = (i % 65536) - 32768;
  assert.deepEqual(base64ToBytes(base64FromArrayBuffer(pcm.buffer)), new Uint8Array(pcm.buffer));
});
test('interrupted response preserves the final transcript', () => {
  assert.equal(extractResponseTranscript({output: [{content: [{transcript: ' À bord! '}, {text: 'Bonjour.'}]}]}), 'À bord! Bonjour.');
  assert.equal(extractResponseTranscript({}), '');
});
for (const inputRate of [24000, 44100, 48000]) {
  test(`microphone ${inputRate} Hz becomes 40ms mono 24k PCM16 frames`, () => {
    const messages = [];
    let Processor;
    const context = vm.createContext({
      sampleRate: inputRate,
      AudioWorkletProcessor: class { constructor() { this.port = {postMessage: data => messages.push(data)}; } },
      registerProcessor: (_name, cls) => { Processor = cls; },
    });
    vm.runInContext(fs.readFileSync(new URL('../worklets/mic-capture.js', import.meta.url), 'utf8'), context);
    const processor = new Processor({processorOptions: {targetRate: 24000, chunkMs: 40}});
    processor.process([[new Float32Array(inputRate / 10).fill(0.5)]]);
    const audio = messages.filter(m => typeof m.byteLength === 'number');
    assert.equal(audio.length, 2);
    assert.equal(audio[0].byteLength, 1920);
    const view = new DataView(audio[0]);
    assert.ok(Math.abs(view.getInt16(0, true) - 16384) <= 1);
  });
}
