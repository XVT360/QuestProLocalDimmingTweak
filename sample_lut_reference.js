'use strict';

// Offline specification of the two replacement stages. The middle stages in
// processFrame are the verified native reference, not new module algorithms.
const native = require('./native_reference');
const f32 = Math.fround;
const PAIR = native.CELLS * 2;

function validateTable(values) {
  if (!Array.isArray(values) && !(values instanceof Uint16Array)) {
    throw new TypeError('LUT must contain integer software output codes');
  }
  const table = Array.from(values);
  if (table.length < 2 || table.length > 256 || table[0] !== 0 || table.at(-1) !== 8190) {
    throw new RangeError('LUT requires 2..256 entries, starting at 0 and ending at 8190');
  }
  for (let i = 0; i < table.length; i++) {
    if (!Number.isInteger(table[i]) || table[i] < 0 || table[i] > 8190 ||
        (i && table[i] < table[i - 1])) throw new RangeError('LUT must be monotonic in 0..8190');
  }
  return Object.freeze(table);
}

function curve(threshold = 20, gamma = 1) {
  // These bounds are a module policy, not a proven optical operating range.
  if (!Number.isFinite(gamma) || gamma < 0.1 || gamma > 8) {
    throw new RangeError('Curve gamma must be in 0.1..8');
  }
  return validateTable(native.generateNativeLut(threshold, gamma));
}

function preparePlan(request = {}) {
  const allowed = new Set(['enabled', 'sampler', 'peakWeight', 'lut']);
  for (const key of Object.keys(request)) {
    if (!allowed.has(key)) throw new TypeError(`Unsupported setting: ${key}`);
  }
  const enabled = request.enabled ?? false;
  const sampler = request.sampler ?? 'native';
  const peakWeight = f32(request.peakWeight ?? 0);
  if (typeof enabled !== 'boolean' || !['native', 'mean', 'peak', 'blend'].includes(sampler)) {
    throw new TypeError('Invalid enable flag or sampler');
  }
  if (!Number.isFinite(peakWeight) || peakWeight < 0 || peakWeight > 1) {
    throw new RangeError('Peak weight must be in 0..1');
  }
  // A frame receives a private immutable snapshot. Later edits cannot change
  // one eye or only the later LUT stage of a frame already in progress.
  return Object.freeze({ enabled, sampler, peakWeight,
    lut: request.lut == null ? null : validateTable(request.lut) });
}

function samplePair(raw, stride, plan) {
  if (!Buffer.isBuffer(raw) || !Number.isInteger(stride) || stride < 1440 ||
      stride > 65536 || stride % 4 || raw.length < 191 * stride + 1440) {
    throw new RangeError('Expected two 180x192 RGBA regions and a bounded row stride');
  }
  const output = new Float32Array(PAIR);
  for (let eye = 0; eye < 2; eye++) {
    for (let y = 0; y < native.HEIGHT; y++) {
      for (let x = 0; x < native.WIDTH; x++) {
        let r = 0, g = 0, b = 0, peak = 0;
        for (let yy = 0; yy < 6; yy++) {
          const start = eye * 720 + (y * 6 + yy) * stride + x * 40;
          for (let xx = 0; xx < 10; xx++) {
            const at = start + xx * 4;
            r += raw[at]; g += raw[at + 1]; b += raw[at + 2];
            peak = Math.max(peak, raw[at], raw[at + 1], raw[at + 2]);
          }
        }
        const mean = f32(f32(Math.max(r, g, b) / 10) / 6);
        let value = mean;
        if (plan.sampler === 'peak' || (plan.sampler === 'blend' && plan.peakWeight === 1)) value = peak;
        else if (plan.sampler === 'blend' && plan.peakWeight !== 0) {
          value = native.fma32(plan.peakWeight, f32(peak - mean), mean);
        }
        output[eye * native.CELLS + y * native.WIDTH + x] = value;
      }
    }
  }
  return output;
}

function mapPair(pair, table) {
  if (!(pair instanceof Float32Array) || pair.length !== PAIR) throw new RangeError('Expected both matrices');
  table = validateTable(table);
  // Validate the complete pair before committing either eye. No partial
  // writes if one value or table entry is invalid.
  if (pair.some(v => !Number.isFinite(v) || v < 0)) throw new RangeError('Invalid LUT input');
  return Float32Array.from(pair, value => native.mapNativeLut(value, table));
}

function cloneState(state) {
  return { selector: state.selector, buffers: Float32Array.from(state.buffers),
    history: Float32Array.from(state.history) };
}

function activePair(state) {
  return state.buffers.subarray(state.selector * PAIR, (state.selector + 1) * PAIR);
}

function processFrame(state, raw, stride, request = {}, original = {}, nativeLut = native.NATIVE_LUT) {
  const plan = preparePlan(request);
  if (plan.enabled && plan.sampler !== 'native') activePair(state).set(samplePair(raw, stride, plan));
  else native.sampleStage(state, raw, stride);
  const sampled = cloneState(state);
  // Owned by the original runtime in the proposed integration. No module
  // settings exist for dilation, Gaussian, smooth or smooth.weight.
  native.dilateStage(state, original.x ?? 1, original.y ?? 2);
  native.gaussianStage(state, original.gaussian ?? 3);
  if (original.smooth ?? 1) native.smoothStage(state, original.weight ?? 0.3);
  const beforeLut = cloneState(state);
  if (plan.enabled && plan.lut !== null) activePair(state).set(mapPair(activePair(state), plan.lut));
  else native.lutStage(state, nativeLut);
  return { sampled, beforeLut, after: cloneState(state) };
}

module.exports = { preparePlan, curve, samplePair, mapPair, processFrame, activePair, validateTable };

// JSON-lines transport for the offline ARM64 verifier. No Android operations.
if (require.main === module) {
  const readline = require('node:readline');
  function floats(encoded) {
    const bytes = Buffer.from(encoded, 'base64');
    return Float32Array.from({ length: bytes.length / 4 }, (_, i) => bytes.readFloatLE(i * 4));
  }
  function encode(state) {
    const bytes = a => Buffer.from(a.buffer, a.byteOffset, a.byteLength).toString('base64');
    return { selector: state.selector, buffers: bytes(state.buffers), history: bytes(state.history) };
  }
  const lines = readline.createInterface({ input: process.stdin });
  lines.on('line', line => {
    try {
      const req = JSON.parse(line);
      const state = { selector: req.before.selector, buffers: floats(req.before.buffers), history: floats(req.before.history) };
      const stages = processFrame(state, Buffer.from(req.raw, 'base64'), req.stride, req.plan, req.original, req.nativeLut);
      process.stdout.write(JSON.stringify(Object.fromEntries(Object.entries(stages).map(([k, v]) => [k, encode(v)]))) + '\n');
    } catch (err) {
      process.stdout.write(JSON.stringify({ error: err.message }) + '\n');
    }
  });
}
