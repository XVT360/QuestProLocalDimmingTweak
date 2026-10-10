"""Run actually compiled Android C++ with original ARM64/libm in Unicorn."""
import base64
import hashlib
import json
import random
import struct

from native_oracle import Oracle, ROOT, LIBM_BASE, LIBM, PRIVATE_INPUTS, pack, regs
from elftools.elf.elffile import ELFFile
from unicorn import UC_HOOK_CODE

BASE = 0x8000000
INPUT = 0x9000000
OUTPUT = 0x9100000
STOP = 0x9200000
LIBRARY = ROOT/'sample_lut_build/libs/arm64-v8a/libsample_lut_test.so'


class Compiled(Oracle):
    def __init__(self):
        super().__init__()
        self.uc.mem_map(BASE, 0x100000)
        self.uc.mem_map(INPUT, 0x100000)
        self.uc.mem_map(OUTPUT, 0x100000)
        self.uc.mem_map(STOP, 0x1000)
        self.load_elf(LIBRARY, BASE)
        self.symbols = {}
        with LIBM.open('rb') as file:
            symbols = ELFFile(file).get_section_by_name('.dynsym')
            libm_symbols = {s.name: LIBM_BASE+s['st_value'] for s in symbols.iter_symbols() if s['st_shndx'] != 'SHN_UNDEF'}
        with LIBRARY.open('rb') as file:
            elf = ELFFile(file)
            symbols = elf.get_section_by_name('.dynsym')
            self.symbols = {s.name: BASE+s['st_value'] for s in symbols.iter_symbols() if s['st_shndx'] != 'SHN_UNDEF'}
            externals = {}
            for section in elf.iter_sections():
                if section['sh_type'] not in ['SHT_RELA', 'SHT_REL']:
                    continue
                table = elf.get_section(section['sh_link'])
                for relocation in section.iter_relocations():
                    kind = relocation['r_info_type']
                    addend = relocation['r_addend'] if section['sh_type'] == 'SHT_RELA' else 0
                    destination = BASE + relocation['r_offset']
                    symbol = table.get_symbol(relocation['r_info_sym'])
                    if kind == 1027:
                        value = BASE + addend
                    elif kind in [257, 1025, 1026]:
                        if symbol['st_shndx'] != 'SHN_UNDEF':
                            value = BASE + symbol['st_value'] + addend
                        elif symbol.name in libm_symbols:
                            value = libm_symbols[symbol.name] + addend
                        else:
                            if symbol.name not in externals:
                                externals[symbol.name] = STOP + 0x100 + len(externals)*4
                            value = externals[symbol.name]
                    else:
                        raise AssertionError(('unsupported relocation', kind))
                    self.u64(destination, value)
            def external(uc, address, size, user):
                name = next(k for k,v in externals.items() if v == address)
                destination = uc.reg_read(regs.UC_ARM64_REG_X0)
                source = uc.reg_read(regs.UC_ARM64_REG_X1)
                count = uc.reg_read(regs.UC_ARM64_REG_X2)
                if name in ['memcpy', 'memmove']:
                    uc.mem_write(destination, bytes(uc.mem_read(source, count)))
                elif name == 'memset':
                    uc.mem_write(destination, bytes([source & 255])*count)
                else:
                    raise AssertionError(('unexpected external call', name, hex(uc.reg_read(regs.UC_ARM64_REG_LR))))
                self.reg('pc', uc.reg_read(regs.UC_ARM64_REG_LR))
            if externals:
                self.uc.hook_add(UC_HOOK_CODE, external, begin=min(externals.values()), end=max(externals.values()))

    def call(self, name, integers, number=None):
        self.prepare()
        self.reg('x30', STOP)
        for i, value in enumerate(integers):
            self.reg('x'+str(i), value)
        if number is not None:
            self.reg('s0', struct.unpack('<I', struct.pack('<f', number))[0])
        self.execute(self.symbols[name], STOP)
        return self.uc.reg_read(regs.UC_ARM64_REG_W0)


