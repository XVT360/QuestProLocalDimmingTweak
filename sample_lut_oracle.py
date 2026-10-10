"""Two-stage replacement contract, executed offline with original ARM64.

Only the sampling and LUT blocks may be redirected. The original runtime
executes all middle stages, its epilogue, and the output encoder. A JS worker
supplies the proposed replacement arithmetic; this does NOT execute the new
C++ source or a live injection bridge. No ADB, compilation or device access.
"""
from __future__ import annotations

import base64
import hashlib
import json
import random
import struct
import subprocess

from native_oracle import Oracle, ROOT, SO, B, RAW, HISTORY, SCRATCH, SP, LUT, b64, pack, regs
from unicorn import UC_HOOK_CODE

SAMPLE_ENTRY, SAMPLE_EXIT = 0x72e908, 0x72ec4c
LUT_ENTRY, LUT_EXIT = 0x72f930, 0x72fa98
RETURN = 0x730278
PAIR_BYTES = 0x1200


def decode(value):
    return base64.b64decode(value)


def set_state(oracle, state):
    oracle.seed(decode(state['buffers']), state['selector'])
    oracle.uc.mem_write(HISTORY, decode(state['history']))


def active_bytes(state):
    at = state['selector'] * PAIR_BYTES
    return decode(state['buffers'])[at:at + PAIR_BYTES]


def set_table(oracle, table):
    # Emulator storage only, for independent execution of native interpolation
    # with module table values. The device integration must NEVER swap this
    # native vector from a watcher thread.
    oracle.uc.mem_write(SCRATCH + 0x1000, struct.pack('<%dH' % len(table), *table))
    oracle.u64(0xe46bf0, SCRATCH + 0x1000)
    oracle.u64(0xe46bf8, SCRATCH + 0x1000 + 2 * len(table))


def original_frame(oracle, raw, stride, config, trace):
    oracle.prepare()
    # Exercise the real function prologue/epilogue with caller register values.
    for i in range(19, 30):
        oracle.reg('x' + str(i), 0x99100000 + i * 0x1010)
    for i in range(8, 16):
        oracle.reg('q' + str(i), (0x12340000 + i) * ((1 << 64) + 1))
    caller = {i: oracle.uc.reg_read(getattr(regs, 'UC_ARM64_REG_X' + str(i))) for i in range(19, 30)}
    caller_d = {i: oracle.uc.reg_read(getattr(regs, 'UC_ARM64_REG_D' + str(i))) for i in range(8, 16)}
    oracle.config(**config)
    oracle.uc.mem_write(RAW, raw)
    oracle.i32(0xe435d0, stride)
    oracle.u64(0xe435d8, RAW)
    oracle.i32(0xe46c68, 0) # excludes the runtime's optional mode-4 dump path
    oracle.uc.mem_write(SCRATCH + 3, bytes([int(trace)]))
    trace_calls = []
    def log_shim(uc, address, size, user):
        trace_calls.append(uc.reg_read(regs.UC_ARM64_REG_LR))
        oracle.reg('pc', uc.reg_read(regs.UC_ARM64_REG_LR))
    hook = oracle.uc.hook_add(UC_HOOK_CODE, log_shim, begin=0x3fa14c, end=0x3fa14c)
    try:
        oracle.execute(0x72e8a4, RETURN)
    finally:
        oracle.uc.hook_del(hook)
    assert oracle.uc.reg_read(regs.UC_ARM64_REG_SP) == SP
    for i, expected in caller.items():
        assert oracle.uc.reg_read(getattr(regs, 'UC_ARM64_REG_X' + str(i))) == expected, ('callee x', i)
    for i, expected in caller_d.items():
        assert oracle.uc.reg_read(getattr(regs, 'UC_ARM64_REG_D' + str(i))) == expected, ('callee d', i)
    if trace:
        assert 0x7302ec in trace_calls and 0x730324 in trace_calls
    return oracle.state(), len(trace_calls)


