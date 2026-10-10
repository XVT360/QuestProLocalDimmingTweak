# Graphical Controller 0.5.0

The Android API 35 / Java 8 build compiles and the signed APK verifies.
Minimum device API is 29; the connected Quest Pro runs API 34 (Android 14).

Completed checks:

- 31 NDK-compiled ARM64 arithmetic, mapping and controller regressions in Unicorn.
- 22 JVM controller state/process/debug bounds checks.
- 19 mocked Runtime helper scenarios, including preparation, recovery, rollback,
  save/restore, invalid plans, pending updates and stale PIDs.
- 8 boot-worker scenarios including a simulated 120-second root gap, retries,
  invalid snapshots, manual activation, disabled module and timeout.
- 40 cases executing NDK-compiled settings/ldctl in ARM64 Unicorn. OS/libc calls
  are mocked; powf executes the captured Android libm. Tests cover exact LUT
  persistence, 256-entry/imported LUTs, CRC damage, bounds, file modes, missing
  root, storage/property failures and unchanged activation gates.
- Android shell scripts pass bash syntax checking.
- The module ZIP verifies CRC and every SHA256SUMS.json entry when packaged.

Limits:

- The Windows host has no emulator hypervisor driver. Software emulation did not
  become available; native UI screenshots and actual Quest touch interaction have
  not been verified. The APK was not installed on the user's headset during build.
- Runtime restart was tested with mocked process/property commands. This release
  does not claim a new live installer or optical validation.
- Existing native dilation, Gaussian and smoothing remain in the pipeline;
  the GUI changes their properties. Gaussian 5..9 optical effects and real boot
  restoration remain to be checked on the headset.

Opening the controller reads status. Preparation/recovery require explicit dialog
confirmation. Emergency restore is independent of polling and repeats after an
in-flight action. Firmware fingerprints and the underlying hook implementation
are unchanged from the working 0.4.0 module. Saved data lives outside the module
directory; the first installer only captures data if no saved file exists.
