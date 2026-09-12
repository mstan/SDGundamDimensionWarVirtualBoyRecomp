param(
    [string]$Rom = '',
    [string]$Framework = '',
    [string]$Ui = '',
    [string]$Oracle = '',
    [string]$Build = 'build',
    [string]$Toolchain = 'C:\msys64\mingw64\bin',
    [string]$Python = '',
    [switch]$NoUi,
    [switch]$FastBuild,
    [switch]$Production
)
$ErrorActionPreference='Stop'
if($FastBuild -and $Production) { throw 'Use FastBuild for development or Production for release, not both.' }
$projectRoot=[IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..'))
if(!$Python) { $Python=(Get-Command python.exe -ErrorAction Stop).Source }
if(!$Rom) { $Rom=Join-Path $projectRoot 'roms\sd_gundam.vb' }
if(!$Framework) { $Framework=Join-Path $projectRoot 'vbrecomp' }
if(!$Ui) { $Ui=Join-Path $projectRoot 'recomp-ui' }
if(!$Oracle) { $Oracle=Join-Path $projectRoot 'beetle-vb' }
foreach($path in @($Rom,$Framework,$Python,(Join-Path $Toolchain 'cmake.exe'),(Join-Path $Toolchain 'ninja.exe'),
    (Join-Path $Toolchain 'gcc.exe'),(Join-Path $Toolchain 'g++.exe'))) {
    if(!(Test-Path -LiteralPath $path)) { throw "Missing dependency: $path" }
}
if(!$NoUi -and !(Test-Path -LiteralPath (Join-Path $Ui 'recomp_ui.cmake'))) {
    throw 'recomp-ui is missing. Run git submodule update --init --recursive.'
}
$expected='98d210dcbd1c5d836aa5bbf018eb26e971711b69b4423187bbb72178d5da9a92'
if((Get-FileHash -LiteralPath $Rom -Algorithm SHA256).Hash.ToLowerInvariant() -ne $expected) { throw 'Wrong SD Gundam Japanese cartridge revision' }
$Rom=(Resolve-Path -LiteralPath $Rom).Path
$Framework=(Resolve-Path -LiteralPath $Framework).Path
if(Test-Path -LiteralPath $Ui) { $Ui=(Resolve-Path -LiteralPath $Ui).Path }
if(Test-Path -LiteralPath $Oracle) { $Oracle=(Resolve-Path -LiteralPath $Oracle).Path }
$buildPath=[IO.Path]::GetFullPath((Join-Path $projectRoot $Build))
$previousPath=$env:PATH
function Invoke-Native([string]$Executable,[string[]]$Arguments) {
    $previousPreference=$ErrorActionPreference
    try {
        $ErrorActionPreference='Continue'
        & $Executable @Arguments
        $nativeExit=$LASTEXITCODE
    } finally { $ErrorActionPreference=$previousPreference }
    if($nativeExit -ne 0) { throw "$Executable failed ($nativeExit)" }
}
try {
    $env:PATH=$Toolchain+';'+$env:PATH
    Push-Location -LiteralPath $Framework
    try {
        Invoke-Native $Python @('-m','recompiler.cli.vbrecomp_codegen','--rom',$Rom,'--module','sd_gundam',
            '--out',(Join-Path $projectRoot 'generated'),'--seeds-toml',(Join-Path $projectRoot 'sd_gundam.toml'))
    } finally { Pop-Location }
    $options=@('-S',$projectRoot,'-B',$buildPath,'-G','Ninja','-DCMAKE_BUILD_TYPE=Release',
        "-DCMAKE_MAKE_PROGRAM=$Toolchain/ninja.exe","-DCMAKE_C_COMPILER=$Toolchain/gcc.exe",
        "-DCMAKE_CXX_COMPILER=$Toolchain/g++.exe","-DPython3_EXECUTABLE=$Python",
        "-DVBRECOMP_ROOT=$Framework","-DRECOMP_UI_ROOT=$Ui","-DBEETLE_VB_ROOT=$Oracle","-DSD_GUNDAM_ROM=$Rom",
        ('-DSD_GUNDAM_UI='+$(if($NoUi){'OFF'}else{'ON'})),
        ('-DSD_GUNDAM_FAST_BUILD='+$(if($FastBuild){'ON'}else{'OFF'})),
        ('-DVBRECOMP_DEBUG_TOOLS='+$(if($Production){'OFF'}else{'ON'})),
        ('-DVBRECOMP_CPUHOOK='+$(if($Production){'OFF'}else{'ON'})))
    Invoke-Native (Join-Path $Toolchain 'cmake.exe') $options
    Invoke-Native (Join-Path $Toolchain 'cmake.exe') @('--build',$buildPath,'--parallel','8')
    Invoke-Native (Join-Path $Toolchain 'ctest.exe') @('--test-dir',$buildPath,'--output-on-failure')
} finally { $env:PATH=$previousPath }
