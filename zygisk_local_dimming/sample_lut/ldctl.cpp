#include "settings.h"
#include <sys/system_properties.h>
#include <cstdio>
#include <cstring>
#include <unistd.h>

using namespace quest_ld;
static void usage() {
    std::fprintf(stderr, "ldctl status | disable | reset | reset-all | save | restore | sampler native|mean|peak|blend [weight] | lut-native | lut-curve threshold gamma | debug X Y gaussian smooth weight | debug-reset\n");
}
static int fail(const char *message, int code = 1) {
    std::fprintf(stderr, "%s\n", message);
    return code;
}
static bool sampler(const char *text, Sampler *out) {
    const char *names[] = {"native", "mean", "peak", "blend"};
    for (uint32_t i = 0; i < 4; ++i) {
        if (std::strcmp(text, names[i]) == 0) { *out = static_cast<Sampler>(i); return true; }
    }
    return false;
}
static bool curve(const char *threshold, const char *gamma, Settings *settings) {
    uint32_t t;
    float g;
    if (!parse_uint(threshold, 255, &t) || t < 1 || !parse_float(gamma, 0.1f, 8.0f, &g) ||
        !make_curve(t, g, &settings->plan.lut)) return false;
    settings->curve = {true, t, g};
    return true;
}
static bool debug(char **arguments, DebugSettings *out) {
    DebugSettings d;
    if (!parse_uint(arguments[0], kMaxDilateX, &d.x) || !parse_uint(arguments[1], kMaxDilateY, &d.y) ||
        !parse_uint(arguments[2], kMaxGaussian, &d.gaussian) || !parse_uint(arguments[3], 1, &d.smooth) ||
        !parse_float(arguments[4], 0, kMaxSmoothWeight, &d.weight) || !valid_debug(d)) return false;
    *out = d;
    return true;
}
static bool inactive_gates() {
    const char *keys[] = {"enable", "hook_mode", "bypass"};
    const char *defaults[] = {"0", "0", "1"};
    char value[PROP_VALUE_MAX];
    for (size_t i = 0; i < 3; ++i) {
        if (!prop_read(keys[i], value) || (value[0] && std::strcmp(value, defaults[i]) != 0)) return false;
    }
    return true;
}
static int commit(const Settings &settings, bool plan_changed, bool debug_changed) {
    // Stage and fsync the full bounded snapshot before changing live properties.
    PendingSettings pending;
    if (!stage_settings(settings, &pending)) return fail("Cannot save settings; live parameters unchanged");
    DebugSettings before{};
    // External ADB may have left an invalid value. Use the pinned firmware
    // defaults as a deterministic rollback target in that case.
    read_debug(&before);
    if (debug_changed && !apply_debug(settings.debug)) {
        cancel_settings(&pending);
        return fail("Debug property update failed; saved settings unchanged");
    }
    if (plan_changed && !publish_properties(settings.plan, &settings.curve)) {
        if (debug_changed) apply_debug(before);
        cancel_settings(&pending);
        return fail("Plan publication failed; saved settings unchanged");
    }
    if (!finish_settings(&pending)) return fail("Parameters applied, but settings save failed; check status");
    std::puts("configuration committed\nsettings_saved=1");
    return 0;
}
int main(int argc, char **argv) {
    if (geteuid() != 0) return fail("root_required");
    if (argc < 2) { usage(); return 2; }
    if (std::strcmp(argv[1], "status") == 0) {
        if (argc != 2) return 2;
        char value[PROP_VALUE_MAX];
        const char *keys[] = {"enable", "bypass", "hook_mode", "seq", "sampler", "peak_weight", "lut_mode", "lut_count"};
        for (const char *key : keys) if (prop_read(key, value)) std::printf("%s=%s\n", key, value);
        Plan plan;
        uint32_t seq;
        const bool good = read_committed_plan(&plan, &seq);
        std::printf("plan_valid=%d\n", good);
        if (good) {
            const CurveSettings c = read_curve_settings(plan);
            std::printf("lut_curve_known=%d\n", c.known);
            if (c.known) std::printf("lut_threshold=%u\nlut_gamma=%.9g\n", c.threshold, static_cast<double>(c.gamma));
        }
        print_debug();
        print_saved_settings();
        return 0;
    }
    if (std::strcmp(argv[1], "disable") == 0) {
        if (argc != 2) return 2;
        const bool disabled = prop_set("enable", "0");
        const bool bypassed = prop_set("bypass", "1");
        return disabled && bypassed ? 0 : 1;
    }
    const int lock_fd = lock_settings();
    if (lock_fd < 0) return fail("Cannot serialize settings writers");
    if (std::strcmp(argv[1], "restore") == 0 && argc == 2) {
        Settings s;
        const LoadResult result = load_settings(&s);
        if (result == LoadResult::Missing) { std::puts("restore_state=empty"); return 0; }
        if (result == LoadResult::Invalid) return fail("restore_state=invalid", 2);
        if (result != LoadResult::Good) return fail("restore_state=storage_unavailable");
        // A delayed boot worker must not overwrite tuning after manual activation.
        if (!inactive_gates()) return fail("restore_state=manual_activation_detected", 3);
        if (!apply_debug(s.debug) || !publish_properties(s.plan, &s.curve)) return fail("restore_state=retry");
        std::puts("restore_state=restored");
        return 0; // never saves or changes enable, bypass or hook_mode
    }
    Settings s;
    uint32_t seq;
    bool plan_changed = false, debug_changed = false;
    const bool reset_all = std::strcmp(argv[1], "reset-all") == 0 && argc == 2;
    const bool reset_plan = std::strcmp(argv[1], "reset") == 0 && argc == 2;
    const bool debug_command = std::strcmp(argv[1], "debug") == 0 && argc == 7;
    const bool reset_debug = std::strcmp(argv[1], "debug-reset") == 0 && argc == 2;
    if (!reset_all) {
        if (!reset_plan) {
            if (!read_committed_plan(&s.plan, &seq)) return fail("Current plan invalid; use reset-all");
            s.curve = read_curve_settings(s.plan);
        }
        if (!debug_command && !reset_debug && !read_debug(&s.debug))
            return fail("Debug values outside controller bounds; use debug-reset");
    }
    if (reset_all || reset_plan) {
        s.plan = Plan{};
        s.curve = CurveSettings{};
        plan_changed = true;
        debug_changed = reset_all;
    } else if (std::strcmp(argv[1], "sampler") == 0 && (argc == 3 || argc == 4)) {
        if (!sampler(argv[2], &s.plan.sampler) || (s.plan.sampler == Sampler::Blend && argc != 4) ||
            (argc == 4 && !parse_float(argv[3], 0, 1, &s.plan.peak_weight))) return fail("Invalid sampler arguments", 2);
        plan_changed = true;
    } else if (std::strcmp(argv[1], "lut-native") == 0 && argc == 2) {
        s.plan.lut = Lut{};
        s.curve = CurveSettings{};
        plan_changed = true;
    } else if (std::strcmp(argv[1], "lut-curve") == 0 && argc == 4) {
        if (!curve(argv[2], argv[3], &s)) return fail("Invalid LUT curve", 2);
        plan_changed = true;
    } else if (debug_command || reset_debug) {
        if (debug_command && !debug(argv + 2, &s.debug)) return fail("Debug values outside bounds; smooth weight maximum is 0.30", 2);
        debug_changed = true;
    } else if (std::strcmp(argv[1], "save") == 0 && argc == 2) {
        // Explicitly adopt current properties, including an imported LUT table.
        if (!read_live_settings(&s)) return fail("Settings changed during capture; try save again");
    } else if (std::strcmp(argv[1], "apply") == 0 && (argc == 10 || argc == 12)) {
        if (!sampler(argv[2], &s.plan.sampler) || !parse_float(argv[3], 0, 1, &s.plan.peak_weight)) return 2;
        int start = 5;
        if (std::strcmp(argv[4], "curve") == 0 && argc == 12) {
            if (!curve(argv[5], argv[6], &s)) return 2;
            start = 7;
        } else if (std::strcmp(argv[4], "native") == 0 && argc == 10) {
            s.plan.lut = Lut{};
            s.curve = CurveSettings{};
        } else if (std::strcmp(argv[4], "keep") != 0 || argc != 10) return 2;
        if (!debug(argv + start, &s.debug)) return 2;
        plan_changed = debug_changed = true;
    } else {
        usage(); return 2;
    }
    if (!valid_settings(s)) return fail("Invalid settings", 2);
    return commit(s, plan_changed, debug_changed);
}
