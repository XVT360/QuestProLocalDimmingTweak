#include "zygisk.hpp"
#include "runtime.h"
#include <fcntl.h>
#include <unistd.h>
#include <cstring>
#include <pthread.h>

namespace {
class Module : public zygisk::ModuleBase {
    zygisk::Api *api_ = nullptr;
    JNIEnv *env_ = nullptr;
    bool target_ = false;
    int fd_ = -1;
public:
    void onLoad(zygisk::Api *api, JNIEnv *env) override { api_ = api; env_ = env; }
    void preAppSpecialize(zygisk::AppSpecializeArgs *args) override {
        if (!args || !args->nice_name || !env_ || !api_) return;
        const char *name = env_->GetStringUTFChars(args->nice_name, nullptr);
        target_ = name && std::strcmp(name, "com.oculus.vrruntimeservice") == 0;
        if (name) env_->ReleaseStringUTFChars(args->nice_name, name);
        if (!target_) { api_->setOption(zygisk::DLCLOSE_MODULE_LIBRARY); return; }
        const int dir = api_->getModuleDir();
        if (dir >= 0) {
            fd_ = openat(dir, "log/zygisk_trace.log", O_CREAT | O_WRONLY | O_APPEND | O_CLOEXEC, 0600);
            close(dir);
        }
        if (fd_ >= 0 && !api_->exemptFd(fd_)) { close(fd_); fd_ = -1; }
    }
    void postAppSpecialize(const zygisk::AppSpecializeArgs *) override {
        if (!target_) return;
        pthread_t thread;
        if (pthread_create(&thread, nullptr, quest_ld::runtime_worker,
                           reinterpret_cast<void *>(static_cast<intptr_t>(fd_))) == 0) {
            pthread_detach(thread);
            fd_ = -1;
        } else if (fd_ >= 0) { close(fd_); fd_ = -1; }
    }
};
} // namespace
REGISTER_ZYGISK_MODULE(Module)
