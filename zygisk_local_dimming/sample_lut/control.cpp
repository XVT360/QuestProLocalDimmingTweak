#include "control.h"
#include <sys/system_properties.h>
#include <cstdlib>
#include <cstdio>
#include <cstring>
#include <cerrno>

namespace quest_ld {
bool prop_read(const char *suffix, char *out) {
    char key[128];
    const int n = std::snprintf(key, sizeof(key), "%s%s", kPrefix, suffix);
    if (n < 0 || static_cast<size_t>(n) >= sizeof(key)) return false;
    out[0] = 0;
    return __system_property_get(key, out) >= 0;
}
bool prop_set(const char *suffix, const char *value) {
    char key[128];
    const int n = std::snprintf(key, sizeof(key), "%s%s", kPrefix, suffix);
    return n > 0 && static_cast<size_t>(n) < sizeof(key) && __system_property_set(key, value) == 0;
}
bool switch_on(const char *suffix) {
    char value[PROP_VALUE_MAX];
    return prop_read(suffix, value) && std::strcmp(value, "1") == 0;
}
namespace {
bool integer(const char *key, uint32_t fallback, uint32_t *out) {
    char value[PROP_VALUE_MAX];
    if (!prop_read(key, value)) return false;
    if (!value[0]) { *out = fallback; return true; }
    if (value[0] == '-') return false;
    errno = 0;
    char *end;
    const unsigned long number = std::strtoul(value, &end, 10);
    if (errno || *end || end == value || number > UINT32_MAX) return false;
    *out = static_cast<uint32_t>(number);
    return true;
}
bool decimal(const char *key, float fallback, float *out) {
    char value[PROP_VALUE_MAX];
    if (!prop_read(key, value)) return false;
    if (!value[0]) { *out = fallback; return true; }
    errno = 0;
    char *end;
    *out = std::strtof(value, &end);
    return !errno && end != value && !*end;
}
int hex(char c) {
    if (c >= '0' && c <= '9') return c - '0';
    if (c >= 'a' && c <= 'f') return c - 'a' + 10;
    return -1;
}
bool set_number(const char *key, uint32_t value) {
    char text[32];
    std::snprintf(text, sizeof(text), "%u", value);
    return prop_set(key, text);
}
} // namespace
bool read_committed_plan(Plan *out, uint32_t *sequence) {
    uint32_t before, after, sampler, lut_mode, threshold, count;
    Plan candidate;
    if (!integer("seq", 0, &before) || before & 1u ||
        !integer("sampler", 0, &sampler) || !decimal("peak_weight", 0, &candidate.peak_weight) ||
        !integer("lut_mode", 0, &lut_mode)) return false;
    candidate.enabled = true; // enable/bypass is an independent live gate
    candidate.sampler = static_cast<Sampler>(sampler);
    if (lut_mode == 1) {
        float gamma;
        if (!integer("lut_threshold", 20, &threshold) || !decimal("lut_gamma", 1, &gamma) ||
            !make_curve(threshold, gamma, &candidate.lut)) return false;
    } else if (lut_mode == 2) {
        if (!integer("lut_count", 0, &count) || count < 2 || count > 256) return false;
        char joined[1025] = {};
        size_t length = 0;
        for (size_t i = 0; length < count * 4 && i < 13; ++i) {
            char key[16], chunk[PROP_VALUE_MAX];
            std::snprintf(key, sizeof(key), "lut%zu", i);
            if (!prop_read(key, chunk)) return false;
            const size_t n = std::strlen(chunk);
            if (n != (count * 4 - length < 80 ? count * 4 - length : 80)) return false;
            std::memcpy(joined + length, chunk, n);
            length += n;
        }
        if (length != count * 4) return false;
        candidate.lut.count = count;
        for (size_t i = 0; i < count; ++i) {
            uint16_t code = 0;
            for (size_t j = 0; j < 4; ++j) {
                const int n = hex(joined[i * 4 + j]);
                if (n < 0) return false;
                code = static_cast<uint16_t>((code << 4) | n);
            }
            candidate.lut.codes[i] = code;
        }
    } else if (lut_mode != 0) return false;
    if (!valid_plan(candidate) || !integer("seq", 0, &after) || before != after) return false;
    *out = candidate;
    *sequence = after;
    return true;
}
CurveSettings read_curve_settings(const Plan &plan) {
    CurveSettings curve;
    if (!plan.lut.count) return curve;
    curve.known = false;
    uint32_t threshold;
    float gamma;
    Lut expected;
    if (integer("lut_threshold", 20, &threshold) && decimal("lut_gamma", 1, &gamma) &&
        make_curve(threshold, gamma, &expected) && expected.count == plan.lut.count &&
        std::memcmp(expected.codes, plan.lut.codes, expected.count * sizeof(uint16_t)) == 0) {
        curve = {true, threshold, gamma};
    }
    return curve;
}
bool publish_properties(const Plan &plan, const CurveSettings *curve) {
    if (!valid_plan(plan)) return false;
    uint32_t seq;
    if (!integer("seq", 0, &seq)) return false;
    // Reader never accepts an odd sequence; completed snapshots use even values.
    seq = (seq & ~1u) + 2u;
    if (!set_number("seq", seq - 1)) return false;
    char weight[32];
    std::snprintf(weight, sizeof(weight), "%.9g", static_cast<double>(plan.peak_weight));
    if (!set_number("sampler", static_cast<uint32_t>(plan.sampler)) ||
        !prop_set("peak_weight", weight) || !set_number("lut_mode", plan.lut.count ? 2 : 0) ||
        !set_number("lut_count", static_cast<uint32_t>(plan.lut.count))) return false;
    char encoded[1025] = {};
    for (size_t i = 0; i < plan.lut.count; ++i)
        std::snprintf(encoded + i * 4, 5, "%04x", plan.lut.codes[i]);
    size_t at = 0;
    for (size_t i = 0; i < 13; ++i) {
        char key[16], chunk[81] = {};
        std::snprintf(key, sizeof(key), "lut%zu", i);
        const size_t remaining = plan.lut.count * 4 - at;
        const size_t n = remaining < 80 ? remaining : 80;
        std::memcpy(chunk, encoded + at, n);
        at += n;
        if (!prop_set(key, chunk)) return false;
    }
    if (curve) {
        char gamma[32];
        std::snprintf(gamma, sizeof(gamma), "%.9g", static_cast<double>(curve->gamma));
        if (!(curve->known ? set_number("lut_threshold", curve->threshold) : prop_set("lut_threshold", "")) ||
            !prop_set("lut_gamma", curve->known ? gamma : "")) return false;
    }
    return set_number("seq", seq);
}
} // namespace quest_ld
