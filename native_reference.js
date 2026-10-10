'use strict';

const WIDTH = 18;
const HEIGHT = 32;
const CELLS = WIDTH * HEIGHT;

// Corrected from [SUPERSEDED] 256/512/768: descriptor fallback is at +0xa0.
// See native_audit_20261007/readonly_audit.json. These are firmware-specific.
const NATIVE_DEFAULTS = Object.freeze({
  dilateX: 1,
  dilateY: 2,
  gaussian: 3,
  smooth: 1,
  smoothWeight: 0.3,
});

// S9: software output codes. 8190 is not a physical luminance measurement;
// 255 belongs to the raw RGBA/sampler domain. Do not rescale
// this table to 255 when reproducing the native output interface.
const NATIVE_LUT = Object.freeze([
  0, 409, 819, 1228, 1638, 2047, 2457, 2866, 3276, 3685, 4095,
  4504, 4914, 5323, 5733, 6142, 6552, 6961, 7371, 7780, 8190,
]);

function f32(value) {
  return Math.fround(value);
}

function sampleNative(input, stride, region = 0) {
  if (!Buffer.isBuffer(input) || !Number.isInteger(stride) || stride < WIDTH * 40) {
    throw new TypeError('Expected a byte buffer and a valid RGBA row stride');
  }
  const matrix = new Float32Array(CELLS);
  for (let y = 0; y < HEIGHT; y++) {
    for (let x = 0; x < WIDTH; x++) {
      const sums = [0, 0, 0];
      const start = region + y * 6 * stride + x * 40;
      for (let row = 0; row < 6; row++) {
        for (let col = 0; col < 10; col++) {
          const p = start + row * stride + col * 4;
          if (p + 2 >= input.length) throw new RangeError('Input does not cover the sample grid');
          sums[0] += input[p];
          sums[1] += input[p + 1];
          sums[2] += input[p + 2];
        }
      }
      const peak = Math.max(sums[0], sums[1], sums[2]);
      matrix[y * WIDTH + x] = f32(f32(peak / 10) / 6);
    }
  }
  return matrix;
}

// S1: Destination is the *existing* alternate matrix. Native borders are not
// overwritten; callers need both buffers to reproduce more than one frame.
function dilateNative(matrix, radiusX, radiusY, alternate = new Float32Array(CELLS)) {
  if (matrix.length !== CELLS || alternate.length !== CELLS) throw new RangeError('Expected 32x18 matrices');
  if (!Number.isInteger(radiusX) || !Number.isInteger(radiusY) || radiusX < 0 || radiusY < 0) {
    throw new RangeError('Dilation radii must be non-negative integers');
  }
  if (radiusX === 0 && radiusY === 0) return Float32Array.from(matrix);
  const output = Float32Array.from(alternate);
  if (radiusX >= 9 || radiusY >= 16) return output;
  for (let y = radiusY; y < HEIGHT - radiusY; y++) {
    for (let x = radiusX; x < WIDTH - radiusX; x++) {
      let peak = 0;
      for (let yy = y - radiusY; yy <= y + radiusY; yy++) {
        for (let xx = x - radiusX; xx <= x + radiusX; xx++) {
          const value = matrix[yy * WIDTH + xx];
          if (value > peak) peak = value;
        }
      }
      output[y * WIDTH + x] = peak;
    }
  }
  return output;
}

// Exact finite binary32 fused multiply-add for the host reference. JavaScript
// double multiply/add can double-round at a binary32 midpoint. Use an integer
// significand so the final rounding occurs just once, as on ARM64 FMADD.
const floatView = new DataView(new ArrayBuffer(4));
function floatParts(value) {
  floatView.setFloat32(0, value, true);
  const bits = floatView.getUint32(0, true);
  const exponent = (bits >>> 23) & 255;
  const fraction = bits & 0x7fffff;
  const mantissa = BigInt(exponent ? fraction + 0x800000 : fraction);
  return { n: bits >>> 31 ? -mantissa : mantissa, e: exponent ? exponent - 150 : -149 };
}

