"""Offline oracle: original Quest ARM64 instructions, with no device operations.

Arithmetic, loops and indexing execute unmodified inside Unicorn. Host shims
supply only a property-refresh no-op and vector storage when running a frame.
The runtime and Android expf code are pinned by SHA256 in generated evidence.
"""
from __future__ import annotations
import base64
import hashlib
import json
import os
from pathlib import Path
import random
import struct
import sys

ROOT = Path(__file__).resolve().parent
from unicorn import Uc, UC_ARCH_ARM64, UC_MODE_ARM, UC_HOOK_CODE, __version__ as UC_VERSION
import unicorn.arm64_const as regs
from elftools.elf.elffile import ELFFile

from runtime_images import image_path, select

PRIVATE_INPUTS = Path(os.environ.get('QUEST_LD_PRIVATE_INPUTS', ROOT / '.private-inputs')).resolve()
SO = image_path()
LIBM = PRIVATE_INPUTS / 'libm.so'
# Reviewed image profile: every address below is evidence from SO itself and the
# SHA256 of SO must match this profile. No profile inherits another's values.
PROFILE = select(SO)
CODE = PROFILE['code']
B = PROFILE['b']
SELECTOR = PROFILE['selector']
VECTOR = PROFILE['vector']
STRIDE = PROFILE['stride']
RAW_PTR = PROFILE['raw_ptr']
X20 = PROFILE['x20']
HEADER = PROFILE['header']
X24_PAGE = PROFILE['x24_page']
HIST0, HIST1 = PROFILE['hist0'], PROFILE['hist1']
FLAG0, FLAG1 = PROFILE['flag0'], PROFILE['flag1']
SCRATCH_CELL = PROFILE['scratch']
MODE4 = PROFILE['mode4']
FORCE_CLAMP = PROFILE['force_clamp']
CFG_WEIGHT = PROFILE['cfg_weight']
CFG_OBJECTS = (PROFILE['cfg_dilate_x'], PROFILE['cfg_dilate_y'], PROFILE['cfg_gaussian'], PROFILE['cfg_smooth'])
CFG_FIELD = PROFILE['cfg_field']
EYE_STRUCTS = PROFILE['eye_structs']
GOT_EXPF, GOT_POWF = PROFILE['got_expf'], PROFILE['got_powf']
TRACE_CTX = PROFILE['trace_ctx']
KERNEL = 0x5000000
SCRATCH = 0x5100000
RAW = 0x5200000
HISTORY = 0x5300000
STACK = 0x7000000
SP = STACK + 0x8000
LIBM_BASE = 0x6000000
CELLS = 576
PAIR_BYTES = 0x1200
LUT = [0,409,819,1228,1638,2047,2457,2866,3276,3685,4095,
       4504,4914,5323,5733,6142,6552,6961,7371,7780,8190]


def pack(values):
    return struct.pack('<%df' % len(values), *values)


