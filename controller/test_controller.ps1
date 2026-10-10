$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $MyInvocation.MyCommand.Path
$out = Join-Path $root 'build\test-classes'
New-Item -ItemType Directory -Path $out -Force | Out-Null
$files = @((Join-Path $root 'src\com\questpro\ldcontrol\ControllerState.java'),
           (Join-Path $root 'src\com\questpro\ldcontrol\DebugParameters.java'),
           (Join-Path $root 'src\com\questpro\ldcontrol\RootRunner.java')) +
    @(Get-ChildItem -Path (Join-Path $root 'test') -Filter *.java | Select-Object -ExpandProperty FullName)
& javac --release 8 -d $out $files
if ($LASTEXITCODE -ne 0) { throw 'Test compilation failed' }
& java -cp $out com.questpro.ldcontrol.ControllerTest $out
if ($LASTEXITCODE -ne 0) { throw 'Controller tests failed' }
