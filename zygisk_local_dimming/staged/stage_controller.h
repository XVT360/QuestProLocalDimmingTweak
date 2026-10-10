#pragma once

#include "sample_lut_core.h"
#include <atomic>

namespace quest_ld {
// Publication is nonblocking for the render thread. A failed publish is
// reported to the control thread; it must retry later rather than claim success.
// All Android property/file parsing stays outside this class.
class PlanMailbox {
public:
    bool try_publish(const Plan &next) noexcept;
    bool try_snapshot(Plan *out) const noexcept;
    void bypass(bool value) noexcept { bypass_.store(value, std::memory_order_release); }
    bool bypassed() const noexcept { return bypass_.load(std::memory_order_acquire); }
private:
    mutable std::atomic_flag lock_ = ATOMIC_FLAG_INIT;
    Plan current_{};
    // Explicit arming required even after a plan is published.
    std::atomic<bool> bypass_{true};
};

struct PairView {
    float *data;
    size_t cells;
    // This view must have been resolved from the current native selector at
    // the actual stage, with lifetime/range ownership verified by the adapter.
};

struct FrameTransaction {
    uintptr_t cookie = 0;
    bool active = false;
    Plan plan{};
    float scratch[kPairCells] = {};
};

enum class Route : uint32_t { Original = 0, Replaced = 1, Rejected = 2 };

// Caller owns a transaction per executing frame (not one shared global).
// Never reuse a transaction while another invocation is between the stages.
// cookie is a validated frame identity, not the selector or source pointer.
// Original/Rejected must take the original instruction path; Replaced alone
// permits skipping the corresponding original block. See SAMPLE_LUT_PLAN.md.
Route on_sample(FrameTransaction &frame, const PlanMailbox &mailbox,
                uintptr_t cookie, RawView raw, PairView current) noexcept;
Route on_lut(FrameTransaction &frame, const PlanMailbox &mailbox,
             uintptr_t cookie, PairView current) noexcept;
} // namespace quest_ld
