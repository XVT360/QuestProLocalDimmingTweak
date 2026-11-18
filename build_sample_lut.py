"""Build/package the two-stage module; never connect to a headset."""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import zipfile

ROOT = Path(__file__).resolve().parent
VERSION = '0.5.0'
SOURCE = ROOT / 'zygisk_local_dimming'
NATIVE = SOURCE / 'sample_lut'
SO = Path(os.environ['QUEST_LD_RUNTIME_IMAGE']).resolve() if os.environ.get('QUEST_LD_RUNTIME_IMAGE') else None
NDK = Path(os.environ.get('ANDROID_NDK_HOME', ROOT / '.build-deps/android-ndk-r27d')).resolve()
BUILD = ROOT / 'sample_lut_build'

# Every Runtime image this module is reviewed against. One generated header per
# image pins its identity (SHA256, ELF build-id, hook-site fingerprints); the
# address fields are reviewed evidence from that same image. runtime_profile.cpp
# compiles them into a table and selects a profile from the loaded library's
# build-id. An image outside this list is still refused, never patched.
PROFILES = [
    dict(key='v207', vros_build=207, header='pinned_image.h',
         symbols=('kBuildId', 'kSampleFingerprint', 'kLutFingerprint', 'kPinnedSha256'),
         sha='0ffc0216e3904307d8504e4080c4481db2d29030d4bdccfcef462e3809846b11',
         sample=0x72e908, lut=0x72f930),
    dict(key='v204', vros_build=204, header='pinned_image_v204.h',
         symbols=('kBuildIdV204', 'kSampleFingerprintV204', 'kLutFingerprintV204', 'kPinnedSha256V204'),
         sha='840cb7661532ff53a40387cfb17a5c89ccdb114bc9231149b84e5df0e826ef1a',
         sample=0x7133cc, lut=0x7143f4),
]


def generate_identity(image=None):
    selected = None
    if image is not None:
        digest = hashlib.sha256(image.read_bytes()).hexdigest()
        selected = next((p for p in PROFILES if p['sha'] == digest), None)
        if selected is None:
            raise RuntimeError('Unsupported runtime image; SHA256 must match a supported firmware')
    for profile in PROFILES:
        header_path = NATIVE / profile['header']
        if profile is not selected:
            header = header_path.read_text(encoding='ascii')
            build_id, sample_fp, lut_fp, pinned = profile['symbols']
            if profile['sha'] not in header:
                raise RuntimeError(f'Pinned header {profile["header"]} does not pin its reviewed SHA256')
            for symbol in (build_id, sample_fp, lut_fp, pinned):
                if symbol not in header:
                    raise RuntimeError(f'Pinned header {profile["header"]} is missing {symbol}')
            continue
        from elftools.elf.elffile import ELFFile
        with image.open('rb') as file:
            elf = ELFFile(file)
            notes = elf.get_section_by_name('.note.gnu.build-id')
            build_id = bytes.fromhex(next(n['n_desc'] for n in notes.iter_notes() if n['n_type'] == 'NT_GNU_BUILD_ID'))
            segments = list(elf.iter_segments())
            def read_va(va, size):
                for p in segments:
                    if p['p_type'] == 'PT_LOAD' and p['p_vaddr'] <= va and va + size <= p['p_vaddr'] + p['p_filesz']:
                        file.seek(p['p_offset'] + va - p['p_vaddr'])
                        return file.read(size)
                raise ValueError(hex(va))
            build_symbol, sample_symbol, lut_symbol, pinned_symbol = profile['symbols']
            lines = ['// Generated from the pinned original image by build_sample_lut.py.',
                     '#pragma once', '#include <cstdint>', 'namespace quest_ld {',
                     f'constexpr uint8_t {build_symbol}[] = {{' + ','.join(str(b) for b in build_id) + '};']
            lines.append(f'constexpr uint8_t {sample_symbol}[] = {{' + ','.join(str(b) for b in read_va(profile['sample'], 64)) + '};')
            lines.append(f'constexpr uint8_t {lut_symbol}[] = {{' + ','.join(str(b) for b in read_va(profile['lut'], 64)) + '};')
            lines += [f'constexpr const char *{pinned_symbol} = "{profile["sha"]}";', '}']
        with header_path.open('w', encoding='ascii', newline='\n') as header_file:
            header_file.write('\n'.join(lines)+'\n')
    module_version = (NATIVE / 'runtime_profile.h').read_text(encoding='ascii')
    if f'kModuleVersion = "{VERSION}"' not in module_version:
        raise RuntimeError('runtime_profile.h/version mismatch; set QUEST_LD_RUNTIME_IMAGE to revalidate')
    if selected is None:
        print('Compiling with reviewed pinned headers; original firmware is not being revalidated')
    else:
        print(f'Revalidated pinned identity for {selected["key"]} from the supplied runtime image')


def build():
    generate_identity(SO)
    BUILD.mkdir(exist_ok=True)
    ndk_build = NDK / ('ndk-build.cmd' if os.name == 'nt' else 'ndk-build')
    if not ndk_build.is_file():
        raise RuntimeError('Set ANDROID_NDK_HOME to an installed Android NDK r27d')
    args = [str(ndk_build), 'NDK_PROJECT_PATH=null',
            'APP_BUILD_SCRIPT=' + str(NATIVE/'Android.mk'),
            'NDK_APPLICATION_MK=' + str(NATIVE/'Application.mk'),
            'NDK_OUT=' + str(BUILD/'obj'), 'NDK_LIBS_OUT=' + str(BUILD/'libs'), '-j4']
    subprocess.run(args, cwd=ROOT, check=True)
    subprocess.run(['powershell.exe', '-NoProfile', '-ExecutionPolicy', 'Bypass', '-File',
                    str(ROOT/'controller/build_controller.ps1')], cwd=ROOT, check=True)


