#include "sample_lut_core.h"

#include <algorithm>
#include <cmath>
#include <limits>

#if defined(__FAST_MATH__)
#error "Native parity requires no fast-math/reassociation and -ffp-contract=off"
#endif

namespace quest_ld {
static_assert(sizeof(float) == 4 && std::numeric_limits<float>::is_iec559,
              "The original code uses IEEE-754 binary32");

namespace {
bool overlap(const void *a, size_t an, const void *b, size_t bn) noexcept {
    const uintptr_t aa = reinterpret_cast<uintptr_t>(a);
    const uintptr_t bb = reinterpret_cast<uintptr_t>(b);
    if (aa > UINTPTR_MAX - an || bb > UINTPTR_MAX - bn) return true;
    return aa < bb + bn && bb < aa + an;
}

float lookup(float v, const Lut &lut) noexcept {
    // Callers have already rejected NaN, infinity and negative inputs.
    if (v >= static_cast<float>(lut.count - 1)) return 8190.0f;
    const size_t i = static_cast<size_t>(v);
    const float fraction = v - static_cast<float>(i);
    const float right = fraction * static_cast<float>(lut.codes[i + 1]);
    const float left_weight = 1.0f - fraction;
    // Match FMUL + FMADD, not a reassociated double-precision lerp.
    return std::fma(left_weight, static_cast<float>(lut.codes[i]), right);
}
} // namespace

bool valid_lut(const Lut &lut) noexcept {
    if (lut.count < 2 || lut.count > kMaxLutEntries ||
        lut.codes[0] != 0 || lut.codes[lut.count - 1] != 8190) return false;
    for (size_t i = 1; i < lut.count; ++i)
        if (lut.codes[i] > 8190 || lut.codes[i] < lut.codes[i - 1]) return false;
    return true;
}

bool valid_plan(const Plan &plan) noexcept {
    if (static_cast<uint32_t>(plan.sampler) > static_cast<uint32_t>(Sampler::Blend) ||
        !std::isfinite(plan.peak_weight) || plan.peak_weight < 0.0f ||
        plan.peak_weight > 1.0f) return false;
    return plan.lut.count == 0 || valid_lut(plan.lut);
}

bool make_curve(uint32_t threshold, float gamma, Lut *candidate) noexcept {
    if (!candidate || threshold < 1 || threshold > 255 ||
        !std::isfinite(gamma) || gamma < 0.1f || gamma > 8.0f) return false;
    Lut prepared{};
    prepared.count = threshold + 1;
    for (uint32_t i = 0; i <= threshold; ++i) {
        const float ratio = static_cast<float>(i) / static_cast<float>(threshold);
        const float power = ::powf(ratio, gamma);
        const float code = power * 8190.0f;
        if (!std::isfinite(code) || code < 0.0f || code > 8190.0f) return false;
        prepared.codes[i] = static_cast<uint16_t>(code);
    }
    if (!valid_lut(prepared)) return false;
    *candidate = prepared;
    return true;
}

bool sample_pair(RawView raw, const Plan &plan, float *scratch,
                 size_t scratch_cells) noexcept {
    if (!raw.data || !scratch || scratch_cells < kPairCells || !valid_plan(plan) ||
        raw.stride < 1440 || raw.stride > 65536 || raw.stride % 4) return false;
    const size_t required = 191 * raw.stride + 1440;
    if (raw.bytes < required || overlap(raw.data, required, scratch, kPairCells * sizeof(float)) ||
        overlap(&plan, sizeof(plan), scratch, kPairCells * sizeof(float))) return false;
    for (size_t eye = 0; eye < 2; ++eye) {
        for (size_t y = 0; y < 32; ++y) {
            for (size_t x = 0; x < 18; ++x) {
                uint32_t r = 0, g = 0, b = 0, peak = 0;
                for (size_t yy = 0; yy < 6; ++yy) {
                    const uint8_t *row = raw.data + eye * 720 +
                        (y * 6 + yy) * raw.stride + x * 40;
                    for (size_t xx = 0; xx < 10; ++xx) {
                        const uint8_t *p = row + xx * 4;
                        r += p[0]; g += p[1]; b += p[2];
                        peak = std::max(peak, static_cast<uint32_t>(std::max(p[0], std::max(p[1], p[2]))));
                    }
                }
                const uint32_t sum = std::max(r, std::max(g, b));
                // Keep two float divisions; /60 is not a bit-exact substitute.
                const float row_average = static_cast<float>(sum) / 10.0f;
                const float mean = row_average / 6.0f;
                float value = mean;
                if (plan.sampler == Sampler::Peak ||
                    (plan.sampler == Sampler::Blend && plan.peak_weight == 1.0f)) {
                    value = static_cast<float>(peak);
                } else if (plan.sampler == Sampler::Blend && plan.peak_weight != 0.0f) {
                    const float difference = static_cast<float>(peak) - mean;
                    value = std::fma(plan.peak_weight, difference, mean);
                }
                scratch[eye * kCells + y * 18 + x] = value;
            }
        }
    }
    return true;
}

bool map_pair(const float *input, size_t input_cells, const Lut &lut,
              float *scratch, size_t scratch_cells) noexcept {
    if (!input || !scratch || input_cells != kPairCells || scratch_cells < kPairCells ||
        !valid_lut(lut) || overlap(input, kPairCells * sizeof(float), scratch, kPairCells * sizeof(float)) ||
        overlap(&lut, sizeof(lut), scratch, kPairCells * sizeof(float))) return false;
    for (size_t i = 0; i < kPairCells; ++i)
        if (!std::isfinite(input[i]) || input[i] < 0.0f) return false;
    for (size_t i = 0; i < kPairCells; ++i) scratch[i] = lookup(input[i], lut);
    return true;
}
} // namespace quest_ld
