'use strict';
const fs = require('node:fs');
const path = require('node:path');
const test = require('node:test');
const assert = require('node:assert/strict');
const native = require('./native_reference');
const custom = require('./sample_lut_reference');
const fixturePath = path.join(__dirname, 'native_oracle_evidence/fixtures.json');
const fixtures = fs.existsSync(fixturePath) ? JSON.parse(fs.readFileSync(fixturePath)) : null;
const fixtureTest = (name, fn) => test(name, {
  skip: fixtures ? false : 'optional ARM64 oracle fixtures are excluded from the source-only tree',
}, fn);
const buf = v => Buffer.from(v.buffer, v.byteOffset, v.byteLength);
const floats = encoded => {
  const b = Buffer.from(encoded, 'base64');
  return Float32Array.from({ length: b.length / 4 }, (_, i) => b.readFloatLE(i * 4));
};

fixtureTest('replacement mean reproduces all four original ARM64 sampling fixtures', () => {
  const plan = custom.preparePlan({ enabled: true, sampler: 'mean' });
  for (const c of fixtures.cases.filter(c => c.stage === 'sample')) {
    const result = custom.samplePair(Buffer.from(c.raw, 'base64'), c.stride, plan);
    const expected = Buffer.from(c.after.buffers, 'base64').subarray(c.selector * 0x1200, (c.selector + 1) * 0x1200);
    assert.deepEqual(buf(result), expected);
  }
});

fixtureTest('native-compatible custom LUT reproduces both original ARM64 mapping fixtures', () => {
  for (const c of fixtures.cases.filter(c => c.stage === 'lut')) {
    const before = floats(c.before).subarray(c.selector * 1152, (c.selector + 1) * 1152);
    const expected = Buffer.from(c.after.buffers, 'base64').subarray(c.selector * 0x1200, (c.selector + 1) * 0x1200);
    assert.deepEqual(buf(custom.mapPair(before, native.NATIVE_LUT)), expected);
  }
});

test('peak preserves a white impulse in either eye without lighting another sample cell', () => {
  const raw = Buffer.alloc(1536 * 192);
  const put = (eye, x, y, rgb, alpha = 0) => raw.set([...rgb, alpha], eye * 720 + y * 1536 + x * 4);
  put(0, 7 * 10 + 3, 12 * 6 + 2, [255, 255, 255]);
  put(1, 17 * 10 + 9, 31 * 6 + 5, [255, 255, 255]);
  put(0, 0, 0, [0, 0, 0], 255); // alpha must not contribute
  const plans = ['mean', 'peak', 'blend'].map(sampler => custom.preparePlan({ enabled: true, sampler, peakWeight: 0.5 }));
  const [mean, peak, blend] = plans.map(plan => custom.samplePair(raw, 1536, plan));
  for (let i = 0; i < 1152; i++) {
    const lit = i === 12 * 18 + 7 || i === 1151;
    assert.equal(mean[i], lit ? 4.25 : 0);
    assert.equal(peak[i], lit ? 255 : 0);
    assert.equal(blend[i], lit ? 129.625 : 0);
  }
});

test('blend endpoints match native and peak exactly including colored checkerboards', () => {
  const raw = Buffer.alloc(1440 * 192);
  for (let p = 0; p < raw.length; p += 4) {
    const pixel = p / 4;
    raw[p + ((pixel + Math.floor(pixel / 360)) % 3)] = 255;
  }
  const run = (sampler, peakWeight = 0) => custom.samplePair(raw, 1440, custom.preparePlan({ enabled: true, sampler, peakWeight }));
  assert.deepEqual(buf(run('mean')), buf(run('blend', 0)));
  assert.deepEqual(buf(run('peak')), buf(run('blend', 1)));
  assert.equal(run('mean')[0], 85); // max(channel sums), not mean(pixel maxima)
  assert.equal(run('peak')[0], 255);
});

test('uniform colors remain invariant under all sampling strategies', () => {
  const raw = Buffer.alloc(1472 * 192);
  for (const rgb of [[0, 0, 0], [255, 255, 255], [10, 100, 23], [128, 0, 0]]) {
    for (let p = 0; p < raw.length; p += 4) raw.set([...rgb, 255], p);
    for (const sampler of ['mean', 'peak', 'blend']) {
      const matrix = custom.samplePair(raw, 1472, custom.preparePlan({ enabled: true, sampler, peakWeight: 0.3 }));
      assert.ok(matrix.every(v => v === Math.max(...rgb)));
    }
  }
});