def generate():
    machine = Compiled()
    fixtures = json.loads((ROOT/'native_oracle_evidence/fixtures.json').read_text())
    cases = []
    # More than 1024 entries reproduces the live lookup scale; test entries
    # at the tail, adjacent mappings, holes, permissions and address overflow.
    ranges = [(0x10000000+i*0x2000, 0x10001000+i*0x2000, True, True) for i in range(4096)]
    blob = b''.join(struct.pack('<QQ??6x', *r) for r in ranges)
    machine.uc.mem_write(INPUT, blob)
    checks = [(4095, 0x100, 1, 1), (3658, 0x100, 0, 1), (1024, 0x1100, 0, 0)]
    for index, span, writable, expected in checks:
        assert machine.call('test_ranges', [INPUT,len(ranges),ranges[index][0],span,writable]) == expected
        cases.append('large_mapping_lookup')
    for rows, at, span, writable, expected in [
        ([(0x1000,0x2000,True,True),(0x2000,0x3000,True,True)],0x1800,0x1000,1,1),
        ([(0x1000,0x2000,True,True),(0x2100,0x3000,True,True)],0x1800,0x1000,1,0),
        ([(0x1000,0x3000,True,False)],0x1800,0x1000,1,0),
        ([(0x1000,0x3000,False,True)],0x1800,0x1000,0,0),
        ([],(1<<64)-10,20,0,0),
    ]:
        if rows: machine.uc.mem_write(INPUT, b''.join(struct.pack('<QQ??6x',*r) for r in rows))
        assert machine.call('test_ranges',[INPUT,len(rows),at,span,writable]) == expected
        cases.append('mapping_guards')
    for c in fixtures['cases']:
        if c['stage'] == 'sample':
            raw = base64.b64decode(c['raw'])
            machine.uc.mem_write(INPUT, raw)
            assert machine.call('test_sample', [INPUT, len(raw), c['stride'], 1, OUTPUT], 0) == 1
            expected = base64.b64decode(c['after']['buffers'])[c['selector']*0x1200:(c['selector']+1)*0x1200]
            assert bytes(machine.uc.mem_read(OUTPUT, 0x1200)) == expected
            cases.append('original_sampling')
        if c['stage'] == 'lut':
            values = base64.b64decode(c['before'])[c['selector']*0x1200:(c['selector']+1)*0x1200]
            machine.uc.mem_write(INPUT, values)
            machine.uc.mem_write(INPUT+0x8000, (PRIVATE_INPUTS/'lut.bin').read_bytes())
            assert machine.call('test_lut', [INPUT, INPUT+0x8000, 21, OUTPUT]) == 1
            expected = base64.b64decode(c['after']['buffers'])[c['selector']*0x1200:(c['selector']+1)*0x1200]
            assert bytes(machine.uc.mem_read(OUTPUT, 0x1200)) == expected
            cases.append('original_lut')
        if c['stage'] == 'lut_generate':
            count = machine.call('test_curve', [c['threshold'], OUTPUT], c['gamma'])
            assert count == c['threshold']+1
            assert bytes(machine.uc.mem_read(OUTPUT, count*2)) == base64.b64decode(c['after'])
            cases.append('android_powf_curve')
    raw = bytearray(1536*192)
    raw[0:4] = b'\xff\xff\xff\x00'
    raw[720:724] = b'\xff\xff\xff\x00'
    machine.uc.mem_write(INPUT, bytes(raw))
    for mode, weight, expected in [(1,0,4.25),(2,0,255),(3,0,4.25),(3,1,255),(3,0.5,129.625)]:
        assert machine.call('test_sample', [INPUT, len(raw), 1536, mode, OUTPUT], weight) == 1
        pair = list(struct.unpack('<1152f', machine.uc.mem_read(OUTPUT, 0x1200)))
        assert pair[0] == expected and pair[576] == expected and sum(v != 0 for v in pair) == 2
        cases.append('impulse_sampler')
    for args in [[INPUT,len(raw)-1,1536,1,OUTPUT], [INPUT,len(raw),720,1,OUTPUT]]:
        # First case's declared extent still covers the sampled rows: deliberately
        # shrink below required, not merely below full stride*192 allocation.
        if args[2] == 1536: args[1] = 191*1536+1440-1
        machine.uc.mem_write(OUTPUT, b'\xaa'*0x1200)
        assert machine.call('test_sample', args, 0) == 0
        assert bytes(machine.uc.mem_read(OUTPUT, 0x1200)) == b'\xaa'*0x1200
        cases.append('extent_rejection')
    for mode, use_lut, arm, result in [(1,0,0,0),(1,0,1,1),(1,1,1,11),(0,1,1,10)]:
        machine.uc.mem_write(OUTPUT, pack([10.0]*1152))
        assert machine.call('test_controller', [INPUT, len(raw),1536,OUTPUT,mode,use_lut,arm]) == result
        cases.append('compiled_controller')
    report = dict(cases=len(cases), stages=cases, library_sha256=hashlib.sha256(LIBRARY.read_bytes()).hexdigest(),
                  scope='Actual NDK-compiled sampling/LUT/controller in Unicorn; target Android powf. libc memory calls shimmed. No live installer/timing test.')
    (ROOT/'sample_lut_evidence/compiled_report.json').write_text(json.dumps(report, indent=2)+'\n')
    print(json.dumps(report, indent=2))


if __name__ == '__main__':
    generate()
