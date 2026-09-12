param(
    [string]$Framework = '',
    [string]$Build = 'build',
    [string]$Rom = '',
    [string]$Route = 'tests/boot-route.json',
    [string]$Out = 'validation/boot',
    [string]$Python = '',
    [int]$Port = 4690,
    [switch]$Gates,
    [switch]$NativeOnly
)
$ErrorActionPreference='Stop'
$projectRoot=[IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..'))
if(!$Framework) { $Framework=Join-Path $projectRoot 'vbrecomp' }
if(!$Rom) { $Rom=Join-Path $projectRoot 'roms/sd_gundam.vb' }
if(!$Python) { $Python=(Get-Command python.exe -ErrorAction Stop).Source }
$buildPath=[IO.Path]::GetFullPath((Join-Path $projectRoot $Build))
$outPath=[IO.Path]::GetFullPath((Join-Path $projectRoot $Out))
if(Test-Path -LiteralPath $outPath) { throw "Use a new validation directory: $outPath" }
$arguments=@((Join-Path $Framework 'tools/cosim.py'),$(if($Gates){'gates'}else{'compare'}),
    '--runtime',(Join-Path $buildPath 'vbrecomp/runtime/SDGundamDimensionWarVirtualBoyRecomp.exe'),
    '--oracle',(Join-Path $buildPath 'vbrecomp/runtime/vb-beetle.exe'),
    '--rom',$Rom,'--route',(Join-Path $projectRoot $Route),'--out',$outPath,'--port',"$Port")
if($NativeOnly) { $arguments+=@('--a-mode','native') }
& $Python @arguments
if($LASTEXITCODE) { throw "Parity validation failed; see $outPath" }
