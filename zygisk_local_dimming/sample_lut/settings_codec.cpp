#include "settings.h"
#include <cmath>
#include <cstring>
#include <cstdlib>
#include <cerrno>

namespace quest_ld {
namespace {
constexpr uint8_t magic[8] = {'Q','P','L','D','c','f','g','1'};
void u32(uint8_t *at, uint32_t value) {
    for (size_t i = 0; i < 4; ++i) at[i] = static_cast<uint8_t>(value >> (8 * i));
}
uint32_t u32(const uint8_t *at) {
    uint32_t value = 0;
    for (size_t i = 0; i < 4; ++i) value |= static_cast<uint32_t>(at[i]) << (8 * i);
    return value;
}
uint32_t bits(float value) { uint32_t result; std::memcpy(&result, &value, 4); return result; }
float number(uint32_t value) { float result; std::memcpy(&result, &value, 4); return result; }
uint32_t checksum(const uint8_t *bytes, size_t length) {
    uint32_t crc = UINT32_MAX;
    for (size_t i = 0; i < length; ++i) {
        crc ^= bytes[i];
        for (size_t j = 0; j < 8; ++j) crc = (crc >> 1) ^ ((crc & 1) ? 0xedb88320u : 0);
    }
    return ~crc;
}
} // namespace
bool parse_uint(const char *text, uint32_t maximum, uint32_t *out) {
    if (!text || !*text || !out) return false;
    uint32_t value = 0;
    for (const char *p = text; *p; ++p) {
        if (*p < '0' || *p > '9') return false;
        const uint32_t digit = static_cast<uint32_t>(*p - '0');
        if (digit > maximum || value > (maximum - digit) / 10) return false;
        value = value * 10 + digit;
    }
    *out = value;
    return true;
}
bool parse_float(const char *text, float minimum, float maximum, float *out) {
    if (!text || !*text || !out) return false;
    // Reject whitespace, shell metacharacters, NaN and infinity spellings.
    for (const char *p = text; *p; ++p)
        if (!(*p >= '0' && *p <= '9') && *p != '.' && *p != 'e' && *p != 'E' && *p != '+' && *p != '-') return false;
    errno = 0;
    char *end;
    const float value = std::strtof(text, &end);
    if (errno || end == text || *end || !std::isfinite(value) || value < minimum || value > maximum) return false;
    *out = value;
    return true;
}
bool valid_debug(const DebugSettings &d) {
    return d.x <= kMaxDilateX && d.y <= kMaxDilateY && d.gaussian <= kMaxGaussian && d.smooth <= 1 &&
           std::isfinite(d.weight) && d.weight >= 0.0f && d.weight <= kMaxSmoothWeight;
}
bool valid_settings(const Settings &s) {
    if (!valid_debug(s.debug) || !valid_plan(s.plan)) return false;
    if (!s.curve.known) return true;
    if (s.plan.lut.count == 0) return s.curve.threshold == 20 && s.curve.gamma == 1.0f;
    Lut expected;
    return make_curve(s.curve.threshold, s.curve.gamma, &expected) && expected.count == s.plan.lut.count &&
           std::memcmp(expected.codes, s.plan.lut.codes, expected.count * sizeof(uint16_t)) == 0;
}
bool same_settings(const Settings &a, const Settings &b) {
    return a.debug.x == b.debug.x && a.debug.y == b.debug.y && a.debug.gaussian == b.debug.gaussian &&
           a.debug.smooth == b.debug.smooth && a.debug.weight == b.debug.weight &&
           a.plan.sampler == b.plan.sampler && a.plan.peak_weight == b.plan.peak_weight &&
           a.plan.lut.count == b.plan.lut.count &&
           std::memcmp(a.plan.lut.codes, b.plan.lut.codes, a.plan.lut.count * sizeof(uint16_t)) == 0 &&
           a.curve.known == b.curve.known && (!a.curve.known ||
               (a.curve.threshold == b.curve.threshold && a.curve.gamma == b.curve.gamma));
}
bool encode_settings(const Settings &s, uint8_t *bytes, size_t capacity, size_t *length) {
    if (!bytes || !length || !valid_settings(s)) return false;
    const size_t n = 60 + s.plan.lut.count * 2;
    if (capacity < n) return false;
    std::memcpy(bytes, magic, 8);
    u32(bytes + 8, static_cast<uint32_t>(n));
    const uint32_t fields[] = {s.debug.x, s.debug.y, s.debug.gaussian, s.debug.smooth, bits(s.debug.weight),
        static_cast<uint32_t>(s.plan.sampler), bits(s.plan.peak_weight), static_cast<uint32_t>(s.plan.lut.count),
        s.curve.known ? 1u : 0u, s.curve.known ? s.curve.threshold : 20u, bits(s.curve.known ? s.curve.gamma : 1.0f)};
    for (size_t i = 0; i < 11; ++i) u32(bytes + 16 + i * 4, fields[i]);
    for (size_t i = 0; i < s.plan.lut.count; ++i) {
        bytes[60 + i * 2] = static_cast<uint8_t>(s.plan.lut.codes[i]);
        bytes[61 + i * 2] = static_cast<uint8_t>(s.plan.lut.codes[i] >> 8);
    }
    u32(bytes + 12, checksum(bytes + 16, n - 16));
    *length = n;
    return true;
}
bool decode_settings(const uint8_t *bytes, size_t length, Settings *out) {
    if (!bytes || !out || length < 60 || length > kSettingsCapacity || std::memcmp(bytes, magic, 8) ||
        u32(bytes + 8) != length || u32(bytes + 12) != checksum(bytes + 16, length - 16)) return false;
    const uint32_t count = u32(bytes + 44), known = u32(bytes + 48);
    if (count > kMaxLutEntries || length != 60 + count * 2 || known > 1) return false;
    Settings s;
    s.debug = {u32(bytes + 16), u32(bytes + 20), u32(bytes + 24), u32(bytes + 28), number(u32(bytes + 32))};
    s.plan.enabled = true; // live enable/bypass gates are deliberately not serialized
    s.plan.sampler = static_cast<Sampler>(u32(bytes + 36));
    s.plan.peak_weight = number(u32(bytes + 40));
    s.plan.lut.count = count;
    s.curve = {known == 1, u32(bytes + 52), number(u32(bytes + 56))};
    for (size_t i = 0; i < count; ++i)
        s.plan.lut.codes[i] = static_cast<uint16_t>(bytes[60 + i * 2] | (bytes[61 + i * 2] << 8));
    if (!valid_settings(s)) return false;
    *out = s;
    return true;
}
} // namespace quest_ld