fixtureTest('curve generation matches original Android powf fixtures and postpones saturation', () => {
  for (const c of fixtures.cases.filter(c => c.stage === 'lut_generate')) {
    assert.deepEqual(buf(Uint16Array.from(custom.curve(c.threshold, c.gamma))), Buffer.from(c.after, 'base64'));
  }
  const input = Float32Array.from({ length: 1152 }, (_, i) => [0, 20, 50, 100, 255, 8190][i % 6]);
  const stock = custom.mapPair(input, native.NATIVE_LUT);
  const extended = custom.mapPair(input, custom.curve(255, 1));
  assert.equal(stock[1], 8190);
  assert.ok(extended[1] < extended[2] && extended[2] < extended[3] && extended[3] < extended[4]);
  assert.equal(extended[0], 0);
  assert.equal(extended[4], 8190);
  assert.equal(extended[5], 8190);
});

test('invalid tables and input are rejected before writing any cell', () => {
  const pair = new Float32Array(1152).fill(10);
  const original = buf(pair).toString('base64');
  for (const lut of [[0], [0, 100, 99, 8190], [0, 8200, 8190], [0, NaN, 8190], [1, 8190], [0, 255], [0, 1.5, 8190]]) {
    assert.throws(() => custom.mapPair(pair, lut));
    assert.equal(buf(pair).toString('base64'), original);
  }
  for (const invalid of [-1, NaN, Infinity]) {
    pair[1151] = invalid; // invalid last cell in the second eye
    const before = Buffer.from(buf(pair));
    assert.throws(() => custom.mapPair(pair, native.NATIVE_LUT));
    assert.deepEqual(buf(pair), before);
  }
  assert.throws(() => custom.samplePair(Buffer.alloc(1440 * 192 - 1), 1440, custom.preparePlan()));
  assert.throws(() => custom.samplePair(Buffer.alloc(1440 * 192), 720, custom.preparePlan()));
});

test('plans are independent immutable snapshots and expose no middle-stage controls', () => {
  const table = [...native.NATIVE_LUT];
  const request = { enabled: true, sampler: 'peak', lut: table };
  const frame = custom.preparePlan(request);
  request.enabled = false; request.sampler = 'mean'; table[1] = 0;
  assert.equal(frame.enabled, true);
  assert.equal(frame.sampler, 'peak');
  assert.equal(frame.lut[1], 409);
  assert.throws(() => { frame.lut[1] = 0; });
  for (const name of ['gaussian', 'dilate_x', 'smooth', 'smooth.weight', 'smooth_weight', 'support_gate', 'threshold']) {
    assert.throws(() => custom.preparePlan({ [name]: 1 }));
  }
  for (const peakWeight of [NaN, Infinity, -0.01, 1.1]) assert.throws(() => custom.preparePlan({ peakWeight }));
});

fixtureTest('default, explicit native replay and disabled custom plan preserve continuous original frames', () => {
  // Replays existing evidence; does not generate or alter any headset setting.
  for (const plan of [{}, { enabled: true, sampler: 'mean', lut: native.NATIVE_LUT },
    { enabled: false, sampler: 'peak', lut: custom.curve(255, 2) }]) {
    const state = native.createNativeState();
    for (const c of fixtures.cases.filter(c => c.stage === 'frame')) {
      custom.processFrame(state, Buffer.from(c.raw, 'base64'), c.stride, plan, c.config);
      assert.equal(state.selector, c.after.selector);
      assert.deepEqual(buf(state.buffers), Buffer.from(c.after.buffers, 'base64'));
      assert.deepEqual(buf(state.history), Buffer.from(c.after.history, 'base64'));
    }
  }
});

fixtureTest('LUT-only changes do not change same-frame history or pre-LUT processing', () => {
  const c = fixtures.cases.find(c => c.stage === 'frame');
  const raw = Buffer.from(c.raw, 'base64');
  const a = native.createNativeState(), b = native.createNativeState();
  const original = custom.processFrame(a, raw, c.stride);
  const changed = custom.processFrame(b, raw, c.stride, { enabled: true, lut: custom.curve(255, 1) });
  assert.deepEqual(buf(original.beforeLut.buffers), buf(changed.beforeLut.buffers));
  assert.deepEqual(buf(a.history), buf(b.history));
  assert.notDeepEqual(buf(a.buffers), buf(b.buffers));
});
