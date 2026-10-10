"""Execute NDK-compiled settings/ldctl in ARM64 Unicorn, with mock OS boundaries.

The C++ parser, CRC, bounds, publish ordering and file workflow run unchanged.
Properties/files/libc are explicit host shims; powf is the captured Android libm.
No ADB calls or device operations are performed.
"""
import hashlib
import json
from pathlib import Path
import re
import struct
import sys
import zlib

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from native_oracle import Oracle, LIBM, LIBM_BASE, regs
from elftools.elf.elffile import ELFFile
from unicorn import UC_HOOK_CODE

BASE, STOP, ARGS = 0x8000000, 0x9000000, 0x9100000
LIBRARY = ROOT / 'sample_lut_build/libs/arm64-v8a/libsettings_test.so'
DIR = '/data/adb/questpro_local_dimming_030'
FILE = DIR + '/settings.bin'
PREFIX = 'debug.oculus.localDimming.zl2.'
DEBUG = 'debug.oculus.localDimming.'
GATES = [PREFIX + k for k in ['enable', 'bypass', 'hook_mode']]


class Control(Oracle):
    def __init__(self):
        super().__init__()
        for at in [BASE, STOP, ARGS]:
            self.uc.mem_map(at, 0x100000)
        self.load_elf(LIBRARY, BASE)
        self.properties = {}
        self.files = {}
        self.fail_write = self.fail_property = None
        self.root = True
        with LIBM.open('rb') as file:
            libm = {s.name: LIBM_BASE + s['st_value'] for s in ELFFile(file).get_section_by_name('.dynsym').iter_symbols()}
        externals = {}
        with LIBRARY.open('rb') as file:
            elf = ELFFile(file)
            table = elf.get_section_by_name('.dynsym')
            self.entry = BASE + table.get_symbol_by_name('test_ldctl')[0]['st_value']
            for section in elf.iter_sections():
                if section['sh_type'] != 'SHT_RELA':
                    continue
                symbols = elf.get_section(section['sh_link'])
                for r in section.iter_relocations():
                    kind, symbol = r['r_info_type'], symbols.get_symbol(r['r_info_sym'])
                    if kind == 1027:
                        value = BASE + r['r_addend']
                    elif symbol['st_shndx'] != 'SHN_UNDEF':
                        value = BASE + symbol['st_value'] + r['r_addend']
                    elif symbol.name == 'powf':
                        value = libm['powf']
                    elif symbol.name == 'stderr':
                        value = STOP + 0x8000
                        self.u64(value, STOP + 0x8010)
                    else:
                        if symbol.name not in externals:
                            externals[symbol.name] = STOP + 0x100 + len(externals) * 4
                        value = externals[symbol.name]
                    self.u64(BASE + r['r_offset'], value)
        self.externals = {address: name for name, address in externals.items()}
        self.uc.hook_add(UC_HOOK_CODE, self.external, begin=min(self.externals), end=max(self.externals))

    def string(self, at):
        return bytes(self.uc.mem_read(at, 4096)).split(b'\0')[0].decode()

    def error(self, code):
        self.uc.mem_write(STOP + 0x9000, struct.pack('<i', code))
        return -1

    def format(self, fmt, next_integer, next_float):
        def replace(match):
            spec = match.group()
            if spec.endswith('g'):
                digits = re.search(r'\.(\d+)', spec)
                return format(next_float(), '.' + (digits.group(1) if digits else '6') + 'g')
            value = next_integer()
            if spec.endswith('s'):
                return self.string(value)
            if spec.endswith('x'):
                # Used by the LUT code exporter: exactly four hex digits.
                return format(value, '04x' if '04' in spec else 'x')
            if spec.endswith('d'):
                value &= 0xffffffff
                value = value if value < 0x80000000 else value - 0x100000000
            return str(value)
        # Width 04 in the LUT formatter must be recognized as well.
        return re.sub(r'%(?:0\d+)?(?:\.\d+)?(?:z|l)?[sudixg]', replace, fmt)

    def printf(self, format_index):
        integer, vector = format_index + 1, 0
        def next_integer():
            nonlocal integer
            value = self.reg_value('x' + str(integer))
            integer += 1
            return value
        def next_float():
            nonlocal vector
            value = self.uc.reg_read(getattr(regs, 'UC_ARM64_REG_Q' + str(vector))) & ((1 << 64) - 1)
            vector += 1
            return struct.unpack('<d', struct.pack('<Q', value))[0]
        return self.format(self.string(self.reg_value('x' + str(format_index))), next_integer, next_float)

    def vsnprintf(self, ap, fmt):
        stack, gr_top, vr_top, gr_off, vr_off = struct.unpack('<QQQii', self.uc.mem_read(ap, 32))
        def next_integer():
            nonlocal stack, gr_off
            if gr_off < 0:
                at = gr_top + gr_off
                gr_off += 8
            else:
                at = stack
                stack += 8
            return struct.unpack('<Q', self.uc.mem_read(at, 8))[0]
        def next_float():
            nonlocal stack, vr_off
            if vr_off < 0:
                at = vr_top + vr_off
                vr_off += 16
            else:
                at = stack
                stack += 8
            return struct.unpack('<d', self.uc.mem_read(at, 8))[0]
        return self.format(self.string(fmt), next_integer, next_float).encode()

    def reg_value(self, name):
        return self.uc.reg_read(getattr(regs, 'UC_ARM64_REG_' + name.upper()))

    def fd(self, name):
        n = len(self.fds) + 10
        self.fds[n] = [name, 0]
        return n

    def open_file(self, name, flags, mode):
        if name == DIR:
            if name not in self.files:
                return self.error(2)
            return self.fd(name)
        if flags & 0x40:
            if flags & 0x80 and name in self.files:
                return self.error(17)
            if name not in self.files:
                self.files[name] = [bytearray(), mode, 0]
        if name not in self.files:
            return self.error(2)
        if self.files[name][1] & 0o170000 == 0o120000:
            return self.error(40)
        if flags & 0x200:
            self.files[name][0] = bytearray()
        return self.fd(name)

    def external(self, uc, at, size, user):
        name = self.externals[at]
        x = [self.reg_value('x' + str(i)) for i in range(8)]
        result = 0
        if name in ['memcpy', '__memcpy_chk', 'memmove']:
            uc.mem_write(x[0], bytes(uc.mem_read(x[1], x[2])))
            result = x[0]
        elif name == 'memset':
            uc.mem_write(x[0], bytes([x[1] & 255]) * x[2])
            result = x[0]
        elif name in ['strcmp', 'memcmp']:
            a, b = (self.string(x[0]), self.string(x[1])) if name == 'strcmp' else (bytes(uc.mem_read(x[0], x[2])), bytes(uc.mem_read(x[1], x[2])))
            result = (a > b) - (a < b)
        elif name in ['strlen', '__strlen_chk']:
            result = len(self.string(x[0]).encode())
        elif name == 'geteuid':
            result = 0 if self.root else 2000
        elif name == '__errno':
            result = STOP + 0x9000
        elif name in ['strtof', 'strtoul']:
            text = self.string(x[0])
            pattern = r'[+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?' if name == 'strtof' else r'\d+'
            match = re.match(pattern, text)
            consumed = len(match.group()) if match else 0
            if x[1]:
                self.u64(x[1], x[0] + consumed)
            value = float(match.group()) if name == 'strtof' and match else int(match.group()) if match else 0
            if name == 'strtof':
                self.reg('s0', struct.unpack('<I', struct.pack('<f', value))[0])
            else:
                result = value
        elif name == '__system_property_get':
            value = self.properties.get(self.string(x[0]), '').encode()
            uc.mem_write(x[1], value + b'\0')
            result = len(value)
        elif name == '__system_property_set':
            key, value = self.string(x[0]), self.string(x[1])
            if key == self.fail_property:
                self.fail_property = None
                result = -1
            else:
                assert len(value.encode()) < 92
                self.properties[key] = value
                self.writes.append((key, value))
        elif name == '__vsnprintf_chk':
            data = self.vsnprintf(x[5], x[4])
            if x[1]:
                uc.mem_write(x[0], data[:x[1] - 1] + b'\0')
            result = len(data)
        elif name in ['printf', 'fprintf']:
            data = self.printf(0 if name == 'printf' else 1)
            self.output += data
            result = len(data)
        elif name == 'puts':
            self.output += self.string(x[0]) + '\n'
        elif name == 'fwrite':
            self.output += bytes(uc.mem_read(x[0], x[1] * x[2])).decode()
            result = x[2]
        elif name == 'mkdir':
            path = self.string(x[0])
            if path in self.files:
                result = self.error(17)
            else:
                self.files[path] = [bytearray(), 0o040000 | x[1], 0]
        elif name in ['open', '__open_2']:
            result = self.open_file(self.string(x[0]), x[1], x[2])
        elif name in ['openat', '__openat_2']:
            path = self.fds[x[0]][0] + '/' + self.string(x[1])
            result = self.open_file(path, x[2], x[3])
        elif name == 'close':
            self.fds[x[0]][1] = -1
        elif name == 'fstat':
            file = self.files[self.fds[x[0]][0]]
            raw = bytearray(128)
            struct.pack_into('<II', raw, 16, file[1] | (0o100000 if file[1] & 0o170000 == 0 else 0), 1)
            struct.pack_into('<I', raw, 24, file[2])
            struct.pack_into('<q', raw, 48, len(file[0]))
            uc.mem_write(x[1], bytes(raw))
        elif name == 'fchmod':
            file = self.files[self.fds[x[0]][0]]
            file[1] = (file[1] & 0o170000) | x[1]
        elif name in ['read', '__read_chk', 'write']:
            fd = self.fds[x[0]]
            file = self.files[fd[0]][0]
            if name == 'write':
                if self.fail_write == 'write':
                    result = self.error(28)
                else:
                    file[fd[1]:fd[1] + x[2]] = uc.mem_read(x[1], x[2])
                    result = x[2]
                    fd[1] += result
            else:
                data = bytes(file[fd[1]:fd[1] + x[2]])
                if data:
                    uc.mem_write(x[1], data)
                result = len(data)
                fd[1] += result
        elif name == 'unlinkat':
            path = self.fds[x[0]][0] + '/' + self.string(x[1])
            if path not in self.files:
                result = self.error(2)
            else:
                del self.files[path]
        elif name == 'renameat':
            old = self.fds[x[0]][0] + '/' + self.string(x[1])
            new = self.fds[x[2]][0] + '/' + self.string(x[3])
            if self.fail_write == 'rename':
                result = self.error(5)
            else:
                self.files[new] = self.files.pop(old)
        elif name == 'fsync':
            if self.fail_write == 'fsync':
                result = self.error(5)
        elif name == 'flock':
            if self.fail_write == 'lock':
                result = self.error(11)
        elif name == 'usleep':
            pass
        else:
            raise AssertionError(('Unexpected libc call', name))
        self.reg('x0', result & ((1 << 64) - 1))
        self.reg('pc', self.reg_value('x30'))

    def run(self, *arguments):
        self.prepare()
        self.fds, self.writes, self.output = {}, [], ''
        self.uc.mem_write(STOP + 0x9000, b'\0' * 4)
        args = ['ldctl', *arguments]
        at = ARGS + 0x1000
        pointers = []
        for arg in args:
            pointers.append(at)
            data = arg.encode() + b'\0'
            self.uc.mem_write(at, data)
            at += len(data)
        self.uc.mem_write(ARGS, struct.pack('<%dQ' % (len(pointers) + 1), *pointers, 0))
        self.reg('x0', len(args))
        self.reg('x1', ARGS)
        self.reg('x30', STOP)
        self.execute(self.entry, STOP)
        code = self.reg_value('w0')
        return code, self.output

    def gates_unchanged(self):
        assert not any(k in GATES for k, v in self.writes), self.writes

    def snapshot(self):
        return bytes(self.files[FILE][0])


