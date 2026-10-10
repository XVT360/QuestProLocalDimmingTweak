#pragma once
#include <cstddef>
#include <cstdint>

namespace quest_ld {
struct Range { uintptr_t start, end; bool read, write; };

inline bool covers(const Range *rows, size_t count, uintptr_t at, size_t bytes,
                   bool writable) noexcept {
    if (!at || !bytes || at > UINTPTR_MAX - bytes) return false;
    const uintptr_t end = at + bytes;
    for (size_t i = 0; i < count && at < end; ++i) {
        if (rows[i].end <= at) continue;
        if (rows[i].start > at || !rows[i].read || (writable && !rows[i].write)) return false;
        at = rows[i].end;
    }
    return at >= end;
}
} // namespace quest_ld