def generate():
    pinned = '0ffc0216e3904307d8504e4080c4481db2d29030d4bdccfcef462e3809846b11'
    assert hashlib.sha256(SO.read_bytes()).hexdigest() == pinned
    oracle_lut = Oracle()
    def curve(threshold, gamma):
        return list(struct.unpack('<%dH' % (threshold + 1), oracle_lut.generate_lut(threshold, gamma)))
    native_lut = LUT[:]
    extended, curved, alternate = curve(255, 1), curve(80, 2), curve(40, 0.5)
    sequence = [
        ('default', {}, {}, native_lut),
        ('explicit_native_replay', dict(enabled=True, sampler='mean', lut=native_lut), {}, native_lut),
        ('peak_only', dict(enabled=True, sampler='peak'), {}, native_lut),
        ('peak_and_extended_lut', dict(enabled=True, sampler='peak', lut=extended), {}, native_lut),
        ('blend_and_curve', dict(enabled=True, sampler='blend', peakWeight=0.25, lut=curved), {}, native_lut),
        ('lut_only', dict(enabled=True, lut=alternate), {}, native_lut),
        ('native_dilation_bypass', dict(enabled=True, sampler='peak', lut=extended), dict(x=0, y=0), native_lut),
        ('native_gaussian_even', dict(enabled=True, sampler='mean', lut=curved), dict(gaussian=2), native_lut),
        ('independent_sampler_disable', dict(enabled=True, sampler='native', lut=extended), {}, native_lut),
        ('independent_lut_disable', dict(enabled=True, sampler='blend', peakWeight=0.5), {}, native_lut),
        ('master_rollback', dict(enabled=False, sampler='peak', lut=extended), {}, native_lut),
        ('follow_current_native_lut', {}, {}, alternate),
        ('replay_changed_native_lut', dict(enabled=True, sampler='mean', lut=alternate), {}, alternate),
    ]
    rng = random.Random(202610071)
    records = []
    worker = subprocess.Popen(['node', str(ROOT / 'sample_lut_reference.js')], cwd=ROOT,
                              stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                              text=True, encoding='utf-8')
    try:
        for selector in [0, 1]:
            for trace in [False, True]:
                actual = Oracle()
                baseline = Oracle()
                # Nonzero alternate borders and history expose accidental clears
                # and make rollback distinguishable from a fresh process.
                initial = dict(selector=selector,
                               buffers=b64(pack([rng.random() * 20 for _ in range(2304)])),
                               history=b64(pack([rng.random() * 10 for _ in range(1152)])))
                set_state(actual, initial)
                for index, (name, plan, original, table) in enumerate(sequence):
                    stride = [1440, 1472, 1536][index % 3]
                    raw = bytearray(stride * 192)
                    if index == 1:
                        for p in range(0, len(raw), 4):
                            raw[p:p+4] = bytes([255, 255, 255, 7])
                    elif index != 10: # rollback frame deliberately black
                        for _ in range(500):
                            eye = rng.randrange(2)
                            p = rng.randrange(192) * stride + eye * 720 + rng.randrange(180) * 4
                            raw[p:p+4] = rng.randbytes(4)
                        raw[12 * 6 * stride + 7 * 40:12 * 6 * stride + 7 * 40 + 4] = b'\xff\xff\xff\x00'
                    before = actual.state()
                    request = dict(before=before, raw=b64(raw), stride=stride, plan=plan,
                                   original=original, nativeLut=table)
                    worker.stdin.write(json.dumps(request, separators=(',', ':')) + '\n')
                    worker.stdin.flush()
                    response = worker.stdout.readline()
                    assert response, worker.stderr.read()
                    expected = json.loads(response)
                    assert 'error' not in expected, expected
                    sample_replace = plan.get('enabled', False) and plan.get('sampler', 'native') != 'native'
                    lut_replace = plan.get('enabled', False) and plan.get('lut') is not None
                    visits = dict(sample_entry=0, sample_exit=0, lut_entry=0, sample_writes=0, lut_writes=0)
                    hooks = []
                    def sampling_entry(uc, address, size, user):
                        visits['sample_entry'] += 1
                        assert uc.reg_read(regs.UC_ARM64_REG_X19) == RAW
                        if sample_replace:
                            uc.mem_write(B + 0x60 + before['selector'] * PAIR_BYTES,
                                         active_bytes(expected['sampled']))
                            # These are established by the skipped native sampler
                            # and read later. Restoring only entry registers fails.
                            actual.reg('x20', 0xe45000)
                            actual.reg('x27', B)
                            actual.reg('pc', SAMPLE_EXIT)
                    def sampling_exit(uc, address, size, user):
                        visits['sample_exit'] += 1
                        assert actual.state() == expected['sampled'], name + ' sample state'
                        assert uc.reg_read(regs.UC_ARM64_REG_X20) == 0xe45000
                        assert uc.reg_read(regs.UC_ARM64_REG_X27) == B
                    def lut_entry(uc, address, size, user):
                        visits['lut_entry'] += 1
                        state = actual.state()
                        assert state == expected['beforeLut'], name + ' native middle stages'
                        # Independently check proposed LUT arithmetic by executing
                        # ORIGINAL instructions against the same arbitrary table.
                        set_state(oracle_lut, state)
                        set_table(oracle_lut, plan['lut'] if lut_replace else table)
                        oracle_lut.lut()
                        assert oracle_lut.state() == expected['after'], name + ' LUT arithmetic'
                        if lut_replace:
                            uc.mem_write(B + 0x60 + state['selector'] * PAIR_BYTES,
                                         active_bytes(expected['after']))
                            actual.reg('pc', LUT_EXIT)
                    def count_store(uc, address, size, user):
                        visits['sample_writes' if address in [0x72ea90, 0x72ec2c] else 'lut_writes'] += 1
                    for at, callback in [(SAMPLE_ENTRY, sampling_entry), (SAMPLE_EXIT, sampling_exit), (LUT_ENTRY, lut_entry),
                                         (0x72ea90, count_store), (0x72ec2c, count_store),
                                         (0x72f99c, count_store), (0x72fa4c, count_store)]:
                        hooks.append(actual.uc.hook_add(UC_HOOK_CODE, callback, begin=at, end=at))
                    set_table(actual, table)
                    native_header = bytes(actual.uc.mem_read(0xe46bf0, 16))
                    native_table = bytes(actual.uc.mem_read(SCRATCH + 0x1000, len(table) * 2))
                    native_text = bytes(actual.uc.mem_read(0x72e8a4, 0x73027c - 0x72e8a4))
                    try:
                        state, trace_calls = original_frame(actual, bytes(raw), stride, original, trace)
                    finally:
                        for hook in hooks:
                            actual.uc.hook_del(hook)
                    assert state == expected['after'], name + ' complete function state'
                    assert visits == dict(sample_entry=1, sample_exit=1, lut_entry=1,
                                          sample_writes=0 if sample_replace else 1152,
                                          lut_writes=0 if lut_replace else 1152), visits
                    assert bytes(actual.uc.mem_read(0xe46bf0, 16)) == native_header
                    assert bytes(actual.uc.mem_read(SCRATCH + 0x1000, len(table) * 2)) == native_table
                    assert bytes(actual.uc.mem_read(0x72e8a4, len(native_text))) == native_text
                    neutral = (not plan.get('enabled', False) or
                               (plan.get('sampler', 'native') in ['mean', 'native'] and
                                plan.get('lut', table) == table))
                    if neutral:
                        set_state(baseline, before)
                        set_table(baseline, table)
                        base_after, _ = original_frame(baseline, bytes(raw), stride, original, trace)
                        assert state == base_after, name + ' unmodified runtime parity'
                    # Use the same unchanged native encoder; this also covers
                    # endianness, permutation, uint16 codes and its trailer.
                    # The separate native_mapping harness intentionally covers
                    # its trace-disabled path; frame tracing was tested above.
                    actual.uc.mem_write(SCRATCH + 3, b'\x00')
                    baseline.uc.mem_write(SCRATCH + 3, b'\x00')
                    payloads = actual.native_mapping(0)
                    assert actual.state() == state
                    for eye in [0, 1]:
                        assert payloads[eye]['eye'] == eye and len(decode(payloads[eye]['bytes'])) == 1153
                    if neutral:
                        assert payloads == baseline.native_mapping(0)
                    records.append(dict(name=name, initial_selector=selector, trace=trace,
                                        trace_calls=trace_calls, native_baseline_compared=neutral,
                                        visits=visits, payload_sha256=[hashlib.sha256(decode(p['bytes'])).hexdigest() for p in payloads]))
                    # Mapping's prepare() changes registers only; buffers/history
                    # carry into the next frame unchanged, including stale borders.
    finally:
        worker.stdin.close()
        worker.stdout.close()
        try:
            worker.wait(timeout=5)
        except subprocess.TimeoutExpired:
            worker.kill()
            worker.wait()
    assert worker.returncode == 0, worker.stderr.read()
    report = dict(runtime_sha256=pinned, cases=len(records),
                  neutral_cases=sum(r['native_baseline_compared'] for r in records),
                  boundary_contract=dict(sample_entry=hex(SAMPLE_ENTRY), sample_resume=hex(SAMPLE_EXIT),
                                         sample_live_out={'x20': 'image_base+0xe45000', 'x27': 'image_base+0xe43588'},
                                         lut_entry=hex(LUT_ENTRY), lut_resume=hex(LUT_EXIT)),
                  scope='Original middle stages, native LUT oracle, function epilogue and output encoder. Replacement arithmetic supplied by JS. Trace logger shimmed. No C++ build or bridge execution.',
                  source_sha256={name: hashlib.sha256((ROOT / name).read_bytes()).hexdigest() for name in
                                 ['sample_lut_reference.js', 'sample_lut_oracle.py', 'native_reference.js',
                                  'zygisk_local_dimming/staged/sample_lut_core.cpp',
                                  'zygisk_local_dimming/staged/sample_lut_core.h']},
                  records=records)
    output = ROOT / 'sample_lut_evidence'
    output.mkdir(exist_ok=True)
    (output / 'contract_report.json').write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
    print(json.dumps({k: v for k, v in report.items() if k not in ['records', 'source_sha256']}, indent=2))


if __name__ == '__main__':
    generate()
