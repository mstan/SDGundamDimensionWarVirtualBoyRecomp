param([string]$Rom = '', [string]$Build = 'build',
      [ValidateSet('saved','ja','en')][string]$Language = 'saved',
      [ValidateSet('saved','on','off')][string]$Color = 'saved',
      [string]$Executable = '', [string]$Profile = '')
$ErrorActionPreference='Stop'
$projectRoot=[IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..'))
if(!$Rom) { $Rom=Join-Path $projectRoot 'roms/sd_gundam.vb' }
$exe=if($Executable){[IO.Path]::GetFullPath($Executable)}else{Join-Path (Join-Path $projectRoot $Build) 'vbrecomp/runtime/SDGundamDimensionWarVirtualBoyRecomp.exe'}
if(!(Test-Path -LiteralPath $exe)) { throw 'Build the game with tools/build.ps1 first.' }
if(!(Test-Path -LiteralPath $Rom)) { throw "Missing Japanese cartridge: $Rom" }
$arguments=@('--launcher','--rom',$Rom)
$profileRoot=Split-Path -Parent $exe
if($Profile) {
    $profileRoot=[IO.Path]::GetFullPath($Profile)
    [IO.Directory]::CreateDirectory($profileRoot) | Out-Null
    $arguments+=@('--config',(Join-Path $profileRoot 'vbrecomp.cfg'),'--mods-dir',(Join-Path $profileRoot 'mods'))
}
if($Language -ne 'saved') {
    $installed=Join-Path $profileRoot 'mods/packages/sd-gundam-english/0.1.0/manifest.toml'
    if(!(Test-Path -LiteralPath $installed)) {
        $package=Join-Path $projectRoot 'dist/sd-gundam-english-0.1.0.vbmod'
        if(!(Test-Path -LiteralPath $package)) { throw 'Build the translation package first.' }
        $arguments+=@('--install-mod',$package)
    }
    $arguments+=@($(if($Language -eq 'en'){'--enable-mod'}else{'--disable-mod'}),'sd-gundam-english:english')
}
if($Color -ne 'saved') {
    $installed=Join-Path $profileRoot 'mods/packages/sd-gundam-color/0.1.0/manifest.toml'
    if(!(Test-Path -LiteralPath $installed)) {
        $package=Join-Path $projectRoot 'dist/sd-gundam-color-0.1.0.vbmod'
        if(!(Test-Path -LiteralPath $package)) { throw 'Build the color package first.' }
        $arguments+=@('--install-mod',$package)
    }
    $arguments+=@($(if($Color -eq 'on'){'--enable-mod'}else{'--disable-mod'}),'sd-gundam-color:color')
}
& $exe @arguments
if($LASTEXITCODE) { throw "Game exited with code $LASTEXITCODE" }
