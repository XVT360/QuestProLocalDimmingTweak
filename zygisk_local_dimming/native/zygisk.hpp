/* Copyright 2022-2023 John "topjohnwu" Wu
 *
 * Permission to use, copy, modify, and/or distribute this software for any
 * purpose with or without fee is hereby granted.
 *
 * THE SOFTWARE IS PROVIDED "AS IS" AND THE AUTHOR DISCLAIMS ALL WARRANTIES WITH
 * REGARD TO THIS SOFTWARE INCLUDING ALL IMPLIED WARRANTIES OF MERCHANTABILITY
 * AND FITNESS. IN NO EVENT SHALL THE AUTHOR BE LIABLE FOR ANY SPECIAL, DIRECT,
 * INDIRECT, OR CONSEQUENTIAL DAMAGES OR ANY DAMAGES WHATSOEVER RESULTING FROM
 * LOSS OF USE, DATA OR PROFITS, WHETHER IN AN ACTION OF CONTRACT, NEGLIGENCE OR
 * OTHER TORTIOUS ACTION, ARISING OUT OF OR IN CONNECTION WITH THE USE OR
 * PERFORMANCE OF THIS SOFTWARE.
 */
// Reduced API v5 declarations adapted for this project; not the full upstream header.
#pragma once

#include <jni.h>
#include <sys/types.h>
#include <cstdint>

#define ZYGISK_API_VERSION 5

namespace zygisk {

struct Api;
struct AppSpecializeArgs;
struct ServerSpecializeArgs;

class ModuleBase {
public:
    virtual void onLoad(Api *, JNIEnv *) {}
    virtual void preAppSpecialize(AppSpecializeArgs *) {}
    virtual void postAppSpecialize(const AppSpecializeArgs *) {}
    virtual void preServerSpecialize(ServerSpecializeArgs *) {}
    virtual void postServerSpecialize(const ServerSpecializeArgs *) {}
};

struct AppSpecializeArgs {
    jint &uid;
    jint &gid;
    jintArray &gids;
    jint &runtime_flags;
    jobjectArray &rlimits;
    jint &mount_external;
    jstring &se_info;
    jstring &nice_name;
    jstring &instruction_set;
    jstring &app_data_dir;
    jintArray *const fds_to_ignore;
    jboolean *const is_child_zygote;
    jboolean *const is_top_app;
    jobjectArray *const pkg_data_info_list;
    jobjectArray *const whitelisted_data_info_list;
    jboolean *const mount_data_dirs;
    jboolean *const mount_storage_dirs;
    jboolean *const mount_sysprop_overrides;
    AppSpecializeArgs() = delete;
};

struct ServerSpecializeArgs {
    jint &uid;
    jint &gid;
    jintArray &gids;
    jint &runtime_flags;
    jlong &permitted_capabilities;
    jlong &effective_capabilities;
    ServerSpecializeArgs() = delete;
};

enum Option : int { FORCE_DENYLIST_UNMOUNT = 0, DLCLOSE_MODULE_LIBRARY = 1 };

namespace internal {
struct api_table;
template <class T> void entry_impl(api_table *, JNIEnv *);
struct module_abi {
    long api_version;
    ModuleBase *impl;
    void (*preAppSpecialize)(ModuleBase *, AppSpecializeArgs *);
    void (*postAppSpecialize)(ModuleBase *, const AppSpecializeArgs *);
    void (*preServerSpecialize)(ModuleBase *, ServerSpecializeArgs *);
    void (*postServerSpecialize)(ModuleBase *, const ServerSpecializeArgs *);
    explicit module_abi(ModuleBase *m) : api_version(ZYGISK_API_VERSION), impl(m) {
        preAppSpecialize = [](auto p, auto a) { p->preAppSpecialize(a); };
        postAppSpecialize = [](auto p, auto a) { p->postAppSpecialize(a); };
        preServerSpecialize = [](auto p, auto a) { p->preServerSpecialize(a); };
        postServerSpecialize = [](auto p, auto a) { p->postServerSpecialize(a); };
    }
};
}

struct Api {
    int connectCompanion();
    int getModuleDir();
    void setOption(Option);
    bool exemptFd(int);
    void hookJniNativeMethods(JNIEnv *, const char *, JNINativeMethod *, int);
    void pltHookRegister(dev_t, ino_t, const char *, void *, void **);
    bool pltHookCommit();
private:
    internal::api_table *tbl = nullptr;
    template <class T> friend void internal::entry_impl(internal::api_table *, JNIEnv *);
};

namespace internal {
struct api_table {
    void *impl;
    bool (*registerModule)(api_table *, module_abi *);
    void (*hookJniNativeMethods)(JNIEnv *, const char *, JNINativeMethod *, int);
    void (*pltHookRegister)(dev_t, ino_t, const char *, void *, void **);
    bool (*exemptFd)(int);
    bool (*pltHookCommit)();
    int (*connectCompanion)(void *);
    void (*setOption)(void *, Option);
    int (*getModuleDir)(void *);
    uint32_t (*getFlags)(void *);
};
template <class T>
void entry_impl(api_table *table, JNIEnv *env) {
    static Api api;
    static T module;
    static module_abi abi(&module);
    api.tbl = table;
    if (table->registerModule(table, &abi)) module.onLoad(&api, env);
}
}

inline int Api::connectCompanion() { return tbl && tbl->connectCompanion ? tbl->connectCompanion(tbl->impl) : -1; }
inline int Api::getModuleDir() { return tbl && tbl->getModuleDir ? tbl->getModuleDir(tbl->impl) : -1; }
inline void Api::setOption(Option o) { if (tbl && tbl->setOption) tbl->setOption(tbl->impl, o); }
inline bool Api::exemptFd(int fd) { return tbl && tbl->exemptFd && tbl->exemptFd(fd); }
inline void Api::hookJniNativeMethods(JNIEnv *e, const char *c, JNINativeMethod *m, int n) { if (tbl && tbl->hookJniNativeMethods) tbl->hookJniNativeMethods(e, c, m, n); }
inline void Api::pltHookRegister(dev_t d, ino_t i, const char *s, void *n, void **o) { if (tbl && tbl->pltHookRegister) tbl->pltHookRegister(d, i, s, n, o); }
inline bool Api::pltHookCommit() { return tbl && tbl->pltHookCommit && tbl->pltHookCommit(); }

#define REGISTER_ZYGISK_MODULE(clazz) /* exported entry point for Magisk */ \
__attribute__((visibility("default"))) extern "C" void zygisk_module_entry(zygisk::internal::api_table *t, JNIEnv *e) { \
    zygisk::internal::entry_impl<clazz>(t, e); \
}

} // namespace zygisk
