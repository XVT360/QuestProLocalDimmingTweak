#pragma once
#include "control.h"
#include <cstddef>
#include <cstdint>

namespace quest_ld {
// Native fallbacks read at descriptor +0xa0 in the pinned firmware.
// The controller range stops before the empty-interior dilation cases.
constexpr uint32_t kMaxDilateX = 8, kMaxDilateY = 15, kMaxGaussian = 9;
constexpr float kMaxSmoothWeight = 0.3f; // exactly 0x3e99999a in binary32
constexpr size_t kSettingsCapacity = 60 + 2 * kMaxLutEntries;
struct DebugSettings {
    uint32_t x = 1, y = 2, gaussian = 3, smooth = 1;
    float weight = kMaxSmoothWeight;
};
struct Settings {
    DebugSettings debug{};
    Plan plan{};
    CurveSettings curve{};
};
bool valid_debug(const DebugSettings &debug);
bool valid_settings(const Settings &settings);
bool same_settings(const Settings &a, const Settings &b);
bool encode_settings(const Settings &settings, uint8_t *bytes, size_t capacity, size_t *length);
bool decode_settings(const uint8_t *bytes, size_t length, Settings *settings);
bool parse_uint(const char *text, uint32_t maximum, uint32_t *out);
bool parse_float(const char *text, float minimum, float maximum, float *out);
bool read_debug(DebugSettings *out);
void print_debug();
bool apply_debug(const DebugSettings &debug);
bool read_live_settings(Settings *out);

enum class LoadResult { Good, Missing, Invalid, IoError };
LoadResult load_settings(Settings *out);
int lock_settings();
struct PendingSettings { int directory = -1; };
bool stage_settings(const Settings &settings, PendingSettings *out);
bool finish_settings(PendingSettings *pending);
void cancel_settings(PendingSettings *pending);
void print_saved_settings();
} // namespace quest_ld
