// Exercise the boot worker with mocked root/property commands and no real waits.
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');
const {spawnSync} = require('node:child_process');
const assert = require('node:assert/strict');
const bash = process.env.QUEST_LD_BASH || (process.platform === 'win32' ? 'C:/Program Files/Git/bin/bash.exe' : 'bash');
const unix = p => p.replaceAll('\\', '/').replace(/^([A-Z]):/i, (_, drive) => '/' + drive.toLowerCase());
const source = fs.readFileSync('zygisk_local_dimming/sample_lut/package/service.sh', 'utf8');
// Remove only the background operator for deterministic host testing; preserve
// every worker statement. Production returns immediately without a wait.
const synchronous = source.replace(') </dev/null >/dev/null 2>&1 &', ') </dev/null');
assert.notEqual(source, synchronous);
function run({rootAfter = 0, bootAfter = 0, failures = 0, result = 0, disabled = false}) {
    const temp = fs.mkdtempSync(path.join(os.tmpdir(), 'quest-ld-boot-'));
    const service = path.join(temp, 'service.sh');
    fs.writeFileSync(service, synchronous);
    const trace = path.join(temp, 'trace'), ticks = path.join(temp, 'ticks'), calls = path.join(temp, 'calls');
    fs.writeFileSync(trace, ''); fs.writeFileSync(ticks, '0\n'); fs.writeFileSync(calls, '0\n');
    if (disabled) fs.writeFileSync(path.join(temp, 'disable'), '');
    // Use shell builtins for shared counters. Launching cat repeatedly in Git
    // Bash on Windows is slow and is unrelated to the Android worker behavior.
    const definitions = `
getprop() { IFS= read -r t < "$MOCK_TICKS"; [ "$t" -ge "$BOOT_AFTER" ] && echo 1 || echo 0; }
id() { IFS= read -r t < "$MOCK_TICKS"; [ "$t" -ge "$ROOT_AFTER" ] && echo 0 || echo 2000; }
sleep() { IFS= read -r t < "$MOCK_TICKS"; echo $((t + 1)) > "$MOCK_TICKS"; }
sh() {
  echo "restore:$*" >> "$MOCK_TRACE"
  IFS= read -r n < "$MOCK_CALLS"; n=$((n + 1)); echo "$n" > "$MOCK_CALLS"
  [ "$n" -le "$FAILURES" ] && return 1
  echo "restore_state=result_$RESTORE_RESULT"
  return "$RESTORE_RESULT"
}
setprop() { echo "unexpected-setprop:$*" >> "$MOCK_TRACE"; return 99; }
kill() { echo "unexpected-kill:$*" >> "$MOCK_TRACE"; return 99; }
. "$0"
`;
    const res = spawnSync(bash, ['-c', definitions, unix(service)], {
        encoding: 'utf8', timeout: 10000,
        env: {...process.env, MOCK_TRACE: unix(trace), MOCK_TICKS: unix(ticks), MOCK_CALLS: unix(calls),
            ROOT_AFTER: String(rootAfter), BOOT_AFTER: String(bootAfter), FAILURES: String(failures), RESTORE_RESULT: String(result)},
    });
    if (res.error) throw res.error;
    assert.equal(res.status, 0, res.stderr);
    assert.doesNotMatch(fs.readFileSync(trace, 'utf8'), /unexpected-|enable|hook_mode|kill:/);
    return {ticks: +fs.readFileSync(ticks), calls: +fs.readFileSync(calls), log: fs.readFileSync(path.join(temp, 'log/boot.log'), 'utf8')};
}
assert.equal(run({}).calls, 1);
const root = run({rootAfter: 24});
assert.equal(root.ticks, 24); assert.equal(root.calls, 1); // 24*5 = 120 seconds simulated
const boot = run({bootAfter: 6}); assert.equal(boot.ticks, 6); assert.equal(boot.calls, 1);
const transient = run({failures: 3}); assert.equal(transient.calls, 4); assert.equal(transient.ticks, 3);
assert.equal(run({result: 2}).calls, 1);
assert.equal(run({result: 3}).calls, 1);
assert.equal(run({disabled: true}).calls, 0);
const timeout = run({rootAfter: 99}); assert.equal(timeout.calls, 0); assert.match(timeout.log, /restore_state=timed_out/);
console.log('Boot restore: 8 scenarios passed; simulated 2 minute root gap; no headset operations');
