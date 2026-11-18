#pragma once

#include <cstddef>
#include <cstdint>

namespace quest_ld {
// One reviewed Runtime image. Every address below is pinned evidence read from
// the image that the build-id identifies: nothing here is a guess, an offset
// applied to another firmware, or a fallback. An image whose build-id is absent
// from this table is refused before any mapping is inspected or patched.
struct RuntimeProfile {
    const char *name;   // diagnostics only
    uint32_t vros_build; // informational; never used as a gate
    const uint8_t *build_id; // kBuildIdBytes, NT_GNU_BUILD_ID
    // Hook sites: the first instruction of each stage block, and the address the
    // replacement path resumes at once that block is skipped.
    uintptr_t sample_entry, sample_resume;
    uintptr_t lut_entry, lut_resume;
    const uint8_t *sample_fingerprint; // kFingerprintBytes at sample_entry
    const uint8_t *lut_fingerprint;    // kFingerprintBytes at lut_entry
    uint32_t sample_instruction, lut_instruction;
    // Native data fields written and read by the replaced stages.
    uintptr_t stride, selector, matrix, bridge_x20, bridge_x27;
    // Mapped-memory windows that must be covered before patching is attempted.
    uintptr_t code_low, code_high;
    uintptr_t data_low, data_high;
    // A parked thread inside this range may be executing the code being patched.
    uintptr_t pause_low, pause_high;
};

constexpr const char *kModuleVersion = "0.5.0";
constexpr size_t kBuildIdBytes = 20;
constexpr size_t kFingerprintBytes = 64;

size_t profile_count() noexcept;
const RuntimeProfile *profile_by_index(size_t index) noexcept;
const RuntimeProfile *profile_for_build_id(const uint8_t build_id[kBuildIdBytes]) noexcept;
} // namespace quest_ld
