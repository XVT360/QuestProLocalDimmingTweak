# Third-party notices

Project-owned source is MIT licensed. The following component retains its own
upstream permission notice:

- `zygisk_local_dimming/native/zygisk.hpp`: reduced/adapted Zygisk API v5
  declarations and module-registration code based on the official
  [Zygisk module sample header](https://github.com/topjohnwu/zygisk-module-sample/blob/master/module/jni/zygisk.hpp).
  Copyright 2022-2023 John "topjohnwu" Wu. The full upstream permission and
  warranty/liability notice is retained at the beginning of the adapted header.
  The adapted header is not represented as an unmodified upstream file.

Magisk/Zygisk and the user's rooting solution are external runtime dependencies.
Android SDK/NDK, JDK, Python, Node.js, pyelftools, Unicorn and Capstone are
external development dependencies. Their distributions and licenses are not
replaced by the project MIT license; they are not included in the source or ZIP.

Small image-identity/instruction fingerprints are firmware compatibility metadata.
Generated bridge words are project-generated code. Complete vendor libraries,
APKs, firmware images, raw captured matrices and private signing keys are not
included and are not relicensed by this project.
