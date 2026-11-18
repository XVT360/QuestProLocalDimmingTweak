"""Reviewed Runtime image address profiles for the offline oracles.

Two images are reviewed. v207 is the image the 0.5.0 release was validated
against and its values are unchanged. v204 is the second reviewed image; every
address for it was recovered from that image and then confirmed by executing it
in Unicorn (see VALIDATION.md for the derivation and for the checks that prove
each one).

Selecting an image:
  * ``QUEST_LD_PROFILE=v207`` / ``v204`` forces a profile, or
  * the profile is chosen from the SHA256 of ``QUEST_LD_RUNTIME_IMAGE``.

Nothing here weakens a check: an image whose SHA256 matches neither profile is
still refused by ``build_sample_lut.py`` and by the module's own build-id gate.
"""
from __future__ import annotations

import hashlib
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent
PRIVATE_INPUTS = Path(os.environ.get('QUEST_LD_PRIVATE_INPUTS', ROOT / '.private-inputs')).resolve()

# A profile is a flat mapping of reviewed constants. Names mirror the roles the
# oracles execute; ``code`` entries are half-open ranges passed to emu_start.
PROFILES = {
    'v207': {
        'name': 'v207',
        'vros_build': 207,
        'sha256': '0ffc0216e3904307d8504e4080c4481db2d29030d4bdccfcef462e3809846b11',
        'build_id': '0eb23622baf2a50528534f27ea1eccdde3fd8dd7',
        # instruction identity at the two hook sites
        'sample_instruction': 0x1e249000,
        'lut_instruction': 0x1e2e1000,
        # data
        'b': 0xe43588,            # x27: pair/metadata base
        'selector': 0xe459e8,     # b + 0x2460
        'matrix': 0xe435e8,       # b + 0x60
        'stride': 0xe435d0,
        'raw_ptr': 0xe435d8,
        'x20': 0xe45000,          # page base used to reach the selector
        'vector': 0xe46f90,
        'header': 0xe46bf0,       # native LUT table begin/end pair
        'x24_page': 0xe46000,     # page base of the header pair
        'hist0': 0xe46f48,
        'hist1': 0xe46f68,
        'flag0': 0xe46f60,
        'flag1': 0xe46f80,
        'scratch': 0xe46c50,
        'mode4': 0xe46c68,
        'force_clamp': 0xe46c84,
        'cfg_weight': 0xe42f98,
        'cfg_dilate_x': 0xe43040,
        'cfg_dilate_y': 0xe430e8,
        'cfg_gaussian': 0xe43190,
        'cfg_smooth': 0xe43238,
        'smooth_args': False,
        'cfg_field': 0x98,
        'eye_structs': 0xe46c30,  # b + 0x3698, 24 bytes per eye
        'got_expf': 0xe19940,
        'got_powf': 0xe19918,
        'trace_ctx': 0xe17ed8,
        # code
        'code': {
            'sample': (0x72e908, 0x72ec4c),
            'lut': (0x72f930, 0x72fa98),
            'frame': (0x72e8a4, 0x72fa98),
            'original': (0x72e8a4, 0x730278),
            'dilate': (0x72ed60, 0x72f074),
            'kernel': (0x72f170, 0x72f274),
            'gaussian': (0x72f274, 0x72f81c),
            'smooth': (0x7324f8, 0x7326e0),
            'native': (0x73060c, 0x731304),
            'lutgen': (0x72d898, 0x72d9b0),
        },
        'lutgen_skip': 0x72d8bc,
        'lutgen_resume': 0x72d88c,
        'log_site': 0x3fa14c,
        'prop_refresh': 0xd80c18,
        'resize_vector': 0x3a77c8,
        'return_addr': 0x730278,
        'trace_calls': (0x7302ec, 0x730324),
        'write_sites': (0x72ea90, 0x72ec2c, 0x72f99c, 0x72fa4c),
        'native_text': (0x72e8a4, 0x73027c),
        'pause': (0x72e8a4, 0x73027c),
    },
    'v204': {
        'name': 'v204',
        'vros_build': 204,
        'sha256': '840cb7661532ff53a40387cfb17a5c89ccdb114bc9231149b84e5df0e826ef1a',
        'build_id': 'db13c881de5413625c45464ba68b1d9be4cd739e',
        'sample_instruction': 0x1e249000,
        'lut_instruction': 0x1e2e1000,
        'b': 0xe072b0,
        'selector': 0xe09710,
        'matrix': 0xe07310,
        'stride': 0xe072f8,
        'raw_ptr': 0xe07300,
        'x20': 0xe09000,
        'vector': 0xe0acb8,
        'header': 0xe0a918,
        'x24_page': 0xe0a000,
        'hist0': 0xe0ac70,
        'hist1': 0xe0ac90,
        'flag0': 0xe0ac88,
        'flag1': 0xe0aca8,
        'scratch': 0xe0a978,
        'mode4': 0xe0a990,
        'force_clamp': 0xe0a9ac,
        'cfg_weight': 0xe06e18,
        'cfg_dilate_x': 0xe06ec0,
        'cfg_dilate_y': 0xe06f68,
        'cfg_gaussian': 0xe07010,
        'cfg_smooth': 0xe070b8,
        'smooth_args': True,
        'cfg_field': 0x98,
        'eye_structs': 0xe0a948,
        'got_expf': 0xdc6448,
        'got_powf': 0xdc6428,
        'trace_ctx': 0xdc4dd0,
        'code': {
            'sample': (0x7133cc, 0x713710),
            'lut': (0x7143f4, 0x71455c),
            'frame': (0x713368, 0x71455c),
            'original': (0x713368, 0x714d3c),
            'dilate': (0x713824, 0x713b38),
            'kernel': (0x713c34, 0x713d38),
            'gaussian': (0x713d38, 0x7142e0),
            'smooth': (0x716e34, 0x7170d4),
            'native': (0x7150d0, 0x715dc8),
            'lutgen': (0x71235c, 0x712474),
        },
        'lutgen_skip': 0x712380,
        'lutgen_resume': 0x712350,
        'log_site': 0x3cba2c,
        'prop_refresh': 0xcb660c,
        'resize_vector': 0x389b74,
        'header_resize': 0x7164b0,
        'return_addr': 0x714d3c,
        'trace_calls': (0x714db0, 0x714de8),
        'write_sites': (0x713554, 0x7136f0, 0x714460, 0x714510),
        'native_text': (0x713368, 0x714d40),
        'pause': (0x713368, 0x714d40),
    },
}


