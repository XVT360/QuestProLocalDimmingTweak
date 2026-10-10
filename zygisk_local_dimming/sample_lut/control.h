#pragma once
#include "sample_lut_core.h"
#include <cstdint>

namespace quest_ld {
constexpr const char *kPrefix = "debug.oculus.localDimming.zl2.";
struct CurveSettings {
    bool known = true;
    uint32_t threshold = 20;
    float gamma = 1.0f;
};
bool prop_read(const char *suffix, char *out);
bool prop_set(const char *suffix, const char *value);
bool switch_on(const char *suffix);
bool read_committed_plan(Plan *out, uint32_t *sequence);
bool publish_properties(const Plan &plan, const CurveSettings *curve = nullptr);
CurveSettings read_curve_settings(const Plan &plan);
} // namespace quest_ld
