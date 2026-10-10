#pragma once

// New two-stage source, intentionally not in Android.mk before build approval.
// This is independent of the historical post-LUT algorithm and hook.
#include <cstddef>
#include <cstdint>

namespace quest_ld {
constexpr size_t kCells = 18 * 32;
constexpr size_t kPairCells = kCells * 2;
constexpr size_t kMaxLutEntries = 256;

enum class Sampler : uint32_t { Native = 0, Mean = 1, Peak = 2, Blend = 3 };

struct Lut {
    size_t count = 0; // zero means use the original runtime's LUT instructions
    uint16_t codes[kMaxLutEntries] = {};
};

struct Plan {
    bool enabled = false;
    Sampler sampler = Sampler::Native;
    float peak_weight = 0.0f;
    Lut lut{};
};

struct RawView {
    const uint8_t *data;
    size_t bytes; // extent verified by the eventual frame adapter, not a guess
    size_t stride;
};

bool valid_lut(const Lut &lut) noexcept;
bool valid_plan(const Plan &plan) noexcept;

// Non-render thread only. Candidate is assigned only after full validation.
// Android must use the target libm's powf; host Math.pow is only a reference.
bool make_curve(uint32_t threshold, float gamma, Lut *candidate) noexcept;

// No allocations, logging, property reads, locks or native global writes.
// The destination is module-owned scratch, not the native matrix. Caller
// commits the complete pair only after success. It must not alias the input.
bool sample_pair(RawView raw, const Plan &plan, float *scratch,
                 size_t scratch_cells) noexcept;
bool map_pair(const float *input, size_t input_cells, const Lut &lut,
              float *scratch, size_t scratch_cells) noexcept;
} // namespace quest_ld
