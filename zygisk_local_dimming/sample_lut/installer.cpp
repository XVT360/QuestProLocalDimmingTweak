#include "runtime.h"
#include "stage_bridge.h"
#include <atomic>
#include <cstdio>
#include <cstring>
#include <cerrno>
#include <csignal>
#include <fcntl.h>
#include <unistd.h>
#include <dirent.h>
#include <ucontext.h>
#include <sys/mman.h>
#include <sys/syscall.h>
#include <linux/futex.h>
#include <time.h>

namespace quest_ld {
namespace {
constexpr size_t kThreads = 256;
struct Parked { int tid; std::atomic<int> arrived{0}; uintptr_t pc = 0; } parked[kThreads];
std::atomic<int> parking{0};
std::atomic<int> park_failed{0};
size_t parked_count = 0;
int park_signal = 0;
static_assert(std::atomic<int>::is_always_lock_free);

void signal_park(int, siginfo_t *, void *opaque) {
    if (!parking.load(std::memory_order_acquire)) return;
    const int tid = static_cast<int>(syscall(SYS_gettid));
    Parked *slot = nullptr;
    for (size_t i = 0; i < parked_count; ++i) if (parked[i].tid == tid) { slot = &parked[i]; break; }
    if (!slot) return;
    slot->pc = static_cast<ucontext_t *>(opaque)->uc_mcontext.pc;
    slot->arrived.store(1, std::memory_order_release);
    const timespec limit{1, 0};
    while (parking.load(std::memory_order_acquire)) {
        const long result = syscall(SYS_futex, reinterpret_cast<int *>(&parking),
                                    FUTEX_WAIT_PRIVATE, 1, &limit, nullptr, 0);
        if (result < 0 && errno == ETIMEDOUT) {
            park_failed.store(1, std::memory_order_release);
            break;
        }
    }
}

void release_threads() {
    parking.store(0, std::memory_order_release);
    syscall(SYS_futex, reinterpret_cast<int *>(&parking), FUTEX_WAKE_PRIVATE, INT32_MAX, nullptr, nullptr, 0);
}
uint64_t monotonic_ns() {
    timespec value;
    syscall(SYS_clock_gettime, CLOCK_MONOTONIC, &value);
    return static_cast<uint64_t>(value.tv_sec) * 1000000000u + value.tv_nsec;
}
struct LinuxDirent {
    uint64_t ino;
    int64_t offset;
    uint16_t length;
    uint8_t type;
    char name[1];
};
// Raw syscalls keep this usable while other threads may hold libc locks.
bool task_list(int *ids, size_t *count) {
    const int fd = static_cast<int>(syscall(SYS_openat, AT_FDCWD, "/proc/self/task", O_RDONLY | O_DIRECTORY | O_CLOEXEC, 0));
    if (fd < 0) return false;
    alignas(8) char buffer[8192];
    size_t used = 0;
    bool good = true;
    for (;;) {
        const long n = syscall(SYS_getdents64, fd, buffer, sizeof(buffer));
        if (n == 0) break;
        if (n < 0) { good = false; break; }
        for (size_t off = 0; off < static_cast<size_t>(n);) {
            const auto *entry = reinterpret_cast<const LinuxDirent *>(buffer + off);
            if (entry->length < 20 || off + entry->length > static_cast<size_t>(n)) { good = false; break; }
            int tid = 0;
            const char *name = entry->name;
            while (*name >= '0' && *name <= '9') {
                if (tid > INT32_MAX / 10) { good = false; break; }
                tid = tid * 10 + *name++ - '0';
            }
            if (!*name && tid > 0) {
                if (used == kThreads) { good = false; break; }
                ids[used++] = tid;
            }
            off += entry->length;
        }
        if (!good) break;
    }
    syscall(SYS_close, fd);
    *count = used;
    return good;
}

bool pause_others(uintptr_t base) {
    int tids[kThreads];
    size_t count;
    const int own = static_cast<int>(syscall(SYS_gettid));
    if (!task_list(tids, &count)) return false;
    parked_count = 0;
    for (size_t i = 0; i < count; ++i) {
        if (tids[i] == own) continue;
        auto &slot = parked[parked_count++];
        slot.tid = tids[i]; slot.pc = 0; slot.arrived.store(0, std::memory_order_relaxed);
    }
    park_failed.store(0, std::memory_order_relaxed);
    parking.store(1, std::memory_order_release);
    for (size_t i = 0; i < parked_count; ++i) {
        if (syscall(SYS_tgkill, getpid(), parked[i].tid, park_signal) != 0) {
            release_threads(); return false;
        }
    }
    const uint64_t deadline = monotonic_ns() + 200000000;
    for (;;) {
        size_t arrived = 0;
        for (size_t i = 0; i < parked_count; ++i) arrived += parked[i].arrived.load(std::memory_order_acquire) != 0;
        if (arrived == parked_count) break;
        if (monotonic_ns() >= deadline || park_failed.load(std::memory_order_acquire)) {
            release_threads(); return false;
        }
        const timespec short_wait{0, 1000000};
        syscall(SYS_nanosleep, &short_wait, nullptr);
    }
    // Every thread in the second inventory must already be parked. Threads
    // cannot spawn further children while all creators are stopped.
    if (!task_list(tids, &count)) { release_threads(); return false; }
    for (size_t i = 0; i < count; ++i) {
        if (tids[i] == own) continue;
        bool found = false;
        for (size_t j = 0; j < parked_count; ++j)
            if (tids[i] == parked[j].tid && parked[j].arrived.load(std::memory_order_acquire)) found = true;
        if (!found) { release_threads(); return false; }
    }
    for (size_t i = 0; i < parked_count; ++i) {
        const uintptr_t pc = parked[i].pc;
        if (pc >= base + 0x72e8a4 && pc < base + 0x73027c) {
            release_threads(); return false;
        }
    }
    return !park_failed.load(std::memory_order_acquire);
}

void *allocate_near(uintptr_t site, size_t bytes, size_t page) {
    const uintptr_t low = site > 0x07000000 ? site - 0x07000000 : page;
    const uintptr_t high = site + 0x07000000;
    FILE *file = std::fopen("/proc/self/maps", "r");
    if (!file) return nullptr;
    uintptr_t cursor = low & ~(page - 1);
    char line[1024];
    void *result = nullptr;
    while (std::fgets(line, sizeof(line), file)) {
        unsigned long start, end;
        if (std::sscanf(line, "%lx-%lx", &start, &end) != 2) continue;
        if (end <= cursor) continue;
        if (start > cursor && start - cursor >= bytes && cursor + bytes < high) {
            void *memory = mmap(reinterpret_cast<void *>(cursor), bytes, PROT_READ | PROT_WRITE,
                                MAP_PRIVATE | MAP_ANONYMOUS, -1, 0);
            if (memory != MAP_FAILED) {
                if (reinterpret_cast<uintptr_t>(memory) == cursor) { result = memory; break; }
                munmap(memory, bytes);
            }
        }
        cursor = (static_cast<uintptr_t>(end) + page - 1) & ~(page - 1);
        if (cursor >= high) break;
    }
    std::fclose(file);
    return result;
}
} // namespace

bool install_bridges(const RuntimeImage &image, int trace_fd) {
    const size_t page = static_cast<size_t>(getpagesize());
    const size_t allocation = page * 2;
    void *memory = allocate_near(image.base + 0x72e908, allocation, page);
    if (!memory) { if (trace_fd >= 0) dprintf(trace_fd, "hook_refused reason=near_allocation\n"); return false; }
    PreparedBridge sample, lut;
    const uintptr_t addr = reinterpret_cast<uintptr_t>(memory);
    if (!prepare_bridge(Stage::Sample, image.base, addr, callback_address(), &sample) ||
        !prepare_bridge(Stage::Lut, image.base, addr + page, callback_address(), &lut)) {
        munmap(memory, allocation); return false;
    }
    std::memcpy(memory, sample.words, sizeof(sample.words));
    std::memcpy(reinterpret_cast<void *>(addr + page), lut.words, sizeof(lut.words));
    __builtin___clear_cache(static_cast<char *>(memory), static_cast<char *>(memory) + allocation);
    if (mprotect(memory, allocation, PROT_READ | PROT_EXEC) != 0) { munmap(memory, allocation); return false; }
    park_signal = SIGRTMIN + 6;
    struct sigaction previous{}, action{};
    if (sigaction(park_signal, nullptr, &previous) != 0 || previous.sa_handler != SIG_DFL) {
        if (trace_fd >= 0) dprintf(trace_fd, "hook_refused reason=signal_in_use\n");
        munmap(memory, allocation); return false;
    }
    action.sa_sigaction = signal_park;
    action.sa_flags = SA_SIGINFO | SA_RESTART;
    sigemptyset(&action.sa_mask);
    if (sigaction(park_signal, &action, nullptr) != 0) { munmap(memory, allocation); return false; }
    // Keep this handler alive after refusal: a pending signal must never revert
    // to its default terminating action when a thread eventually unmasks it.
    const uintptr_t pages[2] = {sample.site & ~(page - 1), lut.site & ~(page - 1)};
    bool installed = false;
    if (pause_others(image.base)) {
        auto *sample_word = reinterpret_cast<uint32_t *>(sample.site);
        auto *lut_word = reinterpret_cast<uint32_t *>(lut.site);
        const bool unchanged = *sample_word == sample.expected_instruction && *lut_word == lut.expected_instruction;
        const bool first = unchanged && syscall(SYS_mprotect, pages[0], page, PROT_READ | PROT_WRITE | PROT_EXEC) == 0;
        const bool second = first && (pages[1] == pages[0] || syscall(SYS_mprotect, pages[1], page, PROT_READ | PROT_WRITE | PROT_EXEC) == 0);
        if (second && !park_failed.load(std::memory_order_acquire)) {
            __atomic_store_n(sample_word, sample.site_branch, __ATOMIC_RELEASE);
            __atomic_store_n(lut_word, lut.site_branch, __ATOMIC_RELEASE);
            __builtin___clear_cache(reinterpret_cast<char *>(sample.site), reinterpret_cast<char *>(sample.site + 4));
            __builtin___clear_cache(reinterpret_cast<char *>(lut.site), reinterpret_cast<char *>(lut.site + 4));
            installed = *sample_word == sample.site_branch && *lut_word == lut.site_branch;
            if (!installed) {
                __atomic_store_n(sample_word, sample.expected_instruction, __ATOMIC_RELEASE);
                __atomic_store_n(lut_word, lut.expected_instruction, __ATOMIC_RELEASE);
                __builtin___clear_cache(reinterpret_cast<char *>(sample.site), reinterpret_cast<char *>(sample.site + 4));
                __builtin___clear_cache(reinterpret_cast<char *>(lut.site), reinterpret_cast<char *>(lut.site + 4));
            }
        }
        const bool protected1 = !first || syscall(SYS_mprotect, pages[0], page, PROT_READ | PROT_EXEC) == 0;
        const bool protected2 = !second || pages[1] == pages[0] || syscall(SYS_mprotect, pages[1], page, PROT_READ | PROT_EXEC) == 0;
        if (installed && protected1 && protected2) runtime_ready(image.base);
        else if (installed) {
            // Bridges stay mapped and bypassed. Do not free code still referenced
            // by a patched branch; report refusal until a fresh process starts.
            installed = false;
        }
        release_threads();
    } else release_threads();
    if (trace_fd >= 0) dprintf(trace_fd, "hook_install=%s base=0x%lx bridge=0x%lx\n",
        installed ? "ok" : "refused_bypassed", static_cast<unsigned long>(image.base), static_cast<unsigned long>(addr));
    // Keep the page for this process lifetime even after refusal/partial patch.
    return installed;
}
} // namespace quest_ld
