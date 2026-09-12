param([string]$Rom = '', [string]$Build = 'build',
      [ValidateSet('saved','ja','en')][string]$Language = 'saved')
$ErrorActionPreference='Stop'
$projectRoot=[IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..'))
if(!$Rom) { $Rom=Join-Path $projectRoot 'roms/sd_gundam.vb' }
$exe=Join-Path (Join-Path $projectRoot $Build) 'vbrecomp/runtime/SDGundamDimensionWarVirtualBoyRecomp.exe'
if(!(Test-Path -LiteralPath $exe)) { throw 'Build the game with tools/build.ps1 first.' }
if(!(Test-Path -LiteralPath $Rom)) { throw "Missing Japanese cartridge: $Rom" }
$arguments=@('--launcher','--rom',$Rom)
if($Language -ne 'saved') {
    $installed=Join-Path (Split-Path -Parent $exe) 'mods/packages/sd-gundam-english/0.1.0/manifest.toml'
    if(!(Test-Path -LiteralPath $installed)) {
        $package=Join-Path $projectRoot 'dist/sd-gundam-english-0.1.0.vbmod'
        if(!(Test-Path -LiteralPath $package)) { throw 'Build the translation package first.' }
        $arguments+=@('--install-mod',$package)
    }
    $arguments+=@($(if($Language -eq 'en'){'--enable-mod'}else{'--disable-mod'}),'sd-gundam-english:english')
}
& $exe @arguments
if($LASTEXITCODE) { throw "Game exited with code $LASTEXITCODE" }
