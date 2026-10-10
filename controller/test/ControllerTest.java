package com.questpro.ldcontrol;

public final class ControllerTest {
    private static void check(boolean condition, String name) {
        if (!condition) throw new AssertionError(name);
    }
    public static void main(String[] args) {
        String common = "version=0.5.0\nmodule_disabled=0\nmodule_update_pending=0\nplan_valid=1\n";
        ControllerState ready = new ControllerState(common +
                "enable=1\nbypass=0\nsampler=3\npeak_weight=0.25\nruntime_pid=18545\n" +
                "status pid=18545 ready=1 enable=1 sample_writes=50 lut_writes=20 rejected=0\n");
        check(ready.canEnable() && ready.active(), "ready active process");
        check(ready.decimal("peak_weight", 0) == 0.25f, "weight parsing");
        ControllerState stale = new ControllerState(common + "runtime_pid=99\n" +
                "status pid=18545 ready=1\n");
        check(!stale.canEnable() && stale.frame.isEmpty(), "old Runtime status must not enable");
        check(!new ControllerState(common + "runtime_pid=0\nstatus pid=0 ready=1\n").ready(), "absent PID");
        check(!new ControllerState(common.replace("module_disabled=0", "module_disabled=1")).usable(), "disabled module");
        check(!new ControllerState(common.replace("module_update_pending=0", "module_update_pending=1")).usable(), "pending upgrade");
        check(!new ControllerState(common.replace("version=0.5.0", "version=0.4.0")).usable(), "unsupported helper version");
        check(!new ControllerState("enable=1\nbypass=1").active(), "bypass overrides enable");
        check(new ControllerState("peak_weight=NaN").decimal("peak_weight", 3) == 3, "NaN rejected");
        check(DebugParameters.valid(1, 2, 3, 1, 0.3f), "exact native weight ceiling accepted");
        check(DebugParameters.valid(0, 0, 0, 0, 0), "debug bypass controls accepted");
        check(!DebugParameters.valid(1, 2, 3, 1, Math.nextUp(0.3f)), "next binary32 above default rejected");
        check(!DebugParameters.valid(1, 2, 3, 1, Float.NaN), "NaN weight rejected");
        check(!DebugParameters.valid(1, 2, 3, 1, Float.POSITIVE_INFINITY), "infinite weight rejected");
        check(!DebugParameters.valid(9, 2, 3, 1, 0.3f), "empty dilation interior excluded");
        check(!DebugParameters.valid(1, 16, 3, 1, 0.3f), "empty vertical interior excluded");
        check(!DebugParameters.valid(1, 2, 10, 1, 0.3f), "oversized GUI Gaussian excluded");
        check(new ControllerState("settings_saved=1\nsettings_valid=1\nsettings_match=1").savedMatches(), "saved current snapshot");
        check(!new ControllerState("settings_saved=1\nsettings_valid=0\nsettings_match=1").saved(), "damaged snapshot rejected");
        check(!new ControllerState("settings_saved=1\nsettings_valid=1\nsettings_match=0").savedMatches(), "unsaved external edits shown");
        RootRunner.Result output = RootRunner.runProcess(new String[]{"java", "-cp", args[0],
                "com.questpro.ldcontrol.OutputChild"}, 5000);
        check(output.ok() && output.output.contains("child_ok"), "process output and exit");
        RootRunner.Result blocked = RootRunner.runProcess(new String[]{"java", "-cp", args[0],
                "com.questpro.ldcontrol.BlockedChild"}, 500);
        check(blocked.code == 124, "timeout while output stream remains open");
        System.out.println("Controller state/process/debug: 22 checks passed");
    }
}
