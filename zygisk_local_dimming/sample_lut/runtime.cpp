#include "runtime.h"
#include "control.h"
#include "pinned_image.h"
#include "stage_bridge.h"
#include "stage_controller.h"
#include "range_view.h"
#include <link.h>
#include <elf.h>
#include <cstdio>
#include <cstring>
#include <atomic>
#include <unistd.h>
#include <sys/syscall.h>
#include <time.h>
#include <vector>

namespace quest_ld {
namespace {
PlanMailbox mailbox;
std::atomic<uintptr_t> ready_base{0};
std::atomic<uint64_t> samples{0}, luts{0}, rejected{0}, hits{0};
struct RangeCache {
    std::atomic_flag lock = ATOMIC_FLAG_INIT;
    std::vector<Range> rows;
} ranges;
struct FrameSlot {
    std::atomic<int> tid{0};
    uintptr_t sp = 0;
    FrameTransaction frame;
};
FrameSlot frames[32];

void refresh_ranges() {
    // Runtime commonly has thousands of mappings. Build on the worker, then
    // swap a complete snapshot; callbacks never grow or free this storage.
    std::vector<Range> next;
    next.reserve(4096);
    FILE *file = std::fopen("/proc/self/maps", "r");
    if (!file) return;
    char line[1024];
    bool complete = true;
    while (std::fgets(line, sizeof(line), file)) {
        unsigned long start, end;
        char perms[5];
        if (std::sscanf(line, "%lx-%lx %4s", &start, &end, perms) != 3) continue;
        next.push_back({start, end, perms[0] == 'r', perms[1] == 'w'});
    }
    complete = !std::ferror(file) && !next.empty();
    std::fclose(file);
    if (!complete || ranges.lock.test_and_set(std::memory_order_acquire)) return;
    ranges.rows.swap(next);
    ranges.lock.clear(std::memory_order_release);
}

bool views(uintptr_t base, uintptr_t input, RawView *raw, PairView *pair, bool sample) {
    // Snapshot lookup only: no file I/O, allocation or blocking in the callback.
    if (ranges.lock.test_and_set(std::memory_order_acquire)) return false;
    const bool global = covers(ranges.rows.data(), ranges.rows.size(), base + 0xe435d0, 16, false) &&
                        covers(ranges.rows.data(), ranges.rows.size(), base + 0xe459e8, 4, false);
    uint32_t selector = 2;
    int32_t stride = 0;
    if (global) {
        std::memcpy(&selector, reinterpret_cast<void *>(base + 0xe459e8), 4);
        std::memcpy(&stride, reinterpret_cast<void *>(base + 0xe435d0), 4);
    }
    const uintptr_t matrix = base + 0xe435e8 + static_cast<uintptr_t>(selector) * 0x1200;
    bool good = global && selector < 2 && covers(ranges.rows.data(), ranges.rows.size(), matrix, 0x1200, true);
    size_t span = 0;
    if (sample) {
        good = good && stride >= 1440 && stride <= 65536 && stride % 4 == 0;
        if (good) {
            span = 191u * static_cast<size_t>(stride) + 1440u;
            good = covers(ranges.rows.data(), ranges.rows.size(), input, span, false);
        }
    }
    ranges.lock.clear(std::memory_order_release);
    if (!good) return false;
    *pair = {reinterpret_cast<float *>(matrix), kPairCells};
    if (raw) *raw = {reinterpret_cast<const uint8_t *>(input), span, static_cast<size_t>(stride)};
    return true;
}

uint32_t dispatch(SavedContext *ctx, uint32_t stage, uintptr_t base) noexcept {
    hits.fetch_add(1, std::memory_order_relaxed);
    if (!ctx || stage > 1 || ready_base.load(std::memory_order_acquire) != base) return 0;
    const int tid = static_cast<int>(syscall(SYS_gettid));
    FrameSlot *slot = nullptr;
    for (auto &candidate : frames) {
        if (candidate.tid.load(std::memory_order_acquire) == tid && candidate.sp == ctx->original_sp) {
            slot = &candidate;
            break;
        }
    }
    if (stage == 0) {
        if (mailbox.bypassed() || ctx->fpcr != 0) {
            if (slot) slot->tid.store(0, std::memory_order_release);
            return 0;
        }
        if (!slot) {
            for (auto &candidate : frames) {
                int free = 0;
                if (candidate.tid.compare_exchange_strong(free, -1, std::memory_order_acquire)) {
                    candidate.sp = ctx->original_sp;
                    candidate.tid.store(tid, std::memory_order_release);
                    slot = &candidate;
                    break;
                }
            }
        }
        if (!slot) { rejected.fetch_add(1, std::memory_order_relaxed); return 0; }
        RawView raw{};
        PairView pair{};
        // Native-only plans also enter here to latch the later LUT settings.
        if (!views(base, ctx->x[19], &raw, &pair, true)) {
            slot->tid.store(0, std::memory_order_release);
            rejected.fetch_add(1, std::memory_order_relaxed);
            return 0;
        }
        const Route route = on_sample(slot->frame, mailbox, ctx->original_sp, raw, pair);
        if (route == Route::Replaced) {
            ctx->x[20] = base + 0xe45000;
            ctx->x[27] = base + 0xe43588;
            samples.fetch_add(1, std::memory_order_relaxed);
        } else if (route == Route::Rejected) rejected.fetch_add(1, std::memory_order_relaxed);
        return static_cast<uint32_t>(route);
    }
    if (!slot) return 0; // installed mid-frame, missing sample or no active plan
    Route route = Route::Original;
    PairView pair{};
    if (ctx->fpcr == 0 && views(base, 0, nullptr, &pair, false)) {
        route = on_lut(slot->frame, mailbox, ctx->original_sp, pair);
    } else rejected.fetch_add(1, std::memory_order_relaxed);
    slot->tid.store(0, std::memory_order_release);
    if (route == Route::Replaced) luts.fetch_add(1, std::memory_order_relaxed);
    else if (route == Route::Rejected) rejected.fetch_add(1, std::memory_order_relaxed);
    return static_cast<uint32_t>(route);
}

bool note_id(const dl_phdr_info *info) {
    for (size_t i = 0; i < info->dlpi_phnum; ++i) {
        const auto &ph = info->dlpi_phdr[i];
        if (ph.p_type != PT_NOTE || ph.p_filesz > 65536) continue;
        const uint8_t *p = reinterpret_cast<const uint8_t *>(info->dlpi_addr + ph.p_vaddr);
        size_t offset = 0;
        while (offset + sizeof(Elf64_Nhdr) <= ph.p_filesz) {
            Elf64_Nhdr note;
            std::memcpy(&note, p + offset, sizeof(note));
            offset += sizeof(note);
            const size_t names = (static_cast<size_t>(note.n_namesz) + 3) & ~size_t{3};
            const size_t descs = (static_cast<size_t>(note.n_descsz) + 3) & ~size_t{3};
            if (names > ph.p_filesz - offset || descs > ph.p_filesz - offset - names) break;
            if (note.n_type == NT_GNU_BUILD_ID && note.n_namesz == 4 &&
                note.n_descsz == sizeof(kBuildId) && std::memcmp(p + offset, "GNU", 4) == 0 &&
                std::memcmp(p + offset + names, kBuildId, sizeof(kBuildId)) == 0) return true;
            offset += names + descs;
        }
    }
    return false;
}
int inspect(dl_phdr_info *info, size_t, void *opaque) {
    if (!info->dlpi_name || !std::strstr(info->dlpi_name, "libvrruntimeservice.so") || !note_id(info)) return 0;
    const uintptr_t base = info->dlpi_addr;
    bool code = false, data = false;
    for (size_t i = 0; i < info->dlpi_phnum; ++i) {
        const auto &p = info->dlpi_phdr[i];
        if (p.p_type != PT_LOAD) continue;
        if ((p.p_flags & (PF_R | PF_X)) == (PF_R | PF_X) &&
            p.p_vaddr <= 0x72e908 && p.p_vaddr + p.p_memsz >= 0x72f970) code = true;
        if ((p.p_flags & (PF_R | PF_W)) == (PF_R | PF_W) &&
            p.p_vaddr <= 0xe435d0 && p.p_vaddr + p.p_memsz >= 0xe46c88) data = true;
    }
    if (!code || !data || std::memcmp(reinterpret_cast<void *>(base + 0x72e908), kSampleFingerprint, 64) ||
        std::memcmp(reinterpret_cast<void *>(base + 0x72f930), kLutFingerprint, 64)) return 0;
    static_cast<RuntimeImage *>(opaque)->base = base;
    return 1;
}
} // namespace

bool find_image(RuntimeImage *out) {
    dl_iterate_phdr(inspect, out);
    return out->base != 0;
}
uintptr_t callback_address() { return reinterpret_cast<uintptr_t>(&dispatch); }
void runtime_ready(uintptr_t base) { ready_base.store(base, std::memory_order_release); }

void *runtime_worker(void *fd_value) {
    const int fd = static_cast<int>(reinterpret_cast<intptr_t>(fd_value));
    const bool install_requested = switch_on("hook_mode");
    if (fd >= 0) dprintf(fd, "startup pid=%d version=%s hook_requested=%d\n", getpid(), kModuleVersion, install_requested);
    bool ready = false, attempted = false, have_plan = false;
    uint32_t applied = UINT32_MAX;
    const timespec delay{0, 100000000};
    for (uint64_t tick = 0;; ++tick) {
        if (install_requested && !attempted) {
            RuntimeImage image;
            if (find_image(&image)) {
                attempted = true;
                ready = install_bridges(image, fd);
            } else if (tick == 300) {
                attempted = true;
                if (fd >= 0) dprintf(fd, "hook_refused reason=pinned_image_not_found\n");
            }
        }
        const bool enable = ready && switch_on("enable") && !switch_on("bypass");
        if (!enable) mailbox.bypass(true);
        if (tick % 10 == 0 || enable) refresh_ranges();
        Plan plan;
        uint32_t seq;
        if (read_committed_plan(&plan, &seq) && (seq != applied || !have_plan)) {
            if (mailbox.try_publish(plan)) {
                applied = seq;
                have_plan = true;
                if (fd >= 0) dprintf(fd, "config_committed seq=%u sampler=%u peak_weight=%.6g lut_entries=%zu\n",
                    seq, static_cast<unsigned>(plan.sampler), static_cast<double>(plan.peak_weight), plan.lut.count);
            }
        }
        mailbox.bypass(!(enable && have_plan));
        if (tick % 20 == 0 && fd >= 0) dprintf(fd,
            "status pid=%d ready=%d enable=%d seq=%u hits=%llu sample_writes=%llu lut_writes=%llu rejected=%llu\n",
            getpid(), ready, !mailbox.bypassed(), applied,
            static_cast<unsigned long long>(hits.load()), static_cast<unsigned long long>(samples.load()),
            static_cast<unsigned long long>(luts.load()), static_cast<unsigned long long>(rejected.load()));
        nanosleep(&delay, nullptr);
    }
}
} // namespace quest_ld
