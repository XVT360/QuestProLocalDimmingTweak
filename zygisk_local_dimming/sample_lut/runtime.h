#pragma once
#include <cstdint>
#include <cstddef>

namespace quest_ld {
struct RuntimeImage { uintptr_t base = 0; };
bool find_image(RuntimeImage *out);
bool install_bridges(const RuntimeImage &image, int trace_fd);
void *runtime_worker(void *fd_value);
void runtime_ready(uintptr_t base);
uintptr_t callback_address();
} // namespace quest_ld
