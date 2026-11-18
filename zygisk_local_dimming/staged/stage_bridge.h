#pragma once

#include "stage_bridge_words.h"
#include "runtime_profile.h"
#include <cstddef>
#include <cstdint>

namespace quest_ld {
enum class Stage : uint32_t { Sample = 0, Lut = 1 };

struct alignas(16) SavedContext {
    uint64_t x[31];
    uint64_t original_sp;
    struct { uint64_t lo, hi; } q[32];
    uint64_t nzcv;
    uint64_t fpcr;
    uint64_t fpsr;
    uint64_t reserved;
};
static_assert(sizeof(SavedContext) == 0x320);
static_assert(offsetof(SavedContext, original_sp) == 0xf8);
static_assert(offsetof(SavedContext, q) == 0x100);
static_assert(offsetof(SavedContext, nzcv) == 0x300);
static_assert(offsetof(SavedContext, fpcr) == 0x308);
static_assert(offsetof(SavedContext, fpsr) == 0x310);

// Callback ABI: uint32_t callback(SavedContext*, uint32_t stage, uintptr_t base).
// Only return value 1 skips the native stage. Everything else replays it.
// Successful Sample MUST set saved x20=base+profile.bridge_x20 and
// x27=base+profile.bridge_x27. All other saved registers/flags must remain
// unchanged. Baseline arithmetic was verified with FPCR=0 only; other FPCR
// values must initially bypass. Reentrancy, validated matrix lifetimes and
// FrameTransaction ownership belong to the future adapter, not this
// byte-template preparer.

struct PreparedBridge {
    uint32_t words[sizeof(bridge_template::kWords) / sizeof(uint32_t)];
    uintptr_t site;
    uint32_t expected_instruction;
    uint32_t site_branch;
};

// Prepares DATA ONLY. Does not allocate executable pages, patch a process,
// change protections, register a hook or flush instruction caches.
// The eventual installer must validate the full library/entry identity and
// safe install time, then verify read-back and publish both stages together.
bool prepare_bridge(Stage stage, const RuntimeProfile &profile, uintptr_t image,
                    uintptr_t bridge_address, uintptr_t callback, PreparedBridge *out) noexcept;
} // namespace quest_ld
