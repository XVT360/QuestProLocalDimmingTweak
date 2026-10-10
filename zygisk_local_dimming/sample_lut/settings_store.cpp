#include "settings.h"
#include <sys/stat.h>
#include <sys/file.h>
#include <fcntl.h>
#include <unistd.h>
#include <cerrno>
#include <cstdio>

namespace quest_ld {
namespace {
constexpr const char *directory = "/data/adb/questpro_local_dimming_030";
constexpr const char *file = "settings.bin", *temporary = "settings.bin.tmp";
bool private_file(int fd) {
    struct stat info{};
    return fstat(fd, &info) == 0 && S_ISREG(info.st_mode) && info.st_uid == 0 && (info.st_mode & 0077) == 0;
}
int open_directory(bool create) {
    if (create && mkdir(directory, 0700) != 0 && errno != EEXIST) return -1;
    const int fd = open(directory, O_RDONLY | O_DIRECTORY | O_NOFOLLOW | O_CLOEXEC);
    if (fd < 0) return -1;
    struct stat info{};
    if (fstat(fd, &info) || info.st_uid != 0 || !S_ISDIR(info.st_mode) ||
        (create ? fchmod(fd, 0700) != 0 : (info.st_mode & 0077) != 0)) {
        close(fd);
        errno = EACCES;
        return -1;
    }
    return fd;
}
} // namespace
int lock_settings() {
    const int dir = open_directory(true);
    if (dir < 0) return -1;
    const int fd = openat(dir, "writer.lock", O_CREAT | O_RDWR | O_NOFOLLOW | O_CLOEXEC, 0600);
    close(dir);
    if (fd < 0) return -1;
    if (!private_file(fd)) { close(fd); return -1; }
    // A bounded lock wait keeps a broken writer from blocking the controller.
    for (size_t i = 0; i < 20; ++i) {
        if (flock(fd, LOCK_EX | LOCK_NB) == 0) return fd;
        if (errno != EWOULDBLOCK && errno != EAGAIN) break;
        usleep(50000);
    }
    close(fd);
    return -1;
}
LoadResult load_settings(Settings *out) {
    const int dir = open_directory(false);
    if (dir < 0) return errno == ENOENT ? LoadResult::Missing : LoadResult::IoError;
    const int fd = openat(dir, file, O_RDONLY | O_NOFOLLOW | O_CLOEXEC);
    const int error = errno;
    close(dir);
    if (fd < 0) return error == ENOENT ? LoadResult::Missing : LoadResult::IoError;
    struct stat info{};
    if (!private_file(fd) || fstat(fd, &info) || info.st_size < 60 || info.st_size > static_cast<off_t>(kSettingsCapacity)) {
        close(fd); return LoadResult::Invalid;
    }
    uint8_t bytes[kSettingsCapacity];
    size_t at = 0;
    const size_t length = static_cast<size_t>(info.st_size);
    while (at < length) {
        const ssize_t n = read(fd, bytes + at, length - at);
        if (n < 0 && errno == EINTR) continue;
        if (n <= 0) { close(fd); return LoadResult::IoError; }
        at += static_cast<size_t>(n);
    }
    uint8_t extra;
    const ssize_t tail = read(fd, &extra, 1);
    close(fd);
    if (tail != 0) return LoadResult::Invalid;
    return decode_settings(bytes, length, out) ? LoadResult::Good : LoadResult::Invalid;
}
void cancel_settings(PendingSettings *pending) {
    if (pending->directory >= 0) {
        unlinkat(pending->directory, temporary, 0);
        close(pending->directory);
        pending->directory = -1;
    }
}
bool stage_settings(const Settings &settings, PendingSettings *pending) {
    uint8_t bytes[kSettingsCapacity];
    size_t length;
    if (!encode_settings(settings, bytes, sizeof(bytes), &length)) return false;
    pending->directory = open_directory(true);
    if (pending->directory < 0) return false;
    // A crashed writer may leave a temporary file. Remove it, then create a
    // fresh file exclusively so a hostile link can never be truncated.
    if (unlinkat(pending->directory, temporary, 0) != 0 && errno != ENOENT) {
        cancel_settings(pending); return false;
    }
    const int fd = openat(pending->directory, temporary, O_WRONLY | O_CREAT | O_EXCL | O_NOFOLLOW | O_CLOEXEC, 0600);
    if (fd < 0) { cancel_settings(pending); return false; }
    bool good = private_file(fd);
    size_t at = 0;
    while (good && at < length) {
        const ssize_t n = write(fd, bytes + at, length - at);
        if (n < 0 && errno == EINTR) continue;
        if (n <= 0) good = false;
        else at += static_cast<size_t>(n);
    }
    if (good) good = fsync(fd) == 0;
    if (close(fd) != 0) good = false;
    if (!good) cancel_settings(pending);
    return good;
}
bool finish_settings(PendingSettings *pending) {
    if (pending->directory < 0) return false;
    if (renameat(pending->directory, temporary, pending->directory, file) != 0) {
        cancel_settings(pending); return false;
    }
    const bool good = fsync(pending->directory) == 0;
    close(pending->directory);
    pending->directory = -1;
    return good;
}
void print_saved_settings() {
    Settings saved, live;
    const LoadResult result = load_settings(&saved);
    std::printf("settings_saved=%d\nsettings_valid=%d\nsettings_match=%d\n",
        result != LoadResult::Missing, result == LoadResult::Good,
        result == LoadResult::Good && read_live_settings(&live) && same_settings(saved, live));
}
} // namespace quest_ld