def package():
    output = ROOT / f'questpro_local_dimming-{VERSION}.zip'
    if output.exists():
        raise RuntimeError('Refusing to replace a released ZIP: ' + str(output))
    module_prop = dict(line.split('=', 1) for line in (NATIVE/'package/module.prop').read_text().splitlines() if '=' in line)
    assert module_prop['version'] == VERSION
    settings_report = json.loads((ROOT/'sample_lut_evidence/settings_report.json').read_text())
    assert settings_report['ldctl_sha256'] == hashlib.sha256((BUILD/'libs/arm64-v8a/ldctl').read_bytes()).hexdigest()
    assert settings_report['library_sha256'] == hashlib.sha256((BUILD/'libs/arm64-v8a/libsettings_test.so').read_bytes()).hexdigest()
    compiled_report = json.loads((ROOT/'sample_lut_evidence/compiled_report.json').read_text())
    assert compiled_report['library_sha256'] == hashlib.sha256((BUILD/'libs/arm64-v8a/libsample_lut_test.so').read_bytes()).hexdigest()
    entries = {
        'zygisk/arm64-v8a.so': BUILD/'libs/arm64-v8a/libquestpro_sample_lut.so',
        'bin/ldctl': BUILD/'libs/arm64-v8a/ldctl',
        'QuestProLDControl.apk': ROOT/f'controller/build/questpro-ld-control-{VERSION}.apk',
    }
    for file in (NATIVE/'package').iterdir():
        if file.is_file():
            name = 'META-INF/com/google/android/' + file.name if file.name in ['update-binary', 'updater-script'] else file.name
            entries[name] = file
    for directory in [SOURCE/'staged', NATIVE]:
        for file in directory.iterdir():
            if file.is_file() and file.suffix in ['.cpp', '.h', '.mk']:
                entries['source/' + file.relative_to(ROOT).as_posix()] = file
    controller = ROOT/'controller'
    for directory in [controller/'src', controller/'res', controller/'test']:
        for file in directory.rglob('*'):
            if file.is_file():
                entries['source/' + file.relative_to(ROOT).as_posix()] = file
    for file in [controller/'AndroidManifest.xml', controller/'README.txt', controller/'build_controller.ps1',
                 controller/'test_controller.ps1', controller/'test_helper.cjs', controller/'test_boot.cjs',
                 controller/'test_installer.cjs', controller/'test_settings_oracle.py', controller/'VALIDATION.md']:
        entries['source/controller/' + file.name] = file
    # Include the exact build inputs and offline validation reports, while
    # excluding object files and the old legacy implementation.
    entries['source/build_sample_lut.py'] = Path(__file__)
    entries['source/zygisk_local_dimming/native/zygisk.hpp'] = SOURCE/'native/zygisk.hpp'
    for file in (NATIVE / 'package').iterdir():
        if file.is_file():
            entries['source/' + file.relative_to(ROOT).as_posix()] = file
    for name in ['native_reference.js', 'native_reference.test.js', 'sample_lut_reference.js',
                 'sample_lut_reference.test.js', 'runtime_images.py', 'native_oracle.py', 'sample_lut_oracle.py',
                 'stage_bridge_oracle.py', 'bridge_integration_oracle.py', 'compiled_sample_lut_oracle.py',
                 'requirements-dev.txt', '.gitattributes', '.gitignore', 'AGENTS.md']:
        entries['source/' + name] = ROOT / name
    for name in ['LICENSE', 'THIRD_PARTY_NOTICES.md', 'README.md', 'COMPATIBILITY.md',
                 'BUILDING.md', 'RELEASE_NOTES_0.5.0.md', 'VALIDATION.md']:
        entries[name] = ROOT / name
        entries['source/' + name] = ROOT / name
    for file in [ROOT/'sample_lut_evidence/compiled_report.json', ROOT/'sample_lut_evidence/bridge_integration_report.json',
                 ROOT/'sample_lut_evidence/contract_report.json', ROOT/'sample_lut_evidence/settings_report.json']:
        entries['evidence/' + file.name] = file
    manifest = {name: hashlib.sha256(file.read_bytes()).hexdigest() for name, file in entries.items()}
    with zipfile.ZipFile(output, 'x', zipfile.ZIP_DEFLATED) as archive:
        for name, file in entries.items():
            archive.write(file, name)
        archive.writestr('SHA256SUMS.json', json.dumps(manifest, indent=2)+'\n')
    with zipfile.ZipFile(output) as archive:
        assert archive.testzip() is None
        for name, digest in manifest.items():
            assert hashlib.sha256(archive.read(name)).hexdigest() == digest
    digest = hashlib.sha256(output.read_bytes()).hexdigest()
    (output.with_suffix('.zip.sha256')).write_text(digest+'  '+output.name+'\n', encoding='ascii')
    print(json.dumps(dict(zip=str(output), sha256=digest, entries=len(entries)), indent=2))


if __name__ == '__main__':
    if '--identity' in sys.argv:
        generate_identity(SO)
    elif '--package' in sys.argv:
        package()
    else:
        build()