function fma32(a, b, c) {
  a = f32(a); b = f32(b); c = f32(c);
  if (![a, b, c].every(Number.isFinite) || a === 0 || b === 0) return f32(a * b + c);
  const aa = floatParts(a), bb = floatParts(b), cc = floatParts(c);
  const ep = aa.e + bb.e;
  const e = Math.min(ep, cc.e);
  let n = (aa.n * bb.n << BigInt(ep - e)) + (cc.n << BigInt(cc.e - e));
  if (n === 0n) return 0;
  const sign = n < 0n ? -1 : 1;
  if (n < 0n) n = -n;
  const length = n.toString(2).length;
  const resultExponent = Math.max(-149, e + length - 24);
  const shift = resultExponent - e;
  if (shift > 0) {
    const s = BigInt(shift);
    let rounded = n >> s;
    const remainder = n - (rounded << s);
    const halfway = 1n << (s - 1n);
    if (remainder > halfway || (remainder === halfway && (rounded & 1n))) rounded++;
    n = rounded;
  } else if (shift < 0) {
    n <<= BigInt(-shift);
  }
  return f32(sign * Number(n) * 2 ** resultExponent);
}

// S2: preserve asymmetric even kernels for compatibility; see SIDE_EFFECTS.md.
function gaussianKernelNative(size) {
  if (!Number.isInteger(size) || size < 1 || size > 33) throw new RangeError('Verified Gaussian size range is 1..33');
  const count = size * size;
  const weights = new Float32Array(count);
  const half = size >> 1;
  let total = 0;
  for (let dx = 0; dx < size; dx++) {
    const x = dx - half;
    for (let dy = 0; dy < size; dy++) {
      const y = dy - half;
      const weight = f32(Math.exp(-0.5 * (x * x + y * y)));
      weights[dy * size + dx] = weight;
      total = f32(total + weight);
    }
  }
  for (let i = 0; i < count; i++) weights[i] = f32(weights[i] / total);
  return weights;
}

// S3: clipped windows consume coefficients from index zero without renormalizing.
function gaussianNative(matrix, size, kernel) {
  if (matrix.length !== CELLS) throw new RangeError('Expected a 32x18 matrix');
  if (size < 1) return Float32Array.from(matrix);
  kernel ??= gaussianKernelNative(size);
  if (kernel.length !== size * size) throw new RangeError('Incorrect Gaussian coefficient count');
  const radius = (size - 1) >> 1;
  const output = new Float32Array(CELLS);
  for (let y = 0; y < HEIGHT; y++) {
    const y0 = Math.max(0, y - radius);
    const y1 = Math.min(HEIGHT - 1, y + radius);
    for (let x = 0; x < WIDTH; x++) {
      const x0 = Math.max(0, x - radius);
      const x1 = Math.min(WIDTH - 1, x + radius);
      let sum = 0;
      let weightIndex = 0;
      for (let yy = y0; yy <= y1; yy++) {
        const vectorEnd = x0 + Math.floor((x1 - x0 + 1) / 8) * 8;
        for (let xx = x0; xx <= x1; xx++, weightIndex++) {
          const weight = kernel[weightIndex];
          const value = matrix[yy * WIDTH + xx];
          sum = xx < vectorEnd ? f32(sum + f32(value * weight)) : fma32(weight, value, sum);
        }
      }
      output[y * WIDTH + x] = sum;
    }
  }
  return output;
}

// S4: compatibility model of temporal lag. No further headset weight sweeps.
function smoothNative(current, previous, weight = NATIVE_DEFAULTS.smoothWeight) {
  if (current.length !== CELLS || previous.length !== CELLS) {
    throw new RangeError('Expected two 32x18 matrices');
  }
  weight = f32(weight);
  const next = new Float32Array(CELLS);
  for (let i = 0; i < CELLS; i++) {
    next[i] = fma32(f32(1 - weight), previous[i], f32(current[i] * weight));
  }
  current.set(next);
  previous.set(next);
  return next;
}

