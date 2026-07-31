[CmdletBinding()]
param(
    [int]$Jobs = 2
)

$ErrorActionPreference = "Stop"
$RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$RuntimeRoot = Join-Path $RepoRoot "telegram\.tdlib-build"
$SourceDir = Join-Path $RuntimeRoot "source"
$BuildDir = Join-Path $RuntimeRoot "build"
$InstallDir = Join-Path $RuntimeRoot "install"
$VcpkgDir = Join-Path $RuntimeRoot "vcpkg"
$PinnedCommit = "a17f87c4cff7b90b278d12b91ba0614383aaee82"
$PinnedVcpkgCommit = "f87344cac03158cbf1467264565f1fd36b382a24"

function Require-Command([string]$Name) {
    if (-not (Get-Command $Name -ErrorAction SilentlyContinue)) {
        throw "Required command '$Name' was not found on PATH."
    }
}

Require-Command git
Require-Command cmake
Require-Command ninja
Require-Command gcc
Require-Command g++

New-Item -ItemType Directory -Force -Path $RuntimeRoot | Out-Null

if (-not (Test-Path (Join-Path $SourceDir ".git"))) {
    git clone https://github.com/tdlib/td.git $SourceDir
}
git -C $SourceDir fetch --depth 1 origin $PinnedCommit
git -C $SourceDir checkout --detach $PinnedCommit

if (-not (Test-Path (Join-Path $VcpkgDir ".git"))) {
    git clone https://github.com/microsoft/vcpkg.git $VcpkgDir
}
git -C $VcpkgDir fetch --depth 1 origin $PinnedVcpkgCommit
git -C $VcpkgDir checkout --detach $PinnedVcpkgCommit
if (-not (Test-Path (Join-Path $VcpkgDir "vcpkg.exe"))) {
    & (Join-Path $VcpkgDir "bootstrap-vcpkg.bat") -disableMetrics
}

$Vcpkg = Join-Path $VcpkgDir "vcpkg.exe"
& $Vcpkg install openssl:x64-mingw-dynamic zlib:x64-mingw-dynamic gperf:x64-mingw-dynamic `
    --host-triplet=x64-mingw-dynamic --clean-after-build

$Toolchain = Join-Path $VcpkgDir "scripts\buildsystems\vcpkg.cmake"
$Installed = Join-Path $VcpkgDir "installed\x64-mingw-dynamic"
$Ninja = (Get-Command ninja).Source
$env:PATH = (Join-Path $Installed "tools\gperf") + ";" + $env:PATH

cmake --fresh -S $SourceDir -B $BuildDir -G Ninja `
    -DCMAKE_MAKE_PROGRAM:FILEPATH=$Ninja `
    -DCMAKE_BUILD_TYPE=Release `
  "-DCMAKE_INSTALL_PREFIX=$InstallDir" `
  "-DCMAKE_TOOLCHAIN_FILE=$Toolchain" `
    -DVCPKG_TARGET_TRIPLET=x64-mingw-dynamic `
    -DCCACHE_FOUND:FILEPATH= `
    -DCMAKE_C_COMPILER=gcc `
    -DCMAKE_CXX_COMPILER=g++

cmake --build $BuildDir --target tdjson --parallel $Jobs

$BinDir = Join-Path $InstallDir "bin"
New-Item -ItemType Directory -Force -Path $BinDir | Out-Null
$TdJson = Get-ChildItem -Path $BuildDir -Recurse -Filter "*tdjson.dll" | Select-Object -First 1
if (-not $TdJson) {
    throw "The build completed without producing tdjson.dll."
}
Copy-Item -Force $TdJson.FullName (Join-Path $BinDir "tdjson.dll")
Get-ChildItem -Path (Join-Path $Installed "bin") -Filter "*.dll" | Copy-Item -Destination $BinDir -Force
$CompilerBin = Split-Path (Get-Command g++).Source
foreach ($RuntimeDll in @("libgcc_s_seh-1.dll", "libstdc++-6.dll", "libwinpthread-1.dll")) {
    $RuntimePath = Join-Path $CompilerBin $RuntimeDll
    if (Test-Path $RuntimePath) {
        Copy-Item -Force $RuntimePath $BinDir
    }
}

Write-Host "TDLib $PinnedCommit installed in $BinDir"
