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
is limited to the images in COMPATIBILITY.md; no all-firmware claim is made.

## v204 profile derivation

The v204 entries in `runtime_profile.cpp` and `runtime_images.py` are not
measured on a headset and are not produced by shifting v207 constants until a
gate passes. Every value was recovered from the vendor library
`libvrruntimeservice.so` (SHA256
`840cb7661532ff53a40387cfb17a5c89ccdb114bc9231149b84e5df0e826ef1a`) and then
confirmed by executing that image in Unicorn.

The uniform-shift assumption does **not** hold across this image: the pair
cluster sits at delta `-0x3c2d8` from v207 while the native-debug object cluster
sits at `-0x3c180`, and the object ordering differs, so each address below was
identified individually rather than derived from a single offset.

| Role | v207 | v204 | How the v204 value was established |
| --- | --- | --- | --- |
| sample entry / resume | `0x72e908` / `0x72ec4c` | `0x7133cc` / `0x713710` | `fmov s0,#10.0` at a branch target; caller at `0x714dac`+`b #0x7133cc`; block length `0x344` preserved |
| lut entry / resume | `0x72f930` / `0x72fa98` | `0x7143f4` / `0x71455c` | `fmov s0,#1.0` at a branch target; caller at `0x714de4`+`b #0x7143f4`; block length `0x168` preserved |
| site instructions | `0x1e249000` / `0x1e2e1000` | identical | byte-identical at both entries |
| `x27`, matrix, selector | `0xe43588`, `0xe435e8`, `0xe459e8` | `0xe072b0`, `0xe07310`, `0xe09710` | immediates inside the hooked blocks; `matrix == x27+0x60` and `selector == x27+0x2460` hold in both images |
| stride / raw pointer | `0xe435d0` / `0xe435d8` | `0xe072f8` / `0xe07300` | `ldrsw [x8,#0x2f8]` and the raw load immediately before the hook site |
| `x20` | `0xe45000` | `0xe09000` | page of the selector; block reads `[x20,#0x710]` |
| native LUT header | `0xe46bf0` | `0xe0a918` | `selector+0x1208`, read by the hooked lut block itself |
| `x24` (header page) | `0xe46000` | `0xe0a000` | `adrp x24` + `ldr [x24,#0x918]` in the LUT generator |
| vector | `0xe46f90` | `0xe0acb8` | grown through `bl 0x389b74` with `x0` = this address |
| history / flags | `0xe46f48`, `0xe46f68`, `0xe46f60`, `0xe46f80` | `0xe0ac70`, `0xe0ac90`, `0xe0ac88`, `0xe0aca8` | pointer/flag cells 0x20 apart, used by the lut and encoder paths |
| scratch / mode4 / clamp | `0xe46c50`, `0xe46c68`, `0xe46c84` | `0xe0a978`, `0xe0a990`, `0xe0a9ac` | `selector`-relative cells read by the encoder |
| debug objects | `0xe42f98`, `0xe43040`, `0xe430e8`, `0xe43190`, `0xe43238` | `0xe06e18`, `0xe06ec0`, `0xe06f68`, `0xe07010`, `0xe070b8` | property-string cross references (`debugDilateX` @`0xe30f7`, `debugDilateY` @`0xe2a72`, `debugGaussian` @`0xb9700`, `smooth` @`0xbf50f`, `smooth.weight` @`0x957bd`) into the reader at `0x7171ec..0x7173fc`; field offset `+0x98` and stride `0xa8` unchanged |
| `expf` / `powf` slots | `0xe19940` / `0xe19918` | `0xdc6448` / `0xdc6428` | resolved from `.rela.plt` by symbol name, not by offset |
| trace context | `0xe17ed8` | `0xdc4dd0` | `.got` cell loaded then read as a byte at `+3` |
| property refresh | `0xd80c18` | `0xcb660c` | the function that calls `__system_property_area_serial`; halting at it reproduces the v207 shim |
| vector resize | `0x3a77c8` | `0x389b74` | the helper called with `x0 == vector` |
| log/trace call | `0x3fa14c` | `0x3cba2c` | FDE start called from `0x714dac` and `0x714de4`; recorded LRs are the two trace sites |
| code ranges | sample/lut/frame/dilate/kernel/gaussian/smooth/native/lutgen | see `runtime_images.py` | each range executed in Unicorn to its exact boundary |
| pause window | `0x72e8a4..0x73027c` | `0x713368..0x714d40` | function FDE start to `ret`+4 (`ret` at `0x714d3c`) |

