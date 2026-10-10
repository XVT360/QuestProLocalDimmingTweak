#include "stage_controller.h"
#include <cstring>

namespace quest_ld {
static_assert(std::atomic<bool>::is_always_lock_free,
              "Emergency bypass must never block the render thread");
bool PlanMailbox::try_publish(const Plan &next) noexcept {
    if (!valid_plan(next) || lock_.test_and_set(std::memory_order_acquire)) return false;
    current_ = next;
    lock_.clear(std::memory_order_release);
    return true;
}

bool PlanMailbox::try_snapshot(Plan *out) const noexcept {
    if (!out || lock_.test_and_set(std::memory_order_acquire)) return false;
    *out = current_;
    lock_.clear(std::memory_order_release);
    return true;
}

Route on_sample(FrameTransaction &frame, const PlanMailbox &mailbox,
                uintptr_t cookie, RawView raw, PairView current) noexcept {
    frame.active = false;
    frame.cookie = cookie;
    if (!cookie || mailbox.bypassed()) return Route::Original;
    if (!mailbox.try_snapshot(&frame.plan)) return Route::Original;
    if (!frame.plan.enabled) return Route::Original;
    frame.active = true;
    if (frame.plan.sampler == Sampler::Native) return Route::Original;
    if (!current.data || current.cells != kPairCells ||
        !sample_pair(raw, frame.plan, frame.scratch, kPairCells)) {
        frame.active = false; // reject both replacements for this frame
        return Route::Rejected;
    }
    if (mailbox.bypassed()) {
        frame.active = false;
        return Route::Original;
    }
    // No native selector/history changes. Both eyes complete before commit.
    std::memcpy(current.data, frame.scratch, sizeof(frame.scratch));
    return Route::Replaced;
}

Route on_lut(FrameTransaction &frame, const PlanMailbox &mailbox,
             uintptr_t cookie, PairView current) noexcept {
    if (!frame.active) return Route::Original;
    if (!cookie || frame.cookie != cookie) {
        frame.active = false;
        return Route::Rejected;
    }
    frame.active = false; // no duplicate commit at a later callback
    if (mailbox.bypassed() || frame.plan.lut.count == 0) return Route::Original;
    if (!current.data || current.cells != kPairCells ||
        !map_pair(current.data, current.cells, frame.plan.lut, frame.scratch, kPairCells)) {
        return Route::Rejected;
    }
    if (mailbox.bypassed()) return Route::Original;
    std::memcpy(current.data, frame.scratch, sizeof(frame.scratch));
    return Route::Replaced;
}
} // namespace quest_ld
