param([string]$Rom = '', [string]$Build = 'build')
$ErrorActionPreference='Stop'
$projectRoot=[IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..'))
if(!$Rom) { $Rom=Join-Path $projectRoot 'roms/sd_gundam.vb' }
$exe=Join-Path (Join-Path $projectRoot $Build) 'vbrecomp/runtime/SDGundamDimensionWarVirtualBoyRecomp.exe'
if(!(Test-Path -LiteralPath $exe)) { throw 'Build the game with tools/build.ps1 first.' }
if(!(Test-Path -LiteralPath $Rom)) { throw "Missing Japanese cartridge: $Rom" }
& $exe --launcher --rom $Rom
if($LASTEXITCODE) { throw "Game exited with code $LASTEXITCODE" }