def main():
    m = Control()
    cases = []
    def ok(*args):
        code, out = m.run(*args)
        assert code == 0, (args, code, out)
        m.gates_unchanged()
        return out
    assert 'settings_saved=0' in ok('status')
    assert not m.files and not m.writes
    cases.append('read_only_status')
    assert 'restore_state=empty' in ok('restore') and not m.writes
    cases.append('empty_restore_does_not_set_debug_or_activate')
    ok('apply', 'blend', '0.75', 'curve', '25', '1.4', '0', '0', '2', '1', '0.2')
    saved = m.snapshot()
    assert len(saved) == 60 + 26 * 2
    assert struct.unpack_from('<f', saved, 40)[0] == 0.75
    assert m.files[FILE][1] == 0o600 and m.files[DIR][1] == 0o40700
    keys = [k for k, v in m.writes if k.startswith(PREFIX)]
    assert keys[0] == keys[-1] == PREFIX + 'seq'
    assert int(m.writes[-1][1]) % 2 == 0
    before = dict(m.properties)
    assert 'settings_match=1' in ok('status')
    cases.append('complete_apply_saves_actual_lut_and_metadata')
    m.properties = {PREFIX + 'enable': '0', PREFIX + 'hook_mode': '0', PREFIX + 'bypass': '1'}
    ok('restore')
    assert m.snapshot() == saved
    for key, value in before.items():
        if key != PREFIX + 'seq':
            assert m.properties[key] == value, (key, m.properties[key], value)
    assert [m.properties[k] for k in GATES] == ['0', '1', '0']
    assert m.writes[0][0] == DEBUG + 'smooth.weight'
    assert 'settings_match=1' in ok('status')
    cases.append('reboot_restores_identical_actual_lut_and_all_tuning_without_gates')
    ok('sampler', 'peak')
    assert m.properties[PREFIX + 'peak_weight'] == '0.75'
    assert all(m.properties[PREFIX + 'lut' + str(i)] == before[PREFIX + 'lut' + str(i)] for i in range(13))
    cases.append('sampler_change_preserves_lut_and_dormant_blend_weight')
    for value in ['0.31', '4', '-0.01', 'NaN', 'inf', '0.30000004', '1e2', '0.2;reboot']:
        prev = dict(m.properties), m.snapshot()
        code, out = m.run('debug', '0', '0', '3', '1', value)
        assert code == 2 and not m.writes and prev == (m.properties, m.snapshot()), (value, code, out)
        cases.append('reject_weight_' + value)
    ok('debug', '0', '0', '4', '0', '0.30')
    assert float(m.properties[DEBUG + 'smooth.weight']) <= struct.unpack('<f', bytes.fromhex('9a99993e'))[0]
    cases.append('native_default_weight_exact_float_ceiling')
    for debug_args in [('9', '0', '3', '1', '.3'), ('0', '16', '3', '1', '.3'), ('0', '0', '10', '1', '.3'), ('0', '0', '3', '2', '.3')]:
        code, _ = m.run('debug', *debug_args)
        assert code == 2 and not m.writes
        cases.append('reject_oversized_debug_range')
    saved = m.snapshot()
    for gate in GATES:
        m.properties[gate] = '1' if gate != PREFIX + 'bypass' else '0'
        code, _ = m.run('restore')
        assert code == 3 and not m.writes
        m.properties[gate] = '0' if gate != PREFIX + 'bypass' else '1'
        cases.append('boot_restore_stops_after_manual_' + gate.split('.')[-1])
    for altered in [saved[:45], saved + b'x', saved[:70] + bytes([saved[70] ^ 1]) + saved[71:]]:
        m.files[FILE][0] = bytearray(altered)
        code, _ = m.run('restore')
        assert code == 2 and not m.writes
        cases.append('damaged_snapshot_rejected_before_writes')
    # Valid checksum but a semantically invalid weight must still be refused.
    altered = bytearray(saved)
    struct.pack_into('<f', altered, 32, 0.31)
    struct.pack_into('<I', altered, 12, zlib.crc32(altered[16:]))
    m.files[FILE][0] = altered
    assert m.run('restore')[0] == 2 and not m.writes
    cases.append('valid_crc_does_not_bypass_weight_ceiling')
    m.files[FILE][0] = bytearray(saved)
    m.files[FILE][1] = 0o644
    assert m.run('restore')[0] == 2 and not m.writes
    m.files[FILE][1] = 0o600
    cases.append('restore_refuses_nonprivate_saved_file')
    m.files[FILE][2] = 2000
    assert m.run('restore')[0] == 2 and not m.writes
    m.files[FILE][2] = 0
    cases.append('restore_refuses_nonroot_saved_file_owner')
    for failure in ['write', 'fsync', 'lock']:
        m.fail_write = failure
        prev = dict(m.properties), m.snapshot()
        code, _ = m.run('debug', '1', '2', '3', '1', '0.2')
        assert code == 1 and not m.writes and prev == (m.properties, m.snapshot())
        cases.append('storage_' + failure + '_failure_leaves_live_and_saved_intact')
    m.fail_write = None
    m.fail_property = DEBUG + 'debugGaussian'
    prev = dict(m.properties), m.snapshot()
    assert m.run('debug', '1', '2', '3', '1', '0.2')[0] == 1
    assert prev == (m.properties, m.snapshot())
    cases.append('debug_property_failure_rolls_back_and_does_not_save')
    m.fail_property = PREFIX + 'lut0'
    assert m.run('lut-curve', '20', '1')[0] == 1
    assert m.snapshot() == saved and int(m.properties[PREFIX + 'seq']) % 2 == 1
    assert 'plan_valid=0' in ok('status')
    cases.append('failed_plan_stays_uncommitted_and_preserves_saved_file')
    ok('restore')
    cases.append('restore_recovers_odd_incomplete_plan')
    ok('lut-native')
    assert m.properties[PREFIX + 'sampler'] == '2' and m.properties[PREFIX + 'lut_mode'] == '0'
    cases.append('native_lut_reset_persists_without_changing_sampler')
    ok('debug-reset')
    assert [m.properties[DEBUG + k] for k in ['debugDilateX', 'debugDilateY', 'debugGaussian', 'smooth']] == ['1', '2', '3', '1']
    cases.append('debug_reset_persists_verified_defaults')
    m.properties.update({PREFIX + 'sampler': '3', PREFIX + 'peak_weight': '0.8', PREFIX + 'lut_mode': '2', PREFIX + 'lut_count': '3',
        PREFIX + 'lut0': '000003e81ffe', PREFIX + 'lut_threshold': '', PREFIX + 'lut_gamma': ''})
    ok('save')
    custom = m.snapshot()
    assert custom[60:] == struct.pack('<3H', 0, 1000, 8190)
    m.properties = {}
    ok('restore')
    assert m.snapshot() == custom and m.properties[PREFIX + 'lut0'] == '000003e81ffe'
    assert 'lut_curve_known=0' in ok('status')
    cases.append('unknown_custom_lut_table_roundtrips_exactly')
    ok('lut-curve', '255', '8')
    saved = m.snapshot()
    assert len(saved) == 572
    m.properties = {}
    ok('restore')
    assert m.snapshot() == saved and len(m.properties[PREFIX + 'lut12']) == 64
    cases.append('maximum_256_entry_lut_roundtrip')
    assert 'settings_match=1' in ok('status')
    m.properties[DEBUG + 'debugDilateX'] = '2'
    assert 'settings_match=0' in ok('status')
    cases.append('status_detects_unsaved_external_changes')
    m.root = False
    assert m.run('debug-reset')[0] == 1 and not m.writes
    m.root = True
    cases.append('missing_root_rejects_writes')
    ok('reset-all')
    assert m.properties[PREFIX + 'sampler'] == '0' and m.properties[PREFIX + 'lut_mode'] == '0'
    assert 'settings_match=1' in ok('status')
    cases.append('all_defaults_reset_and_save_without_activating')
    report = {'cases': len(cases), 'names': cases, 'library_sha256': hashlib.sha256(LIBRARY.read_bytes()).hexdigest(),
              'ldctl_sha256': hashlib.sha256((ROOT / 'sample_lut_build/libs/arm64-v8a/ldctl').read_bytes()).hexdigest(),
              'scope': 'Actual NDK-compiled ldctl/control/storage/codec in ARM64 Unicorn; OS/libc calls mocked, captured Android powf. No headset operations.'}
    (ROOT / 'sample_lut_evidence/settings_report.json').write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps(report, indent=2))


if __name__ == '__main__':
    main()
