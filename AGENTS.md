# Project requirements

- Repository: `Cvinson06/QuestProLocalDimmingTweak`, public, MIT licensed.
- Public UI, accessibility labels, installer messages and documentation are English.
- Keep these prominent README statements:
  **This project was created entirely by AI.**
  **Images demonstrating the actual results will be added later.**
- Release `0.5.0` includes a verified Magisk ZIP and SHA256 checksum. Future
  changes must use a new version; never replace published assets in place.
- Installation/use must not depend on an author's device serial, IP, ADB
  connection, fixed PID, account or desktop path. Retain firmware checks and
  document the supported image in COMPATIBILITY.md.
- Preserve stable module/application IDs and APK signing compatibility.
- Preserve disabled defaults and manual Hook/effect activation. Read-only app
  launch must never restart Runtime. Preparation/recovery require confirmation.
- Never connect, install, write properties or restart a headset without
  explicit device-test authorization. Do not test smooth.weight on hardware.
- Exclude vendor images, device data, raw fixtures, credentials, private keys
  and development dependencies from Git/release assets.
- Use isolated build outputs. Report offline simulation separately from actual
  installation, UI interaction and optical measurements.
