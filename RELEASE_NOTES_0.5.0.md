# QuestProLocalDimmingTweak 0.5.0

Public MIT release with a fully English Android controller, native pipeline
controls and persistent tuning. The Magisk ZIP contains the module, control
tool, signed controller, source, license, documentation and validation summaries.

**This project was created entirely by AI.**

**Images demonstrating the actual results will be added later.**

Changes:

- English UI, accessibility labels, status messages and restart confirmations.
- Native dilation/Gaussian/smoothing controls, bounded debug values, persistent
  sampler/LUT/debug tuning and background boot restoration.
- Installation checks Quest Pro/ARM64 and dynamically discovers the Runtime
  APK package `com.oculus.systemdriver` to verify the supported library SHA256.
- No author's serial number, network address, fixed PID or desktop directory
  is required. Firmware identity/instruction checks remain enabled.
- Configurable build/tool/private-input/signing paths, MIT license, upstream
  Zygisk notice and complete source directory layout inside the ZIP.

Supported: Quest Pro (`seacliff`), ARM64, compatible Magisk/Zygisk setup, and
Runtime SHA256 `0ffc0216e3904307d8504e4080c4481db2d29030d4bdccfcef462e3809846b11`.
Unsupported or unreadable Runtime images stop installation. Install through
Magisk on a booted headset; see README and COMPATIBILITY.md.

The module ID `questpro_local_dimming_030` and controller package
`com.questpro.ldcontrol` are unchanged. The controller retains its previous
signing certificate. Disable the older `questpro_local_dimming` module and
reboot before installation if it is enabled. The bundled APK is installed
automatically where possible; manual installation fallback is documented.

Hook preparation/recovery restart Runtime and disconnect Virtual Desktop.
Hook and replacement stay off until explicitly activated. Saved tuning restores
without automatically enabling those gates. Emergency restore disables
replacement and restores native defaults; full Hook removal uses confirmed
Runtime recovery or disabling the module in Magisk and rebooting.

Offline validation includes 31 compiled core and 40 compiled settings cases,
22 JVM checks, 19 helper scenarios, 8 boot scenarios, 7 installer scenarios,
and original-instruction/bridge checks. APK v3 signature and ZIP CRC/SHA256 are
verified. No new headset installation, English UI hardware interaction or
optical validation was performed. Smoothing weight is capped at the verified
default 0.30; its hardware adjustment is untested. See VALIDATION.md.

Verify the ZIP against the attached `.sha256` file. The ZIP contains the APK;
no vendor firmware, raw device capture, private key or rooting software is bundled.