function mapNativeLut(value, lut = NATIVE_LUT) {
  value = f32(value);
  // Native has no lower-bound guard and would read before the LUT for <= -1.
  // Only the nonnegative finite pipeline domain is supported by this model.
  if (!Number.isFinite(value) || value < 0) throw new RangeError('Expected a finite nonnegative LUT input');
  if (value >= lut.length - 1) return 8190;
  const lower = Math.trunc(value);
  const fraction = f32(value - lower);
  return fma32(f32(1 - fraction), lut[lower], f32(fraction * lut[lower + 1]));
}

function generateNativeLut(threshold = 20, gamma = 1) {
  if (!Number.isInteger(threshold) || threshold < 1 || threshold > 255 || !Number.isFinite(gamma) || gamma <= 0) {
    throw new RangeError('Expected threshold 1..255 and positive finite gamma');
  }
  gamma = f32(gamma);
  const table = new Uint16Array(threshold + 1);
  for (let i = 0; i <= threshold; i++) {
    table[i] = Math.trunc(f32(f32(Math.pow(f32(i / threshold), gamma)) * 8190));
  }
  // This host Math.pow transcription is verified for the oracle cases. A
  // future Android implementation must use that firmware's powf, not assume
  // JavaScript pow is identical for every possible gamma.
  return table;
}

function createNativeState() {
  return { selector: 0, buffers: new Float32Array(CELLS * 4), history: new Float32Array(CELLS * 2) };
}

function eyeMatrix(state, selector, eye) {
  const start = (selector * 2 + eye) * CELLS;
  return state.buffers.subarray(start, start + CELLS);
}

function sampleStage(state, raw, stride) {
  for (let eye = 0; eye < 2; eye++) eyeMatrix(state, state.selector, eye).set(sampleNative(raw, stride, eye * 0x2d0));
}

function dilateStage(state, x, y) {
  if (x === 0 && y === 0) return;
  const dst = 1 - state.selector;
  for (let eye = 0; eye < 2; eye++) {
    const target = eyeMatrix(state, dst, eye);
    target.set(dilateNative(eyeMatrix(state, state.selector, eye), x, y, target));
  }
  state.selector = dst;
}

function gaussianStage(state, size, kernel) {
  if (size < 1) return;
  kernel ??= gaussianKernelNative(size);
  const dst = 1 - state.selector;
  for (let eye = 0; eye < 2; eye++) eyeMatrix(state, dst, eye).set(gaussianNative(eyeMatrix(state, state.selector, eye), size, kernel));
  state.selector = dst;
}

function smoothStage(state, weight) {
  for (let eye = 0; eye < 2; eye++) smoothNative(eyeMatrix(state, state.selector, eye), state.history.subarray(eye * CELLS, (eye + 1) * CELLS), weight);
}

function lutStage(state, lut = NATIVE_LUT) {
  for (let eye = 0; eye < 2; eye++) {
    const matrix = eyeMatrix(state, state.selector, eye);
    for (let i = 0; i < CELLS; i++) matrix[i] = mapNativeLut(matrix[i], lut);
  }
}

function processNativeFrame(state, raw, stride, config = {}) {
  const { x = 1, y = 2, gaussian = 3, smooth = 1, weight = 0.3 } = config;
  sampleStage(state, raw, stride);
  dilateStage(state, x, y);
  gaussianStage(state, gaussian);
  if (smooth) smoothStage(state, weight);
  lutStage(state);
  return state;
}

module.exports = {
  CELLS,
  HEIGHT,
  NATIVE_DEFAULTS,
  NATIVE_LUT,
  WIDTH,
  createNativeState,
  dilateStage,
  eyeMatrix,
  fma32,
  gaussianStage,
  generateNativeLut,
  lutStage,
  processNativeFrame,
  sampleStage,
  smoothStage,
  dilateNative,
  gaussianKernelNative,
  gaussianNative,
  mapNativeLut,
  sampleNative,
  smoothNative,
};
