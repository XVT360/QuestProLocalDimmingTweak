"""Execute the generated bridge inside the original function, OFFLINE only.

The two entry words are patched in Unicorn memory, never in a file or device.
Replacement arithmetic still comes from the JS model; actual C++ and loader
remain subject to the user's hold before building a new package.
"""
import hashlib
import json
import random
import struct
import subprocess

from native_oracle import Oracle, ROOT, SO, B, RAW, SCRATCH, b64, pack, regs
from sample_lut_oracle import (set_state, set_table, original_frame, active_bytes,
                               SAMPLE_ENTRY, SAMPLE_EXIT, LUT_ENTRY, LUT_EXIT, LUT)
from stage_bridge_oracle import template, instantiate_at, branch
from unicorn import UC_HOOK_CODE

BRIDGES = 0x5400000
CALLBACK = BRIDGES + 0x4000


def generate():
    words, slots = template()
    rng = random.Random(202610073)
    records = []
    worker = subprocess.Popen(['node', str(ROOT/'sample_lut_reference.js')], cwd=ROOT,
                              stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                              text=True, encoding='utf-8')
    linear255 = list(struct.unpack('<256H', Oracle().generate_lut(255, 1)))
    plans = [{}, dict(enabled=True, sampler='mean', lut=LUT),
             dict(enabled=True, sampler='peak', lut=linear255),
             dict(enabled=False, sampler='peak', lut=linear255)]
    try:
        for selector in [0, 1]:
            for trace in [False, True]:
                actual, baseline = Oracle(), Oracle()
                actual.uc.mem_map(BRIDGES, 0x10000)
                for stage, entry, exit_at in [(0, SAMPLE_ENTRY, SAMPLE_EXIT), (1, LUT_ENTRY, LUT_EXIT)]:
                    addr = BRIDGES + stage * 0x1000
                    actual.uc.mem_write(addr, instantiate_at(words, slots, stage, 0, entry, addr, CALLBACK, exit_at))
                    actual.uc.mem_write(entry, struct.pack('<I', branch(entry, addr)))
                initial = dict(selector=selector,
                               buffers=b64(pack([rng.random()*20 for _ in range(2304)])),
                               history=b64(pack([rng.random()*10 for _ in range(1152)])))
                set_state(actual, initial)
                for index, plan in enumerate(plans):
                    before = actual.state()
                    raw = bytearray(1536*192)
                    if index != 3:
                        for _ in range(500):
                            p = rng.randrange(192)*1536 + rng.randrange(360)*4
                            raw[p:p+4] = rng.randbytes(4)
                    worker.stdin.write(json.dumps(dict(before=before, raw=b64(raw), stride=1536,
                                                       plan=plan, original={}))+'\n')
                    worker.stdin.flush()
                    expected = json.loads(worker.stdout.readline())
                    assert 'error' not in expected, expected
                    callbacks = []
                    def dispatch(uc, address, size, user):
                        context = uc.reg_read(regs.UC_ARM64_REG_X0)
                        stage = uc.reg_read(regs.UC_ARM64_REG_X1)
                        assert uc.reg_read(regs.UC_ARM64_REG_X2) == 0
                        callbacks.append(stage)
                        route = 0
                        if stage == 0:
                            assert struct.unpack('<Q', uc.mem_read(context+19*8, 8))[0] == RAW
                            if plan.get('enabled') and plan.get('sampler', 'native') != 'native':
                                uc.mem_write(B+0x60+before['selector']*0x1200, active_bytes(expected['sampled']))
                                uc.mem_write(context+20*8, struct.pack('<Q', 0xe45000))
                                uc.mem_write(context+27*8, struct.pack('<Q', B))
                                route = 1
                        else:
                            assert stage == 1 and actual.state() == expected['beforeLut']
                            if plan.get('enabled') and plan.get('lut') is not None:
                                uc.mem_write(B+0x60+expected['after']['selector']*0x1200, active_bytes(expected['after']))
                                route = 1
                        resume = uc.reg_read(regs.UC_ARM64_REG_LR)
                        # Exercise preservation while executing the actual bridge
                        # and actual native continuation, not a synthetic caller.
                        for i in range(31):
                            uc.reg_write(getattr(regs, f'UC_ARM64_REG_X{i}'), 0xbaad0000+i)
                        for i in range(32):
                            uc.reg_write(getattr(regs, f'UC_ARM64_REG_Q{i}'), (1 << 128)-1)
                        for key in ['NZCV', 'FPCR', 'FPSR']:
                            uc.reg_write(getattr(regs, 'UC_ARM64_REG_'+key), 0)
                        uc.reg_write(regs.UC_ARM64_REG_X0, route)
                        uc.reg_write(regs.UC_ARM64_REG_PC, resume)
                    hook = actual.uc.hook_add(UC_HOOK_CODE, dispatch, begin=CALLBACK, end=CALLBACK)
                    set_table(actual, LUT)
                    try:
                        state, _ = original_frame(actual, bytes(raw), 1536, {}, trace)
                    finally:
                        actual.uc.hook_del(hook)
                    assert state == expected['after'] and callbacks == [0, 1]
                    actual.uc.mem_write(SCRATCH+3, b'\x00')
                    payloads = actual.native_mapping(0)
                    neutral = index != 2
                    if neutral:
                        set_state(baseline, before)
                        set_table(baseline, LUT)
                        unchanged, _ = original_frame(baseline, bytes(raw), 1536, {}, trace)
                        assert unchanged == state
                        baseline.uc.mem_write(SCRATCH+3, b'\x00')
                        assert payloads == baseline.native_mapping(0)
                    records.append(dict(initial_selector=selector, trace=trace, plan_index=index,
                                        baseline_compared=neutral, result='pass'))
    finally:
        worker.stdin.close()
        worker.stdout.close()
        try:
            worker.wait(timeout=5)
        except subprocess.TimeoutExpired:
            worker.kill()
            worker.wait()
    assert worker.returncode == 0, worker.stderr.read()
    report = dict(cases=len(records), native_comparisons=sum(r['baseline_compared'] for r in records),
                  runtime_sha256=hashlib.sha256(SO.read_bytes()).hexdigest(),
                  template_sha256=hashlib.sha256((ROOT/'zygisk_local_dimming/staged/stage_bridge_words.h').read_bytes()).hexdigest(),
                  scope='Generated direct-B preserving bridges executed inside original ARM64 function in emulator. Callback arithmetic supplied by JS; callback clobbers GPR/SIMD/flags. No C++ compilation, live patching, installer or headset tests.',
                  records=records)
    (ROOT/'sample_lut_evidence/bridge_integration_report.json').write_text(json.dumps(report, indent=2)+'\n', encoding='utf-8')
    print(json.dumps({k: v for k, v in report.items() if k != 'records'}, indent=2))


if __name__ == '__main__':
    generate()
