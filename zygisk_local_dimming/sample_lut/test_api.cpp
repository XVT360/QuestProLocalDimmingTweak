#include "sample_lut_core.h"
#include "stage_controller.h"
#include "stage_bridge.h"
#include "range_view.h"
extern "C" {
__attribute__((visibility("default"))) int test_ranges(const quest_ld::Range *ranges, size_t count,
    uintptr_t at, size_t bytes, uint32_t writable) {
    return quest_ld::covers(ranges, count, at, bytes, writable != 0);
}
__attribute__((visibility("default"))) int test_sample(const uint8_t *raw, size_t bytes, size_t stride,
    uint32_t mode, float weight, float *out) {
    quest_ld::Plan plan;
    plan.sampler = static_cast<quest_ld::Sampler>(mode); plan.peak_weight = weight;
    return quest_ld::sample_pair({raw, bytes, stride}, plan, out, 1152);
}
__attribute__((visibility("default"))) int test_lut(const float *in, const uint16_t *codes, size_t count, float *out) {
    quest_ld::Lut lut;
    if (count > 256) return 0;
    lut.count = count;
    for (size_t i = 0; i < count; ++i) lut.codes[i] = codes[i];
    return quest_ld::map_pair(in, 1152, lut, out, 1152);
}
__attribute__((visibility("default"))) int test_curve(uint32_t threshold, float gamma, uint16_t *out) {
    quest_ld::Lut lut;
    if (!quest_ld::make_curve(threshold, gamma, &lut)) return 0;
    for (size_t i = 0; i < lut.count; ++i) out[i] = lut.codes[i];
    return static_cast<int>(lut.count);
}
__attribute__((visibility("default"))) int test_controller(const uint8_t *raw, size_t bytes, size_t stride,
    float *pair, uint32_t sampler, uint32_t use_lut, uint32_t arm) {
    quest_ld::Plan plan;
    plan.enabled = true;
    plan.sampler = static_cast<quest_ld::Sampler>(sampler);
    if (use_lut && !quest_ld::make_curve(20, 1, &plan.lut)) return -1;
    quest_ld::PlanMailbox box;
    quest_ld::FrameTransaction frame;
    if (!box.try_publish(plan)) return -2;
    box.bypass(!arm);
    const auto sample = quest_ld::on_sample(frame, box, 0x1234, {raw, bytes, stride}, {pair, 1152});
    const auto lut = quest_ld::on_lut(frame, box, 0x1234, {pair, 1152});
    return static_cast<int>(sample) + 10 * static_cast<int>(lut);
}
}
