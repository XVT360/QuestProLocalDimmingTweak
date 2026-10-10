# Building and offline validation

Installing the release ZIP on a supported headset does not require a PC, Python,
Node.js, a firmware extraction, or these development tools. This guide is for
building or auditing the source.

## Dependencies

- Android NDK r27d, SDK platform API 35, and SDK build-tools 35.0.0.
- JDK 17 (Java sources target Java 8), Windows PowerShell, Python 3.12+,
  Node.js 22+, and Git Bash on Windows.
- `python -m pip install -r requirements-dev.txt` for the offline ARM64 tools.

Set `ANDROID_NDK_HOME` and `ANDROID_SDK_ROOT` to your installed toolchains.
The controller build currently requires Windows; native-only ndk-build can also
be invoked directly on other NDK hosts. No downloaded toolchain is in Git.

## Normal build versus image verification

Run `python build_sample_lut.py` to compile using the reviewed checked-in
`pinned_image.h`. This does not independently verify an original vendor image;
the output clearly states that distinction. Runtime identity and fingerprint
checks remain enabled in the module.

To regenerate/verify the identity from a matching image obtained from your own
headset, set `QUEST_LD_RUNTIME_IMAGE` to its full local path before running the
build. The script rejects a mismatching SHA256. Vendor images are not included
in Git or release assets; never remove the check to force an unsupported image.

## APK signing and upgrades

Set `QUEST_LD_KEYSTORE` to an existing private keystore to preserve upgrade
compatibility. Optional `QUEST_LD_KEY_ALIAS`, `QUEST_LD_STORE_PASS`, and
`QUEST_LD_KEY_PASS` configure signing. Passwords are passed by environment
reference rather than literal command arguments. Never commit or upload a
private key. Preserve it in a private backup under your own control.

Without an explicit key the script generates a local development key in the
ignored `controller/build` directory. Such builds use a different certificate
from the official release and cannot overwrite that controller installation.
The release preserves the certificate used by the previous local controller.
Before uninstalling an incompatible APK, consider its data and migration needs.

The build refuses to overwrite an existing output APK or ZIP. Use a fresh
isolated build directory/snapshot; preserve delivered artifacts.

## Tests without private vendor inputs

From the repository root:

```powershell
node --test native_reference.test.js sample_lut_reference.test.js
powershell -NoProfile -ExecutionPolicy Bypass -File controller/test_controller.ps1
node controller/test_helper.cjs
node controller/test_boot.cjs
node controller/test_installer.cjs
```

Use `QUEST_LD_BASH` if Git Bash is installed in a nonstandard location. Five
reference tests explicitly skip when the optional original ARM64 fixtures are
absent; the other tests run normally. Shell tests mock Android/root/process
operations and never connect to a headset.

## Full private-input verification and packaging

Provide the matching Runtime image via `QUEST_LD_RUNTIME_IMAGE`, and privately
place `libm.so`, `lut.bin`, and `kernel_prefix.bin` under `.private-inputs/` (or
set `QUEST_LD_PRIVATE_INPUTS` to their directory). The libm identity used in
this release is SHA256
`2e7283edc5bca46fae12f62ce59035fc1287c9d8c82a9d5ae2115133ce01cf50`.
These inputs are excluded from publication.

After building, run in order:

```powershell
python native_oracle.py
python sample_lut_oracle.py
python stage_bridge_oracle.py
python bridge_integration_oracle.py
python compiled_sample_lut_oracle.py
python controller/test_settings_oracle.py
node --test native_reference.test.js sample_lut_reference.test.js
python build_sample_lut.py --package
```

Oracle execution generates private fixtures and summary evidence. The packager
requires current compiled/settings reports matching the built test-library and
control-tool hashes. Review the generated bridge header; if it changes, rebuild
and rerun relevant tests before packaging.

Release packaging contains the module, control tool, signed controller,
installation scripts, source, license, documentation and summary reports.
It excludes vendor images, memory captures, raw fixtures, private keys,
test-only native libraries and desktop dependencies. Exact byte-for-byte
reproducibility is not claimed; APK signing and archive timestamps affect it.
