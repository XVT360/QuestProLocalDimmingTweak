const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');
const {spawnSync} = require('node:child_process');
const assert = require('node:assert/strict');

const temp = fs.mkdtempSync(path.join(os.tmpdir(), 'quest-ld-helper-test-'));
const moduleDir = path.join(temp, 'module');
const bash = process.env.QUEST_LD_BASH || (process.platform === 'win32' ? 'C:/Program Files/Git/bin/bash.exe' : 'bash');
const unix = p => p.replaceAll('\\', '/').replace(/^([A-Z]):/i, (_, drive) => '/' + drive.toLowerCase());
fs.mkdirSync(path.join(moduleDir, 'bin'), {recursive: true});
fs.mkdirSync(path.join(moduleDir, 'log'));
fs.writeFileSync(path.join(moduleDir, 'module.prop'), 'version=0.5.0\n');
fs.copyFileSync('zygisk_local_dimming/sample_lut/package/controller.sh', path.join(moduleDir, 'controller.sh'));
fs.writeFileSync(path.join(moduleDir, 'bin', 'ldctl'),
    '#!/bin/bash\nif [ "$1" = status ]; then echo plan_valid=${MOCK_VALID:-1}; else echo "ldctl:$*" >> "$MOCK_TRACE"; fi\n' +
    'case "$1" in restore) exit "${MOCK_RESTORE:-0}" ;; debug-reset) exit "${MOCK_DEBUG_RESET:-0}" ;; esac\n');
const trace = path.join(temp, 'trace');
const definitions = [
    'id() { echo 0; }',
    'pidof() { echo "${MOCK_PID-18545}"; }',
    'setprop() { echo "setprop:$*" >> "$MOCK_TRACE"; }',
    'sleep() { echo "sleep:$*" >> "$MOCK_TRACE"; }',
    'kill() { echo "kill:$*" >> "$MOCK_TRACE"; }',
    '. "$0" "$1"',
].join('\n');
function run(action, extra = {}) {
    fs.writeFileSync(trace, '');
    const result = spawnSync(bash, ['-c', definitions, unix(path.join(moduleDir, 'controller.sh')), action], {
        env: {...process.env, MOCK_TRACE: unix(trace), ...extra}, encoding: 'utf8', timeout: 5000,
    });
    if (result.error) throw result.error;
    return {...result, calls: fs.readFileSync(trace, 'utf8')};
}
fs.writeFileSync(path.join(moduleDir, 'log/zygisk_trace.log'),
    'status pid=18545 ready=1 enable=0 rejected=0\n');
const status = run('status');
assert.equal(status.status, 0);
assert.match(status.stdout, /module_disabled=0/);
assert.match(status.stdout, /runtime_pid=18545/);
assert.equal(status.calls, '');
const enabled = run('enable');
assert.equal(enabled.status, 0);
assert.match(enabled.calls, /bypass 0[\s\S]*enable 1/);
const stale = run('enable', {MOCK_PID: '19999'});
assert.notEqual(stale.status, 0);
assert.equal(stale.calls, '');
assert.match(stale.stdout, /hook_not_ready/);
const invalid = run('enable', {MOCK_VALID: '0'});
assert.notEqual(invalid.status, 0);
assert.equal(invalid.calls, '');
for (const value of ['', '12 14', '1', 'nonnumeric']) {
    const bad = run('prepare', {MOCK_PID: value});
    assert.notEqual(bad.status, 0);
    assert.equal(bad.calls, '');
}
const prepare = run('prepare');
assert.equal(prepare.status, 0);
assert.match(prepare.calls, /ldctl:disable[\s\S]*hook_mode 0[\s\S]*sleep:1[\s\S]*hook_mode 1[\s\S]*kill:-TERM 18545/);
assert.doesNotMatch(prepare.calls, /enable 1|bypass 0/);
const recover = run('recover');
assert.equal(recover.status, 0);
assert.match(recover.calls, /hook_mode 0[\s\S]*kill:-TERM 18545/);
assert.doesNotMatch(recover.calls, /hook_mode 1|enable 1|bypass 0/);
const failedRestore = run('prepare', {MOCK_RESTORE: '2'});
assert.notEqual(failedRestore.status, 0);
assert.match(failedRestore.stdout, /settings_restore_failed/);
assert.doesNotMatch(failedRestore.calls, /kill:|hook_mode 1/);
const rollback = run('rollback');
assert.equal(rollback.status, 0);
assert.match(rollback.calls, /ldctl:disable[\s\S]*hook_mode 0[\s\S]*ldctl:debug-reset/);
assert.doesNotMatch(rollback.calls, /enable 1|bypass 0|kill:/);
const repair = run('rollback', {MOCK_DEBUG_RESET: '1'});
assert.equal(repair.status, 0);
assert.match(repair.calls, /ldctl:debug-reset[\s\S]*ldctl:reset-all/);
fs.writeFileSync(path.join(moduleDir, 'disable'), '');
assert.notEqual(run('prepare').status, 0);
assert.equal(run('disable').status, 0);
fs.unlinkSync(path.join(moduleDir, 'disable'));
fs.writeFileSync(path.join(moduleDir, 'update'), '');
const pending = run('prepare');
assert.notEqual(pending.status, 0);
assert.equal(pending.calls, '');
const restorePending = run('restore');
assert.notEqual(restorePending.status, 0);
assert.equal(restorePending.calls, '');
fs.unlinkSync(path.join(moduleDir, 'update'));
const restored = run('restore');
assert.equal(restored.status, 0);
assert.match(restored.calls, /ldctl:restore/);
assert.doesNotMatch(restored.calls, /setprop:|kill:/);
const saved = run('save');
assert.equal(saved.status, 0);
assert.match(saved.calls, /ldctl:save/);
assert.doesNotMatch(saved.calls, /setprop:|kill:/);
console.log('Runtime helper: 19 scenarios passed; no real process killed');
