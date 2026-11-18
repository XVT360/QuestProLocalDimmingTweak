# Device compatibility and hardcoding audit

The module supports Quest Pro (`ro.product.device=seacliff`) with ARM64 and the
matching Oculus Runtime image. Installation does not require the author's
headset, serial number, IP address, ADB connection, account, fixed PID, or PC.

## Supported images

Each reviewed Runtime image keeps its own pinned identity and its own address
profile (`runtime_profile.cpp`). The library is identified at run time by its
ELF build-id; the profile supplies every address, so no firmware inherits
another firmware's constants. An image outside this table is refused.

| | v207 | v204 |
| --- | --- | --- |
| APK package | `com.oculus.systemdriver` (VrDriver) | same |
| Runtime process | `com.oculus.vrruntimeservice` | same |
| APK version in the reference input | `207.0.0.218.429` | `204.0.0.149.430` |
| Runtime library | `lib/arm64-v8a/libvrruntimeservice.so` | same |
| Runtime SHA256 | `0ffc0216e3904307d8504e4080c4481db2d29030d4bdccfcef462e3809846b11` | `840cb7661532ff53a40387cfb17a5c89ccdb114bc9231149b84e5df0e826ef1a` |
| ELF build-id | `0eb23622baf2a50528534f27ea1eccdde3fd8dd7` | `db13c881de5413625c45464ba68b1d9be4cd739e` |
| Sample / LUT hook site | `0x72e908` / `0x72f930` | `0x7133cc` / `0x7143f4` |

The two images differ only in addresses: the hook-site instructions
(`fmov s0,#10.0`, `fmov s0,#1.0`), block lengths, cell geometry, divisors and
the `x27+0x60` / `matrix+0x2400` data relationships are identical, and each
profile pins the 64-byte fingerprints read from its own image.

The installer finds APK paths with `pm path com.oculus.systemdriver`, extracts
only the candidate library stream using Magisk's BusyBox tools, and checks its
SHA256 against this list. Unsupported or unreadable images abort installation
before settings or the controller are installed. No firmware file is bundled or
persisted by this check. Install through the Magisk app on a booted headset with
package-manager access; recovery installation is not supported.

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
