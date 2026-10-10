'use strict';

const test = require('node:test');
const assert = require('node:assert/strict');
const {
  CELLS,
  HEIGHT,
  NATIVE_DEFAULTS,
  NATIVE_LUT,
  WIDTH,
  dilateNative,
  gaussianKernelNative,
  gaussianNative,
  mapNativeLut,
  sampleNative,
  smoothNative,
} = require('./native_reference');

test('native sampler averages the largest RGB channel sum over each 6x10 cell', () => {
  const stride = WIDTH * 40;
  const input = Buffer.alloc(stride * (HEIGHT * 6 + 1));
  for (let y = 0; y < HEIGHT; y++) {
    for (let x = 0; x < WIDTH; x++) {
      const p = y * 6 * stride + x * 40;
      input[p] = 20;
      input[p + stride + 4] = 20;
      input[p + 2 * stride + 8] = 20;
    }
  }
  const matrix = sampleNative(input, stride);
  assert.equal(matrix.length, CELLS);
  assert.ok(matrix.every(value => value === 1));
});

test('native sampler compares channel totals, not the brightest individual pixel', () => {
  const stride = WIDTH * 40;
  const input = Buffer.alloc(stride * HEIGHT * 6);
  const p = 0;
  input[p] = 40;
  input[p + 4] = 40;
  input[p + 8 + 1] = 60;
  assert.equal(sampleNative(input, stride)[0], Math.fround(Math.fround(80 / 10) / 6));
});

test('native dilation expands an interior impulse and preserves destination borders', () => {
  const input = new Float32Array(CELLS);
  input[16 * WIDTH + 9] = 5;
  const filtered = dilateNative(input, 1, 1);
  let nonzero = 0;
  for (const value of filtered) if (value !== 0) nonzero++;
  assert.equal(nonzero, 9);
  const alternate = new Float32Array(CELLS).fill(17);
  const defaults = dilateNative(input, NATIVE_DEFAULTS.dilateX, NATIVE_DEFAULTS.dilateY, alternate);
  assert.equal(defaults[0], 17);
  assert.equal(defaults[16 * WIDTH + 9], 5);
  assert.equal(defaults[10 * WIDTH + 9], 0);
  assert.equal(defaults.filter(v => v === 5).length, 15);
});

test('native smoothing blends into both current and history matrices', () => {
  const current = new Float32Array(CELLS).fill(1);
  const previous = new Float32Array(CELLS);
  const result = smoothNative(current, previous);
  assert.equal(result[0], Math.fround(0.3));
  assert.equal(current[0], result[0]);
  assert.equal(previous[0], result[0]);
});

test('native LUT maps input units to software output codes and clamps at input 20', () => {
  assert.equal(mapNativeLut(0), NATIVE_LUT[0]);
  assert.equal(mapNativeLut(1), NATIVE_LUT[1]);
  assert.equal(mapNativeLut(20), 8190);
  assert.equal(mapNativeLut(21), 8190);
  assert.equal(mapNativeLut(255), 8190);
  assert.equal(mapNativeLut(10), 4095);
  // 255 is a full-scale byte/input reference, not this output interface's cap.
  assert.equal(mapNativeLut(0.5), Math.fround(0.5 * 409));
});

test('Gaussian coefficient generation follows the normalized radial exponential', () => {
  const kernel = gaussianKernelNative(3);
  assert.equal(kernel.length, 9);
  assert.ok(Math.abs(Array.from(kernel).reduce((sum, value) => sum + value, 0) - 1) < 1e-6);
  assert.equal(kernel[4], Math.max(...kernel));
  assert.ok(kernel[0] < kernel[1]);
  assert.equal(gaussianKernelNative(4).length, 16);
});

test('Gaussian convolution streams coefficients from the table start over the clipped window', () => {
  const source = new Float32Array(CELLS).fill(1);
  const kernel2 = gaussianKernelNative(2);
  const out2 = gaussianNative(source, 2, kernel2);
  assert.ok(out2.every(value => value === kernel2[0]));

  const impulse = new Float32Array(CELLS);
  impulse[WIDTH + 1] = 1;
  const kernel4 = gaussianKernelNative(4);
  const out4 = gaussianNative(impulse, 4, kernel4);
  assert.equal(out4[0], kernel4[3]);
});
