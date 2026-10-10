# Device compatibility and hardcoding audit

The module supports Quest Pro (`ro.product.device=seacliff`) with ARM64 and the
matching Oculus Runtime image. Installation does not require the author's
headset, serial number, IP address, ADB connection, account, fixed PID, or PC.

## Supported image

- APK package: `com.oculus.systemdriver` (VrDriver).
- Runtime process: `com.oculus.vrruntimeservice`.
- APK version in the offline reference input: `207.0.0.218.429`.
- Runtime library: `lib/arm64-v8a/libvrruntimeservice.so`.
- Runtime SHA256: `0ffc0216e3904307d8504e4080c4481db2d29030d4bdccfcef462e3809846b11`.
- ELF build-id: `0eb23622baf2a50528534f27ea1eccdde3fd8dd7`.

The installer finds APK paths with `pm path com.oculus.systemdriver`, extracts
only the candidate library stream using Magisk's BusyBox tools, and checks its
SHA256. Unsupported or unreadable images abort installation before settings or
the controller are installed. No firmware file is bundled or persisted by this
check. Install through the Magisk app on a booted headset with package-manager
access; recovery installation is not supported.

The runtime independently checks the ELF build-id, executable/data segment
coverage and 64-byte instruction fingerprints before installing bridges. These
checks are deliberately retained. A matching library does not establish support
for every firmware combination, rooting solution or Magisk version.

## Constants deliberately retained

| Constant | Purpose |
| --- | --- |
| Runtime image identity and relative addresses | Guard ABI/layout and instruction compatibility |
| `com.oculus.systemdriver` | Discover installed Runtime APK paths |
| `com.oculus.vrruntimeservice` | Select the Runtime process; PID is discovered at each action |
| `questpro_local_dimming_030` | Stable Magisk module ID for upgrades |
| `com.questpro.ldcontrol` | Stable Android controller package for upgrades |
| `/data/adb/modules/...`, `/data/adb/...`, `/sdcard/Download` | Standard Android/Magisk installation and persistence locations |
| Synthetic PIDs and fake APK paths in tests | Mock data; never used to target a device |

## Host paths made configurable

Android NDK/SDK and signing-key locations use documented environment variables.
Private oracle inputs use `QUEST_LD_RUNTIME_IMAGE` and `QUEST_LD_PRIVATE_INPUTS`.
Host Bash test paths support `QUEST_LD_BASH`. No original user's Windows path is
required by the published source or installation package.

## Limits

The public release is rebuilt and checked offline. The fresh-install hash check,
APK installation, English UI layout on Quest, boot restoration on Quest and
optical results have not been newly validated on hardware. Firmware updates may
change the image and require a new reviewed implementation; never remove the
checks to force compatibility.
