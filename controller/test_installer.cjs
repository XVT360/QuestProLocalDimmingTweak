'use strict';
// Exercise actual installer shell with simulated Android/Magisk boundaries.
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');
const {spawnSync} = require('node:child_process');
const assert = require('node:assert/strict');
const bash = process.env.QUEST_LD_BASH || (process.platform === 'win32' ? 'C:/Program Files/Git/bin/bash.exe' : 'bash');
const unix = p => p.replaceAll('\\', '/').replace(/^([A-Z]):/i, (_, d) => '/' + d.toLowerCase());
const hash = '0ffc0216e3904307d8504e4080c4481db2d29030d4bdccfcef462e3809846b11';
const hashV204 = '840cb7661532ff53a40387cfb17a5c89ccdb114bc9231149b84e5df0e826ef1a';
const temp = fs.mkdtempSync(path.join(os.tmpdir(), 'quest-ld-install-'));
const script = path.join(temp, 'customize.sh');
fs.copyFileSync('zygisk_local_dimming/sample_lut/package/customize.sh', script);
const moduleDir = path.join(temp, 'module');
fs.mkdirSync(path.join(moduleDir, 'bin'), {recursive: true});
fs.writeFileSync(path.join(moduleDir, 'QuestProLDControl.apk'), 'mock APK');
fs.writeFileSync(path.join(moduleDir, 'bin/ldctl'), '#!/bin/bash\necho "ldctl:$*" >> "$TRACE"\n');
const trace = path.join(temp, 'trace');
const shell = `
ui_print() { echo "$*"; }
abort() { echo "ABORT:$*"; exit 23; }
getprop() {
  case "$1" in ro.product.device) echo "$DEVICE" ;; ro.product.cpu.abilist) echo "$ABI" ;; esac
}
pm() {
  echo "pm:$*" >> "$TRACE"
  if [ "$1" = path ]; then
    [ "$2" = com.oculus.systemdriver ] || exit 91
    [ "$MISSING" = 1 ] || printf 'package:/system/app/Driver/base.apk\\npackage:/system/app/Driver/split.apk\\n'
  else
    return "$APK_RESULT"
  fi
}
unzip() { echo "unzip:$*" >> "$TRACE"; [ "$3" = lib/arm64-v8a/libvrruntimeservice.so ] || exit 92; echo "mock-library"; }
sha256sum() { while IFS= read -r line; do :; done; echo "$HASH  -"; }
mkdir() { echo "mkdir:$*" >> "$TRACE"; }
cp() { echo "cp:$*" >> "$TRACE"; return "$COPY_RESULT"; }
chmod() { echo "chmod:$*" >> "$TRACE"; }
set_perm_recursive() { :; }
set_perm() { :; }
setprop() { echo forbidden-property-write >> "$TRACE"; exit 93; }
kill() { echo forbidden-restart >> "$TRACE"; exit 94; }
. "$0"
`;
function run(extra = {}) {
  fs.writeFileSync(trace, '');
  const result = spawnSync(bash, ['-c', shell, unix(script)], {
    env: {...process.env, MODPATH: unix(moduleDir), TRACE: unix(trace), DEVICE:'seacliff',
      ABI:'arm64-v8a,armeabi-v7a', HASH:hash, APK_RESULT:'0', COPY_RESULT:'0', MISSING:'0', ...extra},
    encoding:'utf8', timeout:10000,
  });
  if (result.error) throw result.error;
  const calls = fs.readFileSync(trace,'utf8');
  assert.doesNotMatch(calls, /forbidden-/);
  return {...result, calls};
}
const fresh = run();
assert.equal(fresh.status,0,fresh.stderr);
assert.match(fresh.stdout,/Graphical controller installed/);
assert.match(fresh.calls,/pm:path com.oculus.systemdriver/);
assert.match(fresh.calls,/ldctl:save/);
// Every reviewed Runtime image is accepted; an unlisted or near-miss hash is not.
const second = run({HASH:hashV204});
assert.equal(second.status,0,second.stderr);
assert.match(second.calls,/pm:path com.oculus.systemdriver/);
assert.match(second.calls,/ldctl:save/);
for (const options of [{DEVICE:'other-headset'}, {ABI:'armeabi-v7a'}, {HASH:'unsupported'},
    {HASH:hashV204.slice(0,-1)+'b'}, {MISSING:'1'}]) {
  const denied = run(options);
  assert.equal(denied.status,23);
  assert.doesNotMatch(denied.calls,/ldctl:|pm:install/);
}
const fallback = run({APK_RESULT:'1'});
assert.equal(fallback.status,0);
assert.match(fallback.stdout,/Controller APK copied to Download/);
const copyFailed = run({APK_RESULT:'1', COPY_RESULT:'1'});
assert.equal(copyFailed.status,0);
assert.match(copyFailed.stdout,/from the module ZIP manually/);
assert.doesNotMatch(copyFailed.stdout,/Controller APK copied to Download/);
console.log('Installer: 9 scenarios passed; Android, package extraction and filesystem operations mocked');
