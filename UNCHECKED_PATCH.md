# UNCHECKED PATCH WARNING

This is an **experimental unchecked local build** of QuestProLocalDimmingTweak
0.5.0, made at the explicit request of the device owner.

- The installer no longer verifies headset model, ABI, or the runtime library
  SHA-256 before installation.
- The native Zygisk library no longer verifies the ELF build ID or the 64-byte
  hook-site fingerprints of `libvrruntimeservice.so` before installing bridges.
- Hook-site trampolines replay the instruction actually found at each hook site
  at install time, instead of a hard-coded v207 opcode.

The build still targets the pinned v207 memory layout (hook sites `0x72e908`
/ `0x72f930`, resume sites `0x72ec4c` / `0x72fa98`, data at `0xe435d0`),
because the official release ZIP packages only the compiled library, not a
rebuilt offset model. If your runtime differs from v207, a mismatch can crash
`com.oculus.vrruntimeservice`, black-screen the headset, or interrupt
Virtual Desktop.

The module installs disabled (`hook_mode=0`, `enable=0`, `bypass=1`). Hook and
replacement activation stay manual and require confirmation. Remaining
mapped-memory coverage, thread-parking, rollback and emergency-bypass checks
are intact.

This build is not validated on any headset and is not supported by upstream.