def unpack(data):
    return list(struct.unpack('<%df' % (len(data)//4), data))


def b64(data):
    return base64.b64encode(data).decode('ascii')


class Oracle:
    def __init__(self):
        self.uc = Uc(UC_ARCH_ARM64, UC_MODE_ARM)
        self.uc.mem_map(0, 0xf00000)
        self.uc.mem_map(LIBM_BASE, 0x40000)
        for addr in [KERNEL, SCRATCH, RAW, HISTORY, STACK]:
            self.uc.mem_map(addr, 0x100000)
        self.load_elf(SO, 0)
        self.load_elf(LIBM, LIBM_BASE)
        with LIBM.open('rb') as f:
            symbols = ELFFile(f).get_section_by_name('.dynsym')
            expf = symbols.get_symbol_by_name('expf')[0]['st_value']
            powf = symbols.get_symbol_by_name('powf')[0]['st_value']
        self.u64(GOT_EXPF, LIBM_BASE + expf)
        self.u64(GOT_POWF, LIBM_BASE + powf)
        self.u64(TRACE_CTX, SCRATCH)  # trace flag at +3 is zero
        self.uc.reg_write(regs.UC_ARM64_REG_TPIDR_EL0, SCRATCH+0x100)
        self.u64(VECTOR, KERNEL)
        self.u64(VECTOR+8, KERNEL)
        self.u64(VECTOR+16, KERNEL+0x10000)
        self.uc.mem_write(SCRATCH+0x1000, struct.pack('<21H', *LUT))
        self.u64(HEADER, SCRATCH+0x1000)
        self.u64(HEADER+8, SCRATCH+0x1000+42)
        self.uc.mem_write(FLAG0, b'\x01')
        self.uc.mem_write(FLAG1, b'\x01')
        self.u64(HIST0, HISTORY)
        self.u64(HIST1, HISTORY+0x900)
        self.uc.hook_add(UC_HOOK_CODE, self.property_refresh,
                         begin=PROFILE['prop_refresh'], end=PROFILE['prop_refresh'])
        self.uc.hook_add(UC_HOOK_CODE, self.resize_vector,
                         begin=PROFILE['resize_vector'], end=PROFILE['resize_vector'])
        self.prepare()

    def load_elf(self, path, base):
        with path.open('rb') as f:
            for seg in ELFFile(f).iter_segments():
                if seg['p_type'] == 'PT_LOAD':
                    self.uc.mem_write(base+seg['p_vaddr'], seg.data())

    def property_refresh(self, uc, address, size, user):
        # Unchanged property: caller has already cleared the changed byte.
        # Its own instructions then read the explicitly seeded cache/fallback.
        uc.reg_write(regs.UC_ARM64_REG_X0, 0)
        uc.reg_write(regs.UC_ARM64_REG_X1, 0)
        uc.reg_write(regs.UC_ARM64_REG_PC, uc.reg_read(regs.UC_ARM64_REG_LR))

    def resize_vector(self, uc, address, size, user):
        assert uc.reg_read(regs.UC_ARM64_REG_X0) == VECTOR
        n = uc.reg_read(regs.UC_ARM64_REG_X1)
        end = struct.unpack('<Q', uc.mem_read(VECTOR+8, 8))[0]
        assert KERNEL <= end <= KERNEL+0x10000 and end+n*4 <= KERNEL+0x10000
        uc.mem_write(end, bytes(n*4))
        self.u64(VECTOR+8, end+n*4)
        uc.reg_write(regs.UC_ARM64_REG_PC, uc.reg_read(regs.UC_ARM64_REG_LR))

    def u64(self, at, value):
        self.uc.mem_write(at, struct.pack('<Q', value))

    def i32(self, at, value):
        self.uc.mem_write(at, struct.pack('<i', value))

    def reg(self, name, value):
        self.uc.reg_write(getattr(regs, 'UC_ARM64_REG_'+name.upper()), value)

    def prepare(self):
        self.reg('sp', SP)
        self.reg('x29', SP+0x100)
        self.reg('x20', X20)
        self.reg('x27', B)
        self.reg('x28', SCRATCH)
        self.reg('fpcr', 0)  # nearest-even, gradual underflow

    def execute(self, start, end):
        self.uc.emu_start(start, end, count=15_000_000)
        pc = self.uc.reg_read(regs.UC_ARM64_REG_PC)
        assert pc == end, f'Execution limit or unexpected branch: {pc:#x}, expected {end:#x}'

    def state(self):
        return dict(selector=struct.unpack('<i', self.uc.mem_read(SELECTOR, 4))[0],
                    buffers=b64(self.uc.mem_read(B+0x60, PAIR_BYTES*2)),
                    history=b64(self.uc.mem_read(HISTORY, PAIR_BYTES)))

    def seed(self, data, selector):
        assert len(data) == PAIR_BYTES*2
        self.uc.mem_write(B+0x60, data)
        self.i32(SELECTOR, selector)
        self.prepare()

    def config(self, x=1, y=2, gaussian=3, smooth=1, weight=0.3, property_valid=1):
        for obj, value in zip(CFG_OBJECTS, (x, y, gaussian, smooth)):
            self.uc.mem_write(obj+CFG_FIELD, struct.pack('<iB3xi', value if property_valid else 0, property_valid, value))
        self.uc.mem_write(CFG_WEIGHT+CFG_FIELD, struct.pack('<fB3xf', weight if property_valid else 0, property_valid, weight))

    def sample(self, raw, stride):
        self.uc.mem_write(RAW, raw)
        self.i32(STRIDE, stride)
        self.reg('x19', RAW)
        self.execute(*CODE['sample'])

    def dilate(self, x, y):
        assert x >= 0 and y >= 0
        self.reg('x19', y)
        self.reg('x21', x)
        self.reg('x22', x)
        self.execute(*CODE['dilate'])

    def kernel(self, size):
        self.prepare()
        self.reg('x19', KERNEL)
        self.reg('x21', size)
        self.u64(SP+0x10, size*size)
        self.u64(SP+0x28, size>>1)
        self.u64(SP+0x30, size)
        self.u64(VECTOR+8, KERNEL+size*size*4)
        self.execute(*CODE['kernel'])
        return bytes(self.uc.mem_read(KERNEL, size*size*4))

    def gaussian(self, size, kernel):
        assert size >= 1 and len(kernel) == size*size*4
        self.prepare()
        self.uc.mem_write(KERNEL, kernel)
        self.u64(VECTOR+8, KERNEL+len(kernel))
        self.u64(SP+0x10, size*size)
        self.u64(SP+0x28, size>>1)
        self.u64(SP+0x30, size)
        self.reg('x19', KERNEL)
        self.reg('x21', size)
        self.reg('x22', self.state()['selector'])
        self.execute(*CODE['gaussian'])

    def smooth(self, current, previous, weight, valid=1):
        self.uc.mem_write(HISTORY, previous)
        self.uc.mem_write(SCRATCH+0x4000, current)
        if PROFILE['smooth_args']:
            # This image takes (target, source) as arguments and reads the
            # weight/valid pair from the reviewed object itself.
            self.reg('x0', SCRATCH+0x4000)
            self.reg('x1', HISTORY)
        else:
            self.reg('x19', HISTORY)
            self.reg('x20', SCRATCH+0x4000)
            self.reg('x21', CFG_WEIGHT)
            self.reg('w8', valid)
        self.uc.mem_write(CFG_WEIGHT+CFG_FIELD, struct.pack('<fB3xf', weight, valid, weight))
        self.execute(*CODE['smooth'])
        return bytes(self.uc.mem_read(SCRATCH+0x4000, 0x900)), bytes(self.uc.mem_read(HISTORY, 0x900))

    def lut(self):
        self.execute(*CODE['lut'])

    def generate_lut(self, threshold, gamma):
        assert threshold > 0 and gamma > 0
        self.prepare()
        self.reg('s8', struct.unpack('<I', struct.pack('<f', gamma))[0])
        self.reg('s9', struct.unpack('<I', struct.pack('<f', threshold))[0])
        self.reg('s10', struct.unpack('<I', struct.pack('<f', 8190))[0])
        self.reg('x24', X24_PAGE)
        self.reg('x25', 0)
        self.reg('x27', threshold+1)
        self.u64(HEADER, SCRATCH+0x1000)
        # Skip only the string formatting/logging after each table store.
        def skip_format(uc, address, size, user):
            self.reg('pc', PROFILE['lutgen_resume'])
        hook = self.uc.hook_add(UC_HOOK_CODE, skip_format,
                                begin=PROFILE['lutgen_skip'], end=PROFILE['lutgen_skip'])
        try:
            self.execute(*CODE['lutgen'])
            return bytes(self.uc.mem_read(SCRATCH+0x1000, 2*(threshold+1)))
        finally:
            self.uc.hook_del(hook)

    def native_mapping(self, force_clamp_code):
        self.prepare()
        self.i32(MODE4, 0)  # ordinary mode, no diagnostic uniform value
        # S7: substitutes the software code 8190, not measured LED luminance.
        self.i32(FORCE_CLAMP, force_clamp_code)
        for eye in [0,1]:
            at = EYE_STRUCTS+eye*24
            self.u64(at, SCRATCH+0x10000+eye*0x1000)
            # 576 big-endian halfwords followed by a zero byte. Confirmed by
            # 0x72cfb4 / 0x72d0e4 and native_output_audit_20261007.
            self.u64(at+8, SCRATCH+0x10000+eye*0x1000+0x481)
        self.u64(SCRATCH_CELL, SCRATCH+0x8000)
        self.u64(SCRATCH+0x8000, SCRATCH+0x9000)
        self.u64(SCRATCH+0x9030, SCRATCH+0xa000)
        payloads = []
        def record_submit(uc, address, size, user):
            ptr = uc.reg_read(regs.UC_ARM64_REG_X1)
            count = uc.reg_read(regs.UC_ARM64_REG_X2)
            eye = uc.reg_read(regs.UC_ARM64_REG_X3)
            payloads.append(dict(eye=eye, bytes=b64(uc.mem_read(ptr, count))))
            self.reg('x0', 0)
            self.reg('pc', uc.reg_read(regs.UC_ARM64_REG_LR))
        hook = self.uc.hook_add(UC_HOOK_CODE, record_submit, begin=SCRATCH+0xa000, end=SCRATCH+0xa000)
        try:
            self.execute(*CODE['native'])
            return payloads
        finally:
            self.uc.hook_del(hook)

    def frame(self, raw, stride, config):
        self.prepare()
        self.config(**config)
        self.uc.mem_write(RAW, raw)
        self.i32(STRIDE, stride)
        self.u64(RAW_PTR, RAW)
        self.execute(*CODE['frame'])
        return self.state()


def generate():
    out = ROOT / 'native_oracle_evidence'
    out.mkdir(exist_ok=True)
    rng = random.Random(20261007)
    random_buffers = pack([rng.uniform(0, 30) for _ in range(CELLS*4)])
    labelled_buffers = pack([i/64 for i in range(CELLS*4)])
    oracle = Oracle()
    evidence = dict(schema=2, unicorn=UC_VERSION, fpcr=0,
        runtime_sha256=hashlib.sha256(SO.read_bytes()).hexdigest(),
        libm_sha256=hashlib.sha256(LIBM.read_bytes()).hexdigest(),
        scope='Original ARM64 arithmetic; host shims only for property refresh, vector storage, LUT logging skip, and hardware submission recording.', cases=[])
    cases = evidence['cases']
    for stride in [1440, 1472]:
        raw = rng.randbytes(stride*192)
        for selector in [0, 1]:
            oracle.seed(random_buffers, selector)
            oracle.sample(raw, stride)
            cases.append(dict(stage='sample', selector=selector, stride=stride, raw=b64(raw),
                              before=b64(random_buffers), after=oracle.state()))
    # (256,512) is a rejected-radius regression, NOT the native default.
    for x,y in [(0,0),(1,0),(0,2),(1,2),(2,3),(8,15),(9,2),(1,16),(256,512)]:
        for selector in [0,1]:
            oracle.seed(labelled_buffers, selector)
            oracle.dilate(x,y)
            cases.append(dict(stage='dilate', selector=selector, x=x, y=y,
                              before=b64(labelled_buffers), after=oracle.state()))
    for size in range(1,34):
        kernel = oracle.kernel(size)
        cases.append(dict(stage='kernel', size=size, after=b64(kernel)))
        for labelled in [False, True]:
            coeff = pack([(i+1)/128 for i in range(size*size)]) if labelled else kernel
            for selector in [0,1]:
                oracle.seed(random_buffers, selector)
                oracle.gaussian(size, coeff)
                cases.append(dict(stage='gaussian', size=size, labelled=labelled, selector=selector,
                    kernel=b64(coeff), before=b64(random_buffers), after=oracle.state()))
    for weight in [0,0.1,0.3,0.5,1]:
        for valid in [0,1]:
            current = random_buffers[:0x900]
            previous = random_buffers[0x900:0x1200]
            a,b = oracle.smooth(current, previous, weight, valid)
            assert a == b
            cases.append(dict(stage='smooth', weight=weight, valid=valid,
                              current=b64(current), previous=b64(previous), after=b64(a)))
    probes = [0,0.5,1,10,19.5,19.999998092651367,20,21,255]
    vals = probes + [rng.uniform(0,40) for _ in range(CELLS*4-len(probes))]
    data = pack(vals)
    for selector in [0,1]:
        oracle.seed(data, selector)
        oracle.lut()
        cases.append(dict(stage='lut', selector=selector, before=b64(data), after=oracle.state()))
    for threshold, gamma in [(20,1),(20,2),(20,0.5),(40,1),(255,1),(20,2.2)]:
        table = oracle.generate_lut(threshold, gamma)
        cases.append(dict(stage='lut_generate', threshold=threshold, gamma=gamma, after=b64(table)))
    assert oracle.generate_lut(20,1) == (PRIVATE_INPUTS/'lut.bin').read_bytes()
    # Exercise the untouched native mapping, capturing submission in host memory.
    # Sentinel codes distinguish 255 from 8190 and expose any hidden byte
    # truncation, scaling, or endian swap before the actual submit callback.
    codes = [0, 0.5, 1, 254.5, 255, 256, 4095, 8189.5, 8190]
    sentinel_buffers = pack([codes[i % len(codes)] for i in range(CELLS*4)])
    for input_kind, data in [('random', random_buffers), ('code_sentinels', sentinel_buffers)]:
        for selector in [0,1]:
            for force_clamp_code in [0,1]:
                oracle.seed(data, selector)
                before = oracle.state()
                payloads = oracle.native_mapping(force_clamp_code)
                assert oracle.state() == before, 'Mapping mutated algorithm/history state'
                cases.append(dict(stage='native_mapping', input_kind=input_kind, selector=selector,
                                  force_clamp_code=force_clamp_code, before=before, payloads=payloads))
    # Continuous frames include native cache reuse, selector flips, LUT mutations
    # and historical border contents. Start from zeroed storage, like BSS.
    oracle = Oracle()
    configs = [dict(property_valid=0), {}, dict(property_valid=0), dict(x=0,y=0,gaussian=2), dict(x=1,y=2,gaussian=3),
               dict(x=0,y=2,gaussian=4,smooth=0), dict(gaussian=9,weight=0.5),
               dict(gaussian=0), {}, dict(x=0,y=0,gaussian=0,smooth=0)]
    for index, config in enumerate(configs):
        raw = bytearray(1440*192)
        for _ in range(300):
            pos = rng.randrange(360*192)*4
            raw[pos:pos+4] = bytes([rng.randrange(256) for _ in range(4)])
        before = oracle.state()
        after = oracle.frame(bytes(raw), 1440, config)
        cases.append(dict(stage='frame', index=index, config=config, stride=1440, raw=b64(raw),
                          before=before, after=after))
    (out/'fixtures.json').write_text(json.dumps(evidence, separators=(',',':')), encoding='utf-8')
    print(json.dumps({k:v for k,v in evidence.items() if k != 'cases'}, indent=2))
    print('Saved', len(cases), 'original-instruction cases to', out/'fixtures.json')
    k3 = next(c for c in cases if c['stage']=='kernel' and c['size']==3)
    captured = (PRIVATE_INPUTS/'kernel_prefix.bin').read_bytes()[:36]
    assert base64.b64decode(k3['after']) == captured, 'size3 kernel disagrees with live read-only capture'
    print('Emulated size3 kernel and default LUT match live captured bytes exactly.')


if __name__ == '__main__':
    generate()
