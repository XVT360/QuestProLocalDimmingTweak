# QuestProLocalDimmingTweak — UNCHECKED local build report

Base: upstream v0.5.0, commit e1475c5 ("Release 0.5.0 with English controls, portable installation and MIT license").
Toolchain: Android NDK r27d (linux-x86_64, revision 13750724), arm64-v8a, android-23, c++_static.

## Source changes (see QuestProLocalDimmingTweak-UNCHECKED.patch)

- `zedgisk_local_dimming/sample_lut/package/customize.sh` — removed seacliff model, ARM64 abilist,
  runtime-SHA256 and `compatible != 1` install gates; kept legacy-module check, permissions, settings
  capture, controller APK install and disabled defaults. Header now reads "UNCHECKED LOCAL BUILD".
- `runtime.cpp` — removed `note_id()` ELF build-ID comparison; `inspect()` now matches the library by
  name only; 64-byte `kSampleFingerprint`/`kLutFingerprint` memcmp removed. PT_LOAD RX/RW coverage
  checks (`0x72e908..0x72f970`, `0xe435d0..0xe46c88`) retained.
- `installer.cpp` — after `prepare_bridge()`, `expected_instruction` for both stages is read from the
  actual hook site and written into `words[k_original_instruction]` (index 87), so trampolines replay
  the real original instruction. The equality gate against hardcoded v207 words (`const bool unchanged`)
  was removed; rollback stores now use the dynamic instructions.
- `module.prop` — renamed "…(UNCHECKED)" with new description; `id`, `version=0.5.0`, `versionCode=50` unchanged.
- `UNCHECKED_PATCH.md` — warning file included in the ZIP and its manifest.

## Packaging

- Official release `questpro_local_dimming-0.5.0.zip` downloaded and SHA-256 verified
  (`9af2599b9b0af21746e534c62d7703e7140c04c3de6ceea58cab34f21d1f3176`).
- Repackaged as `questpro_local_dimming-0.5.0-UNCHECKED.zip` (101 entries): replaced
  `zygisk/arm64-v8a.so`, `customize.sh`, `module.prop`, the four matching `source/...` entries;
  added `UNCHECKED_PATCH.md`; regenerated `SHA256SUMS.json` (no duplicates). All other entries
  preserved byte-identical — notably `QuestProLDControl.apk`, `bin/ldctl` (upstream official build),
  `META-INF/com/google/android/update-binary`, `service.sh`, `controller.sh`.

## Verification (offline only — no headset was connected, flashed or tested)

- ndk-build exit 0; `libquestpro_sample_lut.so` is ELF64 AArch64, Android 23, NDK r27d, stripped.
- `bash -n customize.sh`: OK.
- `node --test native_reference.test.js sample_lut_reference.test.js`: 12 pass, 5 skip, 0 fail
  (matches the upstream source-only baseline; the 5 skips are the optional ARM64 oracle fixtures).
- `git diff --check`: clean.
- `ZipFile.testzip()` and every entry of the regenerated `SHA256SUMS.json` verified.
- ZIP `customize.sh` contains no firmware SHA/model check; `module.prop` shows UNCHECKED;
  `runtime.cpp` has no `note_id`/fingerprint compares; `installer.cpp` uses dynamic instructions.

## Artifacts

- `unchecked_build/questpro_local_dimming-0.5.0-UNCHECKED.zip`
  SHA-256 `79717f118c60c7f7ca837bdbfd6d9a7753be836f8da51c604e9331742d75f9a9`
- `unchecked_build/questpro_local_dimming-0.5.0-UNCHECKED.zip.sha256`
- `QuestProLocalDimmingTweak-UNCHECKED.patch` (git diff vs e1475c5, includes UNCHECKED_PATCH.md)
- Copies staged in `/workspace/deliverables/`.

Nothing was committed or pushed; the upstream release assets were not modified.

## Limitation

This is a force-compatibility experiment, not a validated v204 port. Hook sites `0x72e908`/`0x72f930`,
resume sites `0x72ec4c`/`0x72fa98`, and data offsets (e.g. `0xe435d0`, `0xe459e8`) remain hardcoded
from v207. A mismatch can crash `com.oculus.vrruntimeservice` or black-screen the headset. The module
installs disabled; activation stays manual.

## Additional verification (code-correctness pass)

- runtime.o disassembly: 0 `memcmp` calls remain (original code had memcmp in
  `note_id` and both fingerprint compares) — identity gates confirmed absent at
  binary level. `libvrruntimeservice.so` name matching and
  `pinned_image_not_found` trace remain, as intended.
- `bridge_template::kWords` = 135 words; `k_original_instruction` = index 87 is
  in range — the patched trampoline write is structurally valid.
- `node controller/test_boot.cjs`: exit 0, 8 scenarios passed.
- `node controller/test_helper.cjs`: 19 scenarios passed after adding the exec
  bit to the mock `bin/ldctl` (the upstream test omits chmod; on Windows/Git
  Bash everything is executable, on POSIX this is an environment-only issue,
  unrelated to the patch).
- `node controller/test_installer.cjs`: not applicable to this variant — it
  hard-codes the removed `pm path com.oculus.systemdriver` / `unzip -p` /
  `sha256sum` reconciliation flow (asserts `/pm:path com.oculus.systemdriver/`),
  exactly as anticipated by the handoff. Instead, an offline bash simulation of
  the modified `customize.sh` was run with mocked `ui_print`/`pm`/`cp`/
  `set_perm*` and **passed**: UNCHECKED banner printed, no firmware/SHA calls,
  APK install invoked, settings capture ran, no forbidden property writes or
  runtime restarts, module stays disabled.
