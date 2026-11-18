"""Prepare and test a preserving ARM64 bridge as data, without a compiler.

The generated header is source for a future module, not an installable image.
Unicorn executes those exact words with a deliberately destructive callback.
There is no process injection, executable host mapping or device operation.
"""
from __future__ import annotations

import hashlib
import json
import random
import struct

from native_oracle import ROOT, regs, PROFILE, CODE, X20, B
from unicorn import Uc, UC_ARCH_ARM64, UC_MODE_ARM, UC_HOOK_CODE
from capstone import Cs, CS_ARCH_ARM64, CS_MODE_ARM

FRAME = 0x320 # x0..x30, original SP, q0..q31, NZCV/FPCR/FPSR and padding
SITE = 0x100000
BRIDGE = 0x120000
CALLBACK = 0x130000
STACK = 0x200000
SP = STACK + 0x10000
SUCCESS = SITE + 0x1000
IMAGE = 0x7100000000


def template():
    words, slots = [], {}
    def emit(word):
        words.append(word)
    def slot(name, word):
        slots[name] = len(words)
        emit(word)
    def pair(base, r, offset, scale):
        assert 0 <= offset // scale < 64 and offset % scale == 0
        return base | ((offset // scale) << 15) | ((r + 1) << 10) | (31 << 5) | r
    def single(base, r, offset):
        assert offset % 8 == 0
        return base | ((offset // 8) << 10) | (31 << 5) | r
    emit(0xd10003ff | (FRAME << 10)) # sub sp, sp, #FRAME
    for r in range(0, 30, 2):
        emit(pair(0xa9000000, r, r * 8, 8))
    emit(single(0xf9000000, 30, 240))
    emit(0x910003e9 | (FRAME << 10)) # add x9, sp, #FRAME
    emit(single(0xf9000000, 9, 248))
    for r in range(0, 32, 2):
        emit(pair(0xad000000, r, 256 + r * 16, 16))
    for system, offset in [(0xd53b4209, 768), (0xd53b4409, 776), (0xd53b4429, 784)]:
        emit(system)
        emit(single(0xf9000000, 9, offset))
    emit(0x910003e0) # mov x0, sp
    slot('stage', 0x52800001) # mov w1, stage
    slot('load_image', 0x58000002)
    slot('load_callback', 0x58000010)
    emit(0xd63f0200) # blr x16
    emit(0x7100041f) # cmp w0, #1; only Route::Replaced selects success
    slot('select_success', 0x54000000)
    def restore():
        for system, offset in [(0xd51b4429, 784), (0xd51b4409, 776), (0xd51b4209, 768)]:
            emit(single(0xf9400000, 9, offset))
            emit(system)
        for r in range(0, 32, 2):
            emit(pair(0xad400000, r, 256 + r * 16, 16))
        for r in range(0, 30, 2):
            emit(pair(0xa9400000, r, r * 8, 8))
        emit(single(0xf9400000, 30, 240))
        emit(0x910003ff | (FRAME << 10)) # add sp, sp, #FRAME, leaves NZCV
    restore()
    slot('original_instruction', 0xd503201f)
    slot('native_branch', 0x14000000)
    slots['success_restore'] = len(words)
    restore()
    slot('success_branch', 0x14000000)
    if len(words) % 2:
        emit(0xd503201f)
    slot('image_literal', 0)
    emit(0)
    slot('callback_literal', 0)
    emit(0)
    for load, literal in [('load_image', 'image_literal'), ('load_callback', 'callback_literal')]:
        words[slots[load]] |= (slots[literal] - slots[load]) << 5
    words[slots['select_success']] |= (slots['success_restore'] - slots['select_success']) << 5
    return words, slots


def branch(at, target):
    delta = target - at
    if delta % 4 or not -(1 << 27) <= delta < (1 << 27):
        raise ValueError('A direct B must fit the signed 26-word offset')
    return 0x14000000 | ((delta // 4) & 0x03ffffff)


def instantiate_at(words, slots, stage, image, site, bridge, callback, success):
    words = words[:]
    words[slots['stage']] |= stage << 5
    words[slots['original_instruction']] = [0x1e249000, 0x1e2e1000][stage]
    for name, target in [('native_branch', site + 4), ('success_branch', success)]:
        words[slots[name]] = branch(bridge + slots[name] * 4, target)
    for name, value in [('image_literal', image), ('callback_literal', callback)]:
        at = slots[name]
        words[at:at+2] = [value & 0xffffffff, value >> 32]
    return struct.pack('<%dI' % len(words), *words)


def instantiate(words, slots, stage):
    return instantiate_at(words, slots, stage, IMAGE, SITE, BRIDGE, CALLBACK, SUCCESS)


def run_case(words, slots, stage, route, fpcr, rng):
    uc = Uc(UC_ARCH_ARM64, UC_MODE_ARM)
    uc.mem_map(SITE, 0x40000)
    uc.mem_map(STACK, 0x20000)
    uc.mem_write(SITE, struct.pack('<I', branch(SITE, BRIDGE)))
    uc.mem_write(BRIDGE, instantiate(words, slots, stage))
    # A RET is provided so PC can be advanced past the Python callback hook.
    uc.mem_write(CALLBACK, struct.pack('<I', 0xd65f03c0))
    xs = [rng.getrandbits(64) for _ in range(31)]
    qs = [rng.getrandbits(128) for _ in range(32)]
    for i, value in enumerate(xs):
        uc.reg_write(getattr(regs, f'UC_ARM64_REG_X{i}'), value)
    for i, value in enumerate(qs):
        uc.reg_write(getattr(regs, f'UC_ARM64_REG_Q{i}'), value)
    nzcv, fpsr = 0xa0000000, 0x0800001f
    for key, value in [('SP', SP), ('NZCV', nzcv), ('FPCR', fpcr), ('FPSR', fpsr)]:
        uc.reg_write(getattr(regs, 'UC_ARM64_REG_' + key), value)
    caller_stack = rng.randbytes(512)
    uc.mem_write(SP, caller_stack)
    called = []
    def destroy_callback(uc, address, size, user):
        called.append(1)
        context = uc.reg_read(regs.UC_ARM64_REG_X0)
        assert context == SP - FRAME
        assert uc.reg_read(regs.UC_ARM64_REG_X1) == stage
        assert uc.reg_read(regs.UC_ARM64_REG_X2) == IMAGE
        saved = bytes(uc.mem_read(context, FRAME))
        assert struct.unpack('<31Q', saved[:248]) == tuple(xs)
        assert struct.unpack('<Q', saved[248:256])[0] == SP
        assert [int.from_bytes(saved[256+i*16:272+i*16], 'little') for i in range(32)] == qs
        assert struct.unpack('<3Q', saved[768:792]) == (nzcv, fpcr, fpsr)
        resume = uc.reg_read(regs.UC_ARM64_REG_LR)
        # Simulate the sampler's declared live-out contract through saved slots.
        if route == 1 and stage == 0:
            uc.mem_write(context + 20 * 8, struct.pack('<Q', IMAGE + X20))
            uc.mem_write(context + 27 * 8, struct.pack('<Q', IMAGE + B))
        for i in range(31):
            uc.reg_write(getattr(regs, f'UC_ARM64_REG_X{i}'), 0xbaad0000 + i)
        for i in range(32):
            uc.reg_write(getattr(regs, f'UC_ARM64_REG_Q{i}'), (1 << 128) - 1)
        for key in ['NZCV', 'FPCR', 'FPSR']:
            uc.reg_write(getattr(regs, 'UC_ARM64_REG_' + key), 0)
        uc.reg_write(regs.UC_ARM64_REG_X0, route)
        uc.reg_write(regs.UC_ARM64_REG_PC, resume)
    uc.hook_add(UC_HOOK_CODE, destroy_callback, begin=CALLBACK, end=CALLBACK)
    target = SUCCESS if route == 1 else SITE + 4
    uc.emu_start(SITE, target, count=1000)
    assert uc.reg_read(regs.UC_ARM64_REG_PC) == target and len(called) == 1
    for i in range(31):
        expected = xs[i]
        if route == 1 and stage == 0 and i in [20, 27]:
            expected = IMAGE + (X20 if i == 20 else B)
        assert uc.reg_read(getattr(regs, f'UC_ARM64_REG_X{i}')) == expected, ('x', stage, route, i)
    for i in range(32):
        expected = qs[i]
        if route != 1 and i == 0:
            expected = [0x41200000, 0x3f800000][stage] # replayed FMOV s0 also zeroes upper bits
        assert uc.reg_read(getattr(regs, f'UC_ARM64_REG_Q{i}')) == expected, ('q', stage, route, i)
    for key, value in [('SP', SP), ('NZCV', nzcv), ('FPCR', fpcr), ('FPSR', fpsr)]:
        assert uc.reg_read(getattr(regs, 'UC_ARM64_REG_' + key)) == value, key
    assert bytes(uc.mem_read(SP, len(caller_stack))) == caller_stack


def generate():
    words, slots = template()
    rng = random.Random(202610072)
    cases = 0
    for stage in [0, 1]:
        for route in [0, 1, 2, 0xffffffff]:
            for fpcr in [0, 1 << 22, 2 << 22, 3 << 22, 1 << 24, 1 << 25]:
                run_case(words, slots, stage, route, fpcr, rng)
                cases += 1
    assert branch(SITE, SITE - (1 << 27)) == 0x16000000
    assert branch(SITE, SITE + (1 << 27) - 4) == 0x15ffffff
    for dest in [SITE + (1 << 27), SITE - (1 << 27) - 4, SITE + 2]:
        try:
            branch(SITE, dest)
        except ValueError:
            continue
        raise AssertionError('Accepted out-of-range/unaligned branch')
    md = Cs(CS_ARCH_ARM64, CS_MODE_ARM)
    disasm = list(md.disasm(instantiate(words, slots, 0)[:slots['image_literal']*4], BRIDGE))
    assert len(disasm) == slots['image_literal']
    source = '// Generated by stage_bridge_oracle.py; no compiler or device operation.\n#pragma once\n#include <cstddef>\n#include <cstdint>\nnamespace quest_ld::bridge_template {\n'
    source += f'constexpr size_t kFrameBytes = {FRAME};\n'
    for name, index in slots.items():
        source += f'constexpr size_t k_{name} = {index};\n'
    source += 'constexpr uint32_t kWords[] = {\n'
    for i in range(0, len(words), 6):
        source += '    ' + ', '.join(f'0x{w:08x}u' for w in words[i:i+6]) + ',\n'
    source += '};\n} // namespace quest_ld::bridge_template\n'
    target = ROOT / 'zygisk_local_dimming/staged/stage_bridge_words.h'
    target.write_text(source, encoding='utf-8')
    output = ROOT / 'sample_lut_evidence'
    output.mkdir(exist_ok=True)
    (output / 'stage_bridge_disasm.txt').write_text('\n'.join(f'{i.address-BRIDGE:04x}: {i.mnemonic} {i.op_str}' for i in disasm) + '\n', encoding='utf-8')
    report = dict(cases=cases, template_bytes=len(words)*4, frame_bytes=FRAME,
                  source_sha256=hashlib.sha256(target.read_bytes()).hexdigest(),
                  scope='Exact generated ARM64 words in Unicorn with callback destroying all GPR/SIMD/system flags. Two stages, native/replaced/rejected/invalid route, six FPCR patterns. No actual C++ callback, loader, process patch or headset timing test.',
                  result='pass')
    (output / 'bridge_report.json').write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(report, indent=2))


if __name__ == '__main__':
    generate()
