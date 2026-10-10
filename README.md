# QuestProLocalDimmingTweak

**This project was created entirely by AI.**

**Images demonstrating the actual results will be added later.**

An experimental Magisk/Zygisk module and English Android controller for tuning
Quest Pro MiniLED local dimming. The goal is to reduce blooming by adjusting
sampling and the LUT; complete elimination of blooming is not promised.

## Compatibility

Version **0.5.0** supports ARM64 Quest Pro (`seacliff`) with the matching Runtime
image described in [COMPATIBILITY.md](COMPATIBILITY.md). The installer discovers
the Runtime APK and checks its library SHA256. Unsupported images stop the
installation; the Hook independently checks the build-id and instruction bytes.

A compatible root setup with Magisk and Zygisk is required. If using Singularity,
wait for its root restoration after reboot; this can take about two minutes.
No rooting software or vendor firmware is bundled. This release has no newly
measured Magisk/Singularity version compatibility matrix. Refer to the upstream
[Magisk](https://github.com/topjohnwu/Magisk) and
[Zygisk API sample](https://github.com/topjohnwu/zygisk-module-sample) for their
own requirements. This module does not root the headset.

Installation and normal use do not require the author's headset, serial number,
IP address, account, ADB connection, or computer. Support for other headsets or
arbitrary Quest firmware is not claimed.

## Install and use

1. Download `questpro_local_dimming-0.5.0.zip` and its `.sha256` file from
   [Releases](https://github.com/Cvinson06/QuestProLocalDimmingTweak/releases).
2. If the legacy module `questpro_local_dimming` is enabled, disable it and reboot
   before installing this module. Do not run both modules together.
3. Install the ZIP through Magisk's **Modules > Install from storage** on a booted
   supported Quest Pro, then reboot. Zygisk must be enabled in your root setup.
4. The installer tries to install the bundled **Quest Pro LD Control** APK. If it
   cannot, install the copy in the headset's Download folder, or extract
   `QuestProLDControl.apk` from the ZIP and install it manually. Grant it root.
5. Open the controller from the app list or the module's action button. Opening
   the app only reads status; it does not restart Runtime or enable effects.
6. Native pipeline controls can be changed without enabling the replacement.
   To use replacement sampling/LUT, choose **Prepare Hook and restart Runtime**,
   read the confirmation, and wait for **Hook ready; native passthrough**. Runtime
   restart disconnects Virtual Desktop and can briefly interrupt the display.
7. Enable **Enable replacement** manually when ready. Use **Apply and save live**
   or **Apply and save** to store tuning. Settings restore after reboot; Hook and
   effect activation remain manual.

The ZIP installs disabled (`hook_mode=0`, `enable=0`, `bypass=1`). A first install
can capture the current bounded tuning; it does not activate the effect. Saved
settings survive module updates in `/data/adb/questpro_local_dimming_030/`.
Malformed or non-private snapshots are rejected before restoration.

## Controls and limits

Replacement controls provide Native/Mean/Peak/Blend sampling, blend weight,
native LUT, saturation threshold, and gamma. The Hook only replaces
sampling/reduction and LUT. Native dilation, Gaussian filtering, smoothing,
backlight mapping and submission remain native; the separate native controls
adjust properties in those original stages.

Native controls provide dilation X/Y, Gaussian, temporal smoothing, and a
bounded smoothing weight. The verified firmware's fallback smoothing weight is
0.30 and the UI/parser cap it there. Lower weights retain more history; zero can
retain the prior frame. Changes to this weight have not been tested on hardware;
previous experiments had flicker/freeze reports. Leave it at the native default
unless you understand that limitation. Gaussian 5..9 optical effects are also
untested; 2/4 can noticeably change brightness. Reset buttons restore defaults.

`8190` is a software output code, not 8-bit `255` or measured physical luminance.
Compile/target API 35 describes the APK build; it does not change the headset OS.
The controller requires Android API 29 or newer; prior development used API 34.

## Recovery and uninstall

**Emergency restore** disables replacement, returns the native controls to
bounded defaults, and saves them. Existing bridges stay mapped in native
passthrough. **Recover native and restart Runtime** starts a new native process
with Hook requests off and requires confirmation.

For replacement-only disable with root access:

```sh
sh /data/adb/modules/questpro_local_dimming_030/controller.sh disable
```

If the UI cannot be used, disable the module in Magisk and reboot. Do not attempt
to unload live code. To uninstall, remove the module in Magisk, reboot, and
uninstall the separate controller if desired. Saved tuning is retained outside
the module; it can be removed later through your root file tools if you choose.

## Validation

The 0.5.0 English release was rebuilt and validated offline. Checks include
compiled ARM64 arithmetic/settings execution, original-instruction comparison,
controller JVM tests, mocked installer/helper/boot tests, APK signature and
metadata verification, and ZIP CRC/SHA256 validation. See
[VALIDATION.md](VALIDATION.md) for exact counts and certificate fingerprint.

This preparation did not install or activate the new package on a headset.
English UI interaction/layout on Quest, fresh installation, reboot restoration,
and optical results still require real-device validation. Earlier user feedback
about the previous implementation is not a new hardware test of this release.

## Source and license

See [BUILDING.md](BUILDING.md) to build and run offline tests. Ordinary compilation
uses a reviewed fingerprint header; full verification requires private inputs
legally obtained from a matching device. Those inputs are not distributed.

Project-owned code is licensed under [MIT](LICENSE). The adapted Zygisk API
header retains its upstream permissive notice; see
[THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md). No license here grants rights to
redistribute proprietary Quest firmware or vendor APKs.
