$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $MyInvocation.MyCommand.Path
$module = Join-Path (Split-Path -Parent $root) 'zygisk_local_dimming\sample_lut\package\module.prop'
$version = (Get-Content $module | Where-Object { $_ -match '^version=' }) -replace '^version=', ''
$versionCode = (Get-Content $module | Where-Object { $_ -match '^versionCode=' }) -replace '^versionCode=', ''
$sdk = if ($env:ANDROID_SDK_ROOT) { $env:ANDROID_SDK_ROOT } elseif ($env:ANDROID_HOME) { $env:ANDROID_HOME } else { Join-Path (Split-Path -Parent $root) '.build-deps\android-sdk' }
$platform = Join-Path $sdk 'platforms\android-35\android.jar'
$tools = Join-Path $sdk 'build-tools\35.0.0'
$out = Join-Path $root 'build'
$working = Join-Path $out ('working\' + [guid]::NewGuid().ToString('N'))
$gen = Join-Path $working 'gen'
$classes = Join-Path $working 'classes'
$dex = Join-Path $working 'dex'
$unsigned = Join-Path $working 'controller-unsigned.apk'
$aligned = Join-Path $out "questpro-ld-control-$version.apk"
$keystore = if ($env:QUEST_LD_KEYSTORE) { $env:QUEST_LD_KEYSTORE } else { Join-Path $out 'controller-debug.keystore' }
if ($env:QUEST_LD_KEYSTORE -and !(Test-Path -LiteralPath $keystore)) { throw 'QUEST_LD_KEYSTORE must point to an existing private signing key' }
if (!$env:QUEST_LD_STORE_PASS) { $env:QUEST_LD_STORE_PASS = 'android' }
if (!$env:QUEST_LD_KEY_PASS) { $env:QUEST_LD_KEY_PASS = 'android' }
$keyAlias = if ($env:QUEST_LD_KEY_ALIAS) { $env:QUEST_LD_KEY_ALIAS } else { 'controller' }
New-Item -ItemType Directory -Force -Path $out,$gen,$classes,$dex | Out-Null
if (Test-Path -LiteralPath $aligned) { throw "Refusing to replace an existing APK: $aligned" }
function Invoke-Native([string]$Executable, [string[]]$Arguments) {
    & $Executable @Arguments
    if ($LASTEXITCODE -ne 0) { throw "Command failed ($LASTEXITCODE): $Executable $Arguments" }
}
Invoke-Native (Join-Path $tools 'aapt2.exe') @('compile', '--dir', (Join-Path $root 'res'), '-o', (Join-Path $working 'resources.zip'))
Invoke-Native (Join-Path $tools 'aapt2.exe') @(
    'link', '-o', $unsigned, '-I', $platform, '--manifest', (Join-Path $root 'AndroidManifest.xml'),
    '--java', $gen, '--auto-add-overlay', (Join-Path $working 'resources.zip'), '--min-sdk-version', '29',
    '--target-sdk-version', '35', '--version-code', $versionCode, '--version-name', $version)
$javaFiles = @(Get-ChildItem -Recurse -Filter *.java (Join-Path $root 'src') | Select-Object -ExpandProperty FullName) +
    (Get-ChildItem -Recurse -Filter R.java $gen | Select-Object -ExpandProperty FullName)
Invoke-Native 'javac' (@('--release', '8', '-encoding', 'UTF-8', '-classpath', $platform, '-d', $classes) + $javaFiles)
Invoke-Native (Join-Path $tools 'd8.bat') (@('--lib', $platform, '--min-api', '29', '--output', $dex) + (Get-ChildItem -Recurse -Filter *.class $classes | Select-Object -ExpandProperty FullName))
Invoke-Native 'jar' @('uf', $unsigned, '-C', $dex, 'classes.dex')
if (!(Test-Path -LiteralPath $keystore)) {
    Invoke-Native 'keytool' @('-genkeypair', '-keystore', $keystore, '-storepass:env', 'QUEST_LD_STORE_PASS', '-keypass:env', 'QUEST_LD_KEY_PASS', '-alias', $keyAlias,
        '-keyalg', 'RSA', '-keysize', '2048', '-validity', '10000', '-dname', 'CN=Quest Pro LD Control,O=Codex')
}
Invoke-Native (Join-Path $tools 'zipalign.exe') @('-f', '4', $unsigned, $aligned)
Invoke-Native (Join-Path $tools 'apksigner.bat') @('sign', '--ks', $keystore, '--ks-key-alias', $keyAlias, '--ks-pass', 'env:QUEST_LD_STORE_PASS', '--key-pass', 'env:QUEST_LD_KEY_PASS', $aligned)
Invoke-Native (Join-Path $tools 'apksigner.bat') @('verify', '--verbose', $aligned)
Write-Output $aligned
