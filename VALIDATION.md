# 0.5.0 release validation

Checked on 2026-10-10. All checks below are offline. No ADB connection, headset
installation, property write or Runtime restart was performed during publication.

| Check | Result |
| --- | --- |
| Original ARM64 instruction fixtures | 223 generated/checked in Unicorn |
| Sampling/LUT integration contract | 52 cases, 20 neutral comparisons |
| Generated bridge instruction preservation | 48 cases |
| Bridge integration inside original function | 16 cases, 12 native comparisons |
| NDK-compiled sampling/LUT/controller | 31 cases |
| NDK-compiled settings/control storage | 40 cases |
| JavaScript reference tests with private fixtures | 17 passed, 0 skipped |
| Controller state/process/debug JVM checks | 22 passed |
| Runtime helper, mocked Android commands | 19 scenarios |
| Boot restoration, mocked root/boot status | 8 scenarios |
| Installer compatibility/fresh install/fallback | 7 scenarios |
| Android installer/helper shell syntax | 6 files |
| English UI source/accessibility scan | No Chinese literals or Unicode escapes |
| APK | Signed v3, verified, package/version/API checked |

APK package: `com.questpro.ldcontrol`, versionName `0.5.0`, versionCode `50`,
minimum API `29`, target/compile API `35`.

Signer certificate SHA256:
`16eeb0f06c1a2797f19cdba009d18b89d4cf795a319dfebaacd2382907f10e66`.
It matches the previous 0.4.0 controller. Private keys are not included.

The module ZIP is checked for CRC, all SHA256SUMS.json entries, duplicate or
unsafe archive paths, unexpected proprietary/private files, embedded APK hash,
English source, and agreement between embedded source and the published source.
The release's external `.sha256` file provides the exact ZIP hash.

Private oracle inputs, raw synthetic original-instruction fixtures and captured
vendor binaries were used only locally and are not distributed. Compiled tests
execute actual ARM64 code in Unicorn, with OS/file/property boundaries mocked.
This does not validate live Hook installation, timing, Android package-manager
behavior or physical luminance.

Fresh installation, English UI layout/touch interaction on Quest, real boot
restoration, Gaussian 5..9 optical behavior, smoothing-weight adjustments and
optical improvement images remain unvalidated in this release. Compatibility
is limited to the image in COMPATIBILITY.md; no all-firmware claim is made.