def image_path() -> Path:
    return Path(os.environ.get('QUEST_LD_RUNTIME_IMAGE', PRIVATE_INPUTS / 'libvrruntimeservice.so')).resolve()


def sha256_of(path: Path) -> str:
    with path.open('rb') as file:
        digest = hashlib.sha256()
        for block in iter(lambda: file.read(1 << 20), b''):
            digest.update(block)
        return digest.hexdigest()


def select(path: Path | None = None) -> dict:
    """Return the reviewed profile for the selected or supplied image.

    An explicit QUEST_LD_PROFILE wins. Otherwise the image SHA256 selects the
    profile, so a mismatched image can never silently borrow another profile.
    """
    forced = os.environ.get('QUEST_LD_PROFILE')
    if forced:
        if forced not in PROFILES:
            raise SystemExit(f'QUEST_LD_PROFILE must be one of {sorted(PROFILES)}')
        profile = PROFILES[forced]
        target = Path(path) if path else image_path()
        if target.is_file():
            digest = sha256_of(target)
            if digest != profile['sha256']:
                raise SystemExit(f'{target} is not the {forced} image (sha256 {digest})')
        return profile
    target = Path(path) if path else image_path()
    if target.is_file():
        digest = sha256_of(target)
        for profile in PROFILES.values():
            if profile['sha256'] == digest:
                return profile
        raise SystemExit(f'Unsupported runtime image: {target} (sha256 {digest})')
    return PROFILES['v207']