### Oracle results on the v204 image

Run with `QUEST_LD_PROFILE=v204` and the v204 library as
`QUEST_LD_RUNTIME_IMAGE`:

| Oracle | v204 result |
| --- | --- |
| `sample_lut_oracle.py` | 52 cases, 20 neutral comparisons — same counts as the v207 release run |
| `stage_bridge_oracle.py` | 48 cases, pass |
| `bridge_integration_oracle.py` | 16 cases, 12 native comparisons; bridges executed inside the patched v204 function |
| `native_oracle.py` stages | sample, lut, frame, dilate, kernel (3x3 Gaussian coefficients reproduced), gaussian, smooth and native encoder (two 1153-byte submits) all execute to their boundaries |
| LUT generator | `generate_lut(20,1)` reproduces the reference table exactly: `0,409,819,…,8190` |

### Device witnesses

`native_oracle.py` cross-checks its emulated default LUT and size-3 kernel
against two captures taken from the running runtime, so the assertion proves the
emulator against the device instead of against itself:

| Witness | Source | SHA256 |
| --- | --- | --- |
| `lut.bin`, 42 bytes | `[selector+0x1208]` in the live process, 21 uint16 | `868439418a77a361150c68b41e6605627290a0a4ea434f6c391f3c9546c73c72` |
| `kernel_prefix.bin`, 36 bytes | vector at `0xe0acb8`, 3x3 Gaussian `f32` | `73200537f0df0a49dec48f957e8ed87fac1f3d00c5a2b293693a924597826c75` |

Both matched the v204 emulation byte for byte. Reading them also confirmed the
live layout independently: the two 64-byte fingerprints read back identical at
`base+0x7133cc` and `base+0x7143f4`, `stride` was 1536, `selector` 0, the header
pair spanned exactly 42 bytes and the vector exactly 36.

### Live hook and replacement on v204

Installed from the packaged ZIP with `magisk --install-module` (the installer
SHA256 gate matched the v204 entry), then rebooted: the module merged into
`/data/adb/modules`, boot restore reported `restore_state=restored`, and
`system.prop` re-armed the gates at `hook_mode=0`, `enable=0`, `bypass=1`.

Prepare Hook (`controller.sh prepare`), then the runtime restarted:

```
startup pid=15494 version=0.5.0 hook_requested=1
image_profile=v204 base=0x7651928000
hook_install=ok base=0x7651928000 bridge=0x764b03b000
```

Bridge-only window (`enable=0`), hits rising, nothing written:

```
status pid=15494 ready=1 enable=0 seq=4 hits=35934 sample_writes=0 lut_writes=0 rejected=0
```

After arming (`enable=1`, mean sampler, then the curve), over one process
lifetime with the pid never changing:

```
status pid=15494 ready=1 enable=0 seq=292 hits=315404 sample_writes=101994 lut_writes=51283 rejected=1
```

101 994 sample-stage and 51 283 LUT-stage replacements were applied on the
headset, with one rejected frame out of 315 404 hits (the validator declining a
single frame, not a fault), and the runtime never restarted.

The bridge preparation and the first arming were driven through
`controller.sh prepare` and `ldctl sampler mean` + `controller.sh enable`. The
curve was then armed and the replacement switched off again through the
controller activity itself (`com.questpro.ldcontrol`), which is why the final
line shows `enable=0` after 51 283 LUT writes: the on-device controls were
exercised end to end, and closing the switch kept the tuning saved and the
runtime alive.

Both last lines above end at `enable=0` because the owner disarmed the
replacement; `hook_mode=1` is not persisted across reboots by design, so a fresh
boot returns to `hook_mode=0`, `enable=0`, `bypass=1`.
