Quest Pro Sampler/LUT 0.5.0
Fix: the process mapping cache now supports more than 1024 entries. Real
Runtime had 3659 mappings, causing 0.3.0 to reject every sample without writing.
Feature: bundled QuestProLDControl.apk provides on-device runtime controls.
The installer attempts one-time APK installation, with a fallback copy in
/sdcard/Download. Grant the app root in Magisk; it opens from the module action
or headset app list. After a reboot wait for Singularity root, then use the
confirmed Prepare Hook and restart Runtime action. Hook ready is checked
against the current Runtime PID before the Enable replacement switch works.
Replacement stays disabled after preparation; the user enables it explicitly.
Default: no hooks, no replacement, no Runtime restart.
Only sampling/reduction and LUT are replaced. Original middle stages and
backlight mapping/submission remain intact. Output saturation code is 8190.

New native debug GUI controls: debugDilateX (0..8), debugDilateY (0..15),
debugGaussian (0..9; quick buttons 0..4), smooth (0/1), smooth.weight (0..0.30).
Pinned firmware defaults are 1, 2, 3, 1, and 0.30. The weight ceiling is checked
by GUI, ldctl and saved-file validation. Gaussian 5..9 have no live validation.
These original properties affect the native pipeline directly without a Hook
or Runtime restart. They also apply while replacement is disabled.

Every parameter apply/reset saves sampler, dormant blend weight, actual LUT
bytes, known curve metadata and the five original debug values. The root-only
file /data/adb/questpro_local_dimming_030/settings.bin survives module updates;
it uses explicit bounded fields, CRC32, fsync and atomic rename. Invalid files
are refused before any property write. Save current running values captures
external ADB tuning without setting properties. Invalid weights are refused.
The installer attempts to capture current 0.4.0 tuning before the first upgrade
reboot; an existing saved file is preserved.
Do not run alongside an enabled legacy questpro_local_dimming module.

Control tool: /data/adb/modules/questpro_local_dimming_030/bin/ldctl
Commands: status; reset; disable; sampler native|mean|peak|blend [weight];
lut-native; lut-curve threshold gamma; debug X Y gaussian smooth weight;
debug-reset; reset-all; save; restore.
Sampler changes preserve the current LUT; LUT changes preserve the sampler.
Plans commit as a complete even-sequence snapshot. An incomplete edit is ignored.

hook_mode is read only at process startup. Set it to 1 before a deliberate
runtime/process restart. Leave enable=0, bypass=1 for the first bridge test.
After verifying hook_install=ok and rising hits with zero writes, publish mean
and arm enable=1, bypass=0. Changing sampler/LUT after this needs no restart.
Never activate before reviewing current logs and having root rollback available.
ldctl disable sets enable=0 and bypass=1. Closing the GUI replacement switch
also sets hook_mode=0. Emergency restore additionally resets native debug.
Installed bridges stay
mapped and execute the native instructions; do not unload live code.
The Magisk action screen is a text terminal and invokes action.sh; it is a
launcher for the graphical controller, not an embedded WebUI. The controller
has the emergency restore action. If it is not installed, install the APK from
/sdcard/Download once, then use this action or the headset app list.

New prefix: debug.oculus.localDimming.zl2.
Log: /data/adb/modules/questpro_local_dimming_030/log/zygisk_trace.log
Firmware build-id and 64-byte fingerprints are pinned per reviewed image
(v207 and v204); an unlisted firmware is refused, never adapted. Unsupported image,
signal conflict, blocked thread, unsafe instruction position or mmap failure
refuses activation. Installation pauses other runtime threads for up to 200ms.
Root may be absent after reboot; module service does not depend on early root.
GUI recovery can restart Runtime with hook_mode=0, after confirmation. No
module service or page launch automatically restarts Runtime or enables replacement.

The service restores saved parameters in a background worker after boot/root
are available, retrying for up to five minutes. It never writes activation
gates; system.prop retains hook_mode=0, enable=0, bypass=1. Native debug values
act immediately; saved sampler/LUT replacements wait for manual Prepare Hook
and Enable replacement. Prepare performs a final restore before its confirmed
Runtime restart, covering a boot-time root gap. Invalid saved data prevents
the restart. Restore stops after manual activation.

Turning the replacement switch off preserves tuning. GUI Emergency restore
first closes enable/bypass/hook gates, then resets/saves native debug defaults.
A repeated rollback follows an in-flight action. Valid sampler/LUT choices
stay saved; invalid plans fall back to all defaults. Ordinary parameter reset
buttons never activate gates or restart Runtime.

This package passed offline compiled arithmetic and bridge tests, and the v204
profile passed a live hook test on a Quest Pro running 204.0.0.149.430:
image_profile=v204, hook_install=ok, 101994 sample and 51283 LUT replacements
applied with one rejected frame in 315404 hits and no runtime restart. The
arming, the curve and the disarm were performed with the graphical controller on
the headset. Optical
results, long-run driver behaviour and other firmwares remain unverified.
