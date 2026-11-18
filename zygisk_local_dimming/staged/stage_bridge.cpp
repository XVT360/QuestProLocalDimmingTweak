#include "stage_bridge.h"
#include <cstring>

namespace quest_ld {
static_assert(sizeof(uintptr_t) == 8, "This bridge only supports ARM64 address width");
namespace {
bool direct_branch(uintptr_t source, uintptr_t destination, uint32_t *word) noexcept {
    if ((source | destination) & 3u) return false;
    int64_t delta;
    if (destination >= source) {
        const uintptr_t distance = destination - source;
        if (distance >= (uintptr_t{1} << 27)) return false;
        delta = static_cast<int64_t>(distance);
    } else {
        const uintptr_t distance = source - destination;
        if (distance > (uintptr_t{1} << 27)) return false;
        delta = -static_cast<int64_t>(distance);
    }
    *word = 0x14000000u | (static_cast<uint32_t>(delta / 4) & 0x03ffffffu);
    return true;
}
} // namespace

bool prepare_bridge(Stage stage, const RuntimeProfile &profile, uintptr_t image,
                    uintptr_t bridge_address, uintptr_t callback, PreparedBridge *out) noexcept {
    using namespace bridge_template;
    if (!out || !image || !bridge_address || !callback ||
        ((image | bridge_address | callback) & 3u) ||
        image > UINTPTR_MAX - profile.data_high ||
        bridge_address > UINTPTR_MAX - sizeof(kWords)) return false;
    uintptr_t entry, resume;
    uint32_t instruction;
    if (stage == Stage::Sample) {
        entry = profile.sample_entry; resume = profile.sample_resume; instruction = profile.sample_instruction;
    } else if (stage == Stage::Lut) {
        entry = profile.lut_entry; resume = profile.lut_resume; instruction = profile.lut_instruction;
    } else {
        return false;
    }
    PreparedBridge candidate{};
    std::memcpy(candidate.words, kWords, sizeof(kWords));
    candidate.site = image + entry;
    candidate.expected_instruction = instruction;
    candidate.words[k_stage] |= static_cast<uint32_t>(stage) << 5;
    candidate.words[k_original_instruction] = instruction;
    if (!direct_branch(candidate.site, bridge_address, &candidate.site_branch) ||
        !direct_branch(bridge_address + 4 * k_native_branch, candidate.site + 4,
                       &candidate.words[k_native_branch]) ||
        !direct_branch(bridge_address + 4 * k_success_branch, image + resume,
                       &candidate.words[k_success_branch])) return false;
    candidate.words[k_image_literal] = static_cast<uint32_t>(image);
    candidate.words[k_image_literal + 1] = static_cast<uint32_t>(image >> 32);
    candidate.words[k_callback_literal] = static_cast<uint32_t>(callback);
    candidate.words[k_callback_literal + 1] = static_cast<uint32_t>(callback >> 32);
    *out = candidate;
    return true;
}
} // namespace quest_ld
