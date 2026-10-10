LOCAL_PATH := $(call my-dir)
include $(CLEAR_VARS)
LOCAL_MODULE := questpro_sample_lut
LOCAL_SRC_FILES := module.cpp runtime.cpp installer.cpp control.cpp ../staged/sample_lut_core.cpp ../staged/stage_controller.cpp ../staged/stage_bridge.cpp
LOCAL_C_INCLUDES := $(LOCAL_PATH)/../native $(LOCAL_PATH)/../staged
LOCAL_CPPFLAGS := -std=c++17 -O2 -fvisibility=hidden -fno-exceptions -fno-rtti -ffp-contract=off -fno-fast-math
LOCAL_CFLAGS := -Wall -Wextra -Werror
LOCAL_LDLIBS := -llog -ldl -lm
LOCAL_LDFLAGS := -Wl,--exclude-libs,ALL
include $(BUILD_SHARED_LIBRARY)

include $(CLEAR_VARS)
LOCAL_MODULE := settings_test
LOCAL_SRC_FILES := settings_test_api.cpp ldctl.cpp control.cpp settings_codec.cpp settings_properties.cpp settings_store.cpp ../staged/sample_lut_core.cpp
LOCAL_C_INCLUDES := $(LOCAL_PATH)/../staged
LOCAL_CPPFLAGS := -std=c++17 -Dmain=ldctl_entry -O2 -fno-exceptions -fno-rtti -ffp-contract=off -fno-fast-math
LOCAL_CFLAGS := -Wall -Wextra -Werror
LOCAL_LDLIBS := -lm
include $(BUILD_SHARED_LIBRARY)

include $(CLEAR_VARS)
LOCAL_MODULE := ldctl
LOCAL_SRC_FILES := ldctl.cpp control.cpp settings_codec.cpp settings_properties.cpp settings_store.cpp ../staged/sample_lut_core.cpp
LOCAL_C_INCLUDES := $(LOCAL_PATH)/../staged
LOCAL_CPPFLAGS := -std=c++17 -O2 -fno-exceptions -fno-rtti -ffp-contract=off -fno-fast-math
LOCAL_CFLAGS := -Wall -Wextra -Werror
LOCAL_LDLIBS := -lm
include $(BUILD_EXECUTABLE)

include $(CLEAR_VARS)
LOCAL_MODULE := sample_lut_test
LOCAL_SRC_FILES := test_api.cpp ../staged/sample_lut_core.cpp ../staged/stage_controller.cpp ../staged/stage_bridge.cpp
LOCAL_C_INCLUDES := $(LOCAL_PATH)/../staged
LOCAL_CPPFLAGS := -std=c++17 -O2 -fno-exceptions -fno-rtti -ffp-contract=off -fno-fast-math
LOCAL_CFLAGS := -Wall -Wextra -Werror
LOCAL_LDLIBS := -lm
include $(BUILD_SHARED_LIBRARY)
