#include "settings.h"
#include <sys/system_properties.h>
#include <cstdio>
#include <cstring>

namespace quest_ld {
namespace {
constexpr const char *debug_names[] = {
    "debug.oculus.localDimming.debugDilateX", "debug.oculus.localDimming.debugDilateY",
    "debug.oculus.localDimming.debugGaussian", "debug.oculus.localDimming.smooth",
    "debug.oculus.localDimming.smooth.weight"};
constexpr const char *defaults[] = {"1", "2", "3", "1", "0.3"};
constexpr const char *status_names[] = {"debug_dilate_x", "debug_dilate_y", "debug_gaussian", "debug_smooth", "debug_smooth_weight"};
bool read_value(size_t index, char *value) {
    value[0] = 0;
    return __system_property_get(debug_names[index], value) >= 0;
}
} // namespace
bool read_debug(DebugSettings *out) {
    DebugSettings d;
    uint32_t *integers[] = {&d.x, &d.y, &d.gaussian, &d.smooth};
    constexpr uint32_t limits[] = {kMaxDilateX, kMaxDilateY, kMaxGaussian, 1};
    char value[PROP_VALUE_MAX];
    for (size_t i = 0; i < 5; ++i) {
        if (!read_value(i, value)) return false;
        if (!value[0]) std::snprintf(value, sizeof(value), "%s", defaults[i]);
        if (i < 4) {
            if (!parse_uint(value, limits[i], integers[i])) return false;
        } else if (!parse_float(value, 0, kMaxSmoothWeight, &d.weight)) return false;
    }
    if (!valid_debug(d)) return false;
    *out = d;
    return true;
}
void print_debug() {
    DebugSettings d;
    std::printf("debug_valid=%d\n", read_debug(&d));
    char value[PROP_VALUE_MAX];
    for (size_t i = 0; i < 5; ++i) {
        read_value(i, value);
        std::printf("%s=%s\n", status_names[i], value[0] ? value : defaults[i]);
    }
    std::puts("debug_smooth_weight_max=0.3");
}
bool apply_debug(const DebugSettings &d) {
    if (!valid_debug(d)) return false;
    char next[5][32], previous[5][PROP_VALUE_MAX];
    const uint32_t values[] = {d.x, d.y, d.gaussian, d.smooth};
    for (size_t i = 0; i < 4; ++i) std::snprintf(next[i], sizeof(next[i]), "%u", values[i]);
    if (d.weight == kMaxSmoothWeight) std::snprintf(next[4], sizeof(next[4]), "0.3");
    else std::snprintf(next[4], sizeof(next[4]), "%.9g", static_cast<double>(d.weight));
    for (size_t i = 0; i < 5; ++i) if (!read_value(i, previous[i])) return false;
    // Restore a safe prior value if a property write fails. Never replay an
    // out-of-range smooth weight imported through an external ADB command.
    DebugSettings prior;
    if (!read_debug(&prior))
        for (size_t i = 0; i < 5; ++i) std::snprintf(previous[i], sizeof(previous[i]), "%s", defaults[i]);
    constexpr size_t order[] = {4, 0, 1, 2, 3}; // bound weight before enabling smoothing
    for (size_t i : order) {
        if (__system_property_set(debug_names[i], next[i]) != 0) {
            for (size_t j : order) __system_property_set(debug_names[j], previous[j]);
            return false;
        }
    }
    return true;
}
bool read_live_settings(Settings *out) {
    Settings s;
    uint32_t seq, after;
    char text[PROP_VALUE_MAX];
    if (!read_committed_plan(&s.plan, &seq) || !read_debug(&s.debug)) return false;
    s.curve = read_curve_settings(s.plan);
    if (!prop_read("seq", text) || !parse_uint(text[0] ? text : "0", UINT32_MAX, &after) || seq != after ||
        !valid_settings(s)) return false;
    *out = s;
    return true;
}
} // namespace quest_ld
