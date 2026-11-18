#include "runtime_profile.h"
#include "pinned_image.h"
#include "pinned_image_v204.h"

namespace quest_ld {
namespace {
constexpr RuntimeProfile profile(const char *name, uint32_t vros_build,
                                 const uint8_t (&build_id)[kBuildIdBytes],
                                 uintptr_t sample_entry, uintptr_t sample_resume,
                                 uintptr_t lut_entry, uintptr_t lut_resume,
                                 const uint8_t (&sample_fingerprint)[kFingerprintBytes],
                                 const uint8_t (&lut_fingerprint)[kFingerprintBytes],
                                 uint32_t sample_instruction, uint32_t lut_instruction,
                                 uintptr_t stride, uintptr_t selector, uintptr_t matrix,
                                 uintptr_t bridge_x20, uintptr_t bridge_x27,
                                 uintptr_t code_low, uintptr_t code_high,
                                 uintptr_t data_low, uintptr_t data_high,
                                 uintptr_t pause_low, uintptr_t pause_high) noexcept {
    return RuntimeProfile{name, vros_build, build_id,
                          sample_entry, sample_resume, lut_entry, lut_resume,
                          sample_fingerprint, lut_fingerprint,
                          sample_instruction, lut_instruction,
                          stride, selector, matrix, bridge_x20, bridge_x27,
                          code_low, code_high, data_low, data_high,
                          pause_low, pause_high};
}

// 0.5.0 shipped only the v207 image. v204 is added alongside it: both are
// reviewed and pinned, and each keeps its own identity gate. The sample/lut
// site instructions are identical in both images; only addresses differ.
constexpr RuntimeProfile kProfiles[] = {
    profile("v207", 207, kBuildId,
            0x72e908, 0x72ec4c, 0x72f930, 0x72fa98,
            kSampleFingerprint, kLutFingerprint,
            0x1e249000, 0x1e2e1000,
            0xe435d0, 0xe459e8, 0xe435e8, 0xe45000, 0xe43588,
            0x72e908, 0x72f970, 0xe435d0, 0xe46c88, 0x72e8a4, 0x73027c),
    profile("v204", 204, kBuildIdV204,
            0x7133cc, 0x713710, 0x7143f4, 0x71455c,
            kSampleFingerprintV204, kLutFingerprintV204,
            0x1e249000, 0x1e2e1000,
            0xe072f8, 0xe09710, 0xe07310, 0xe09000, 0xe072b0,
            0x7133cc, 0x714434, 0xe072f8, 0xe0a9b0, 0x713368, 0x714d40),
};
static_assert(sizeof(kProfiles) / sizeof(kProfiles[0]) == 2,
              "one table entry per reviewed runtime image");
// Both reviewed images place the selector after two 0x1200 pair blocks, which
// runtime.cpp derives from kPairCells. Keeping the check here makes a future
// profile that violates it a build failure instead of a runtime write.
static_assert(0xe459e8 - 0xe435e8 == 0x2400, "v207 selector follows two pair blocks");
static_assert(0xe09710 - 0xe07310 == 0x2400, "v204 selector follows two pair blocks");
static_assert(0xe435e8 - 0xe43588 == 0x60, "v207 matrix is x27 plus 0x60");
static_assert(0xe07310 - 0xe072b0 == 0x60, "v204 matrix is x27 plus 0x60");
} // namespace

size_t profile_count() noexcept { return sizeof(kProfiles) / sizeof(kProfiles[0]); }

const RuntimeProfile *profile_by_index(size_t index) noexcept {
    return index < profile_count() ? &kProfiles[index] : nullptr;
}

const RuntimeProfile *profile_for_build_id(const uint8_t build_id[kBuildIdBytes]) noexcept {
    if (!build_id) return nullptr;
    for (const auto &candidate : kProfiles) {
        bool same = true;
        for (size_t i = 0; i < kBuildIdBytes; ++i) {
            if (candidate.build_id[i] != build_id[i]) { same = false; break; }
        }
        if (same) return &candidate;
    }
    return nullptr;
}
} // namespace quest_ld
