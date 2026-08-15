param(
    [string]$FfmpegRoot = "",
    [string]$DistRoot = "",
    [switch]$SkipTests
)

$ErrorActionPreference = "Stop"
$projectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$python = Join-Path $projectRoot ".venv\Scripts\python.exe"
if ([string]::IsNullOrWhiteSpace($DistRoot)) {
    $distRoot = Join-Path $projectRoot "dist"
}
elseif ([IO.Path]::IsPathRooted($DistRoot)) {
    $distRoot = [IO.Path]::GetFullPath($DistRoot)
}
else {
    $distRoot = [IO.Path]::GetFullPath((Join-Path $projectRoot $DistRoot))
}
$repositoryPrefix = $projectRoot.TrimEnd('\') + '\'
if (-not $distRoot.StartsWith($repositoryPrefix, [StringComparison]::OrdinalIgnoreCase)) {
    throw "Portable output must remain inside the repository: $distRoot"
}
$appRoot = Join-Path $distRoot "Tokkun99Logger"
$workRoot = Join-Path $projectRoot "build\pyinstaller"
$ffmpegCacheRoot = Join-Path $projectRoot "build\ffmpeg-lgpl"
$ffmpegExtractRoot = Join-Path $ffmpegCacheRoot "extracted"
$ffmpegManifestPath = Join-Path $projectRoot "packaging\ffmpeg-manifest.json"
$ffmpegComponentsPath = Join-Path $projectRoot "packaging\ffmpeg-components.json"
$ffmpegRecipesPath = Join-Path $projectRoot "packaging\ffmpeg-build-recipes.json"
$ffmpegRecipeLicensesPath = Join-Path $projectRoot "packaging\ffmpeg-recipe-licenses.json"
$ffmpegRecipeLicenseRoot = Join-Path $projectRoot "packaging\ffmpeg-recipe-licenses"
$ffmpegNestedLicensesPath = Join-Path $projectRoot "packaging\ffmpeg-nested-licenses.json"
$ffmpegNestedLicenseRoot = Join-Path $projectRoot "packaging\ffmpeg-nested-licenses"
$ffmpegNestedDependenciesPath = Join-Path $projectRoot "packaging\ffmpeg-nested-dependencies.json"
$ffmpegVendoredLicensesPath = Join-Path $projectRoot "packaging\ffmpeg-vendored-licenses.json"
$ffmpegVendoredLicenseRoot = Join-Path $projectRoot "packaging\ffmpeg-vendored-licenses"
$ffmpegVendoredCodePath = Join-Path $projectRoot "packaging\ffmpeg-vendored-code.json"
$ffmpegAdditionalSourcesPath = Join-Path $projectRoot "packaging\ffmpeg-additional-source-classification.json"
$rav1eCargoLicensesPath = Join-Path $projectRoot "packaging\rav1e-cargo-licenses.json"
$rav1eCargoLicenseRoot = Join-Path $projectRoot "packaging\rav1e-cargo-licenses"
$rav1eCargoLockPath = Join-Path $projectRoot "packaging\rav1e-Cargo.lock"
$ffmpegVerifier = Join-Path $projectRoot "scripts\verify_ffmpeg_distribution.py"

function Remove-SafeBuildDirectory([string]$Path) {
    $fullPath = [IO.Path]::GetFullPath($Path)
    $allowedPrefix = $projectRoot.TrimEnd('\') + '\'
    if (-not $fullPath.StartsWith($allowedPrefix, [StringComparison]::OrdinalIgnoreCase)) {
        throw "Refusing to remove a path outside the repository: $fullPath"
    }
    if ($fullPath -notin @(
        [IO.Path]::GetFullPath($appRoot),
        [IO.Path]::GetFullPath($workRoot)
    )) {
        throw "Refusing to remove an unexpected build path: $fullPath"
    }
    if (Test-Path -LiteralPath $fullPath) {
        Remove-Item -LiteralPath $fullPath -Recurse -Force
    }
}

if (-not (Test-Path -LiteralPath $python -PathType Leaf)) {
    throw "Dedicated Python environment not found: $python"
}
if (-not [Environment]::Is64BitProcess) {
    throw "The portable Windows build must run from a 64-bit process"
}

$ffmpegManifest = Get-Content -Raw -Encoding UTF8 -LiteralPath $ffmpegManifestPath | ConvertFrom-Json
if ([IO.Path]::GetFileName($ffmpegManifest.archive_name) -ne $ffmpegManifest.archive_name) {
    throw "FFmpeg manifest archive_name must be a file name"
}
if ([IO.Path]::GetFileName($ffmpegManifest.archive_root) -ne $ffmpegManifest.archive_root) {
    throw "FFmpeg manifest archive_root must be a directory name"
}
$ffmpegArchive = $null
if ([string]::IsNullOrWhiteSpace($FfmpegRoot)) {
    New-Item -ItemType Directory -Force -Path $ffmpegCacheRoot | Out-Null
    $ffmpegArchive = Join-Path $ffmpegCacheRoot $ffmpegManifest.archive_name
    if (-not (Test-Path -LiteralPath $ffmpegArchive -PathType Leaf)) {
        Write-Host "Downloading pinned LGPL FFmpeg archive..."
        Invoke-WebRequest -UseBasicParsing -Uri $ffmpegManifest.archive_url -OutFile $ffmpegArchive
    }
    $actualArchiveHash = (Get-FileHash -Algorithm SHA256 -LiteralPath $ffmpegArchive).Hash
    if ($actualArchiveHash -ne $ffmpegManifest.archive_sha256) {
        throw "FFmpeg archive SHA-256 does not match packaging/ffmpeg-manifest.json: $actualArchiveHash"
    }
    $candidateRoot = Join-Path $ffmpegExtractRoot $ffmpegManifest.archive_root
    if (-not (Test-Path -LiteralPath $candidateRoot -PathType Container)) {
        New-Item -ItemType Directory -Force -Path $ffmpegExtractRoot | Out-Null
        Expand-Archive -LiteralPath $ffmpegArchive -DestinationPath $ffmpegExtractRoot
    }
    $ffmpegRootResolved = (Resolve-Path -LiteralPath $candidateRoot).Path
}
else {
    $ffmpegRootResolved = (Resolve-Path -LiteralPath $FfmpegRoot).Path
}

$ffmpeg = Join-Path $ffmpegRootResolved "bin\ffmpeg.exe"
$ffprobe = Join-Path $ffmpegRootResolved "bin\ffprobe.exe"
foreach ($required in @(
    $ffmpeg,
    $ffprobe,
    (Join-Path $ffmpegRootResolved $ffmpegManifest.license_file),
    $ffmpegComponentsPath,
    $ffmpegRecipesPath,
    $ffmpegRecipeLicensesPath,
    $ffmpegNestedLicensesPath,
    $ffmpegNestedDependenciesPath,
    $ffmpegVendoredLicensesPath,
    $ffmpegVendoredCodePath,
    $ffmpegAdditionalSourcesPath,
    (Join-Path $projectRoot "data\template\states\v1\profile.json"),
    (Join-Path $projectRoot "data\template\glyphs\v1\profile.json")
)) {
    if (-not (Test-Path -LiteralPath $required -PathType Leaf)) {
        throw "Required build input not found: $required"
    }
}
$verifyArguments = @(
    $ffmpegVerifier,
    "--manifest", $ffmpegManifestPath,
    "--ffmpeg-root", $ffmpegRootResolved,
    "--components", $ffmpegComponentsPath
)
if ($null -ne $ffmpegArchive) { $verifyArguments += @("--archive", $ffmpegArchive) }
& $python @verifyArguments
if ($LASTEXITCODE -ne 0) { throw "FFmpeg distribution verification failed" }

if (-not $SkipTests) {
    $env:TOKKUN99_TEST_FFMPEG = $ffmpeg
    $env:TOKKUN99_TEST_FFPROBE = $ffprobe
    try {
        & $python -m pytest -q
        if ($LASTEXITCODE -ne 0) { throw "Tests failed" }
    }
    finally {
        Remove-Item Env:TOKKUN99_TEST_FFMPEG -ErrorAction SilentlyContinue
        Remove-Item Env:TOKKUN99_TEST_FFPROBE -ErrorAction SilentlyContinue
    }
}

if (Test-Path -LiteralPath (Join-Path $appRoot "data")) {
    throw "Existing portable data must be backed up and removed before a clean build: $appRoot\data"
}
Remove-SafeBuildDirectory $appRoot
Remove-SafeBuildDirectory $workRoot
New-Item -ItemType Directory -Force -Path $distRoot | Out-Null

$env:TOKKUN99_FFMPEG_ROOT = $ffmpegRootResolved
try {
    & $python -m PyInstaller `
        --noconfirm `
        --clean `
        --distpath $distRoot `
        --workpath $workRoot `
        (Join-Path $projectRoot "packaging\Tokkun99Logger.spec")
    if ($LASTEXITCODE -ne 0) { throw "PyInstaller build failed" }
}
finally {
    Remove-Item Env:TOKKUN99_FFMPEG_ROOT -ErrorAction SilentlyContinue
}

Copy-Item -LiteralPath (Join-Path $projectRoot "packaging\README_PORTABLE.txt") `
    -Destination (Join-Path $appRoot "README.txt")
Copy-Item -LiteralPath (Join-Path $projectRoot "LICENSE") `
    -Destination (Join-Path $appRoot "LICENSE")
Copy-Item -LiteralPath (Join-Path $projectRoot "THIRD_PARTY_ASSETS.md") `
    -Destination (Join-Path $appRoot "THIRD_PARTY_ASSETS.md")
& $python -c "import pathlib, sys; sys.path.insert(0, sys.argv[1]); from tokkun99_logger import __version__; pathlib.Path(sys.argv[2]).write_text(__version__ + '\n', encoding='utf-8')" `
    (Join-Path $projectRoot "src") `
    (Join-Path $appRoot "VERSION.txt")
if ($LASTEXITCODE -ne 0) { throw "Version metadata generation failed" }
& $python (Join-Path $projectRoot "scripts\collect_portable_licenses.py") `
    --output (Join-Path $appRoot "LICENSES") `
    --ffmpeg-root $ffmpegRootResolved `
    --ffmpeg-manifest $ffmpegManifestPath `
    --ffmpeg-components $ffmpegComponentsPath `
    --ffmpeg-recipes $ffmpegRecipesPath `
    --ffmpeg-recipe-licenses $ffmpegRecipeLicensesPath `
    --ffmpeg-recipe-license-root $ffmpegRecipeLicenseRoot `
    --ffmpeg-nested-licenses $ffmpegNestedLicensesPath `
    --ffmpeg-nested-license-root $ffmpegNestedLicenseRoot `
    --ffmpeg-nested-dependencies $ffmpegNestedDependenciesPath `
    --ffmpeg-vendored-licenses $ffmpegVendoredLicensesPath `
    --ffmpeg-vendored-license-root $ffmpegVendoredLicenseRoot `
    --ffmpeg-vendored-code $ffmpegVendoredCodePath `
    --ffmpeg-additional-sources $ffmpegAdditionalSourcesPath `
    --rav1e-cargo-licenses $rav1eCargoLicensesPath `
    --rav1e-cargo-license-root $rav1eCargoLicenseRoot `
    --rav1e-cargo-lock $rav1eCargoLockPath
if ($LASTEXITCODE -ne 0) { throw "License collection failed" }

foreach ($requiredOutput in @(
    (Join-Path $appRoot "Tokkun99Logger.exe"),
    (Join-Path $appRoot "_internal\ffmpeg.exe"),
    (Join-Path $appRoot "_internal\sqlite3.dll"),
    (Join-Path $appRoot "_internal\tcl86t.dll"),
    (Join-Path $appRoot "_internal\tk86t.dll"),
    (Join-Path $appRoot "_internal\template\states\v1\profile.json"),
    (Join-Path $appRoot "_internal\template\glyphs\v1\profile.json"),
    (Join-Path $appRoot "LICENSES\THIRD_PARTY_NOTICES.txt"),
    (Join-Path $appRoot "LICENSES\FFmpeg-LGPL-3.0-or-later.txt"),
    (Join-Path $appRoot "LICENSES\FFmpeg-BUILD.txt"),
    (Join-Path $appRoot "LICENSES\FFmpeg-MANIFEST.json"),
    (Join-Path $appRoot "LICENSES\FFmpeg-COMPONENTS.json"),
    (Join-Path $appRoot "LICENSES\FFmpeg-BUILD-RECIPES.json"),
    (Join-Path $appRoot "LICENSES\FFmpeg-RECIPE-LICENSES.json"),
    (Join-Path $appRoot "LICENSES\FFmpeg-NESTED-LICENSES.json"),
    (Join-Path $appRoot "LICENSES\FFmpeg-NESTED-DEPENDENCIES.json"),
    (Join-Path $appRoot "LICENSES\FFmpeg-VENDORED-LICENSES.json"),
    (Join-Path $appRoot "LICENSES\FFmpeg-VENDORED-CODE.json"),
    (Join-Path $appRoot "LICENSES\FFmpeg-ADDITIONAL-SOURCES.json"),
    (Join-Path $appRoot "LICENSES\RAV1E-CARGO-LICENSES.json"),
    (Join-Path $appRoot "LICENSES\RAV1E-Cargo.lock"),
    (Join-Path $appRoot "LICENSE"),
    (Join-Path $appRoot "THIRD_PARTY_ASSETS.md"),
    (Join-Path $appRoot "README.txt"),
    (Join-Path $appRoot "VERSION.txt")
)) {
    if (-not (Test-Path -LiteralPath $requiredOutput -PathType Leaf)) {
        throw "Required portable output not found: $requiredOutput"
    }
}
if (Test-Path -LiteralPath (Join-Path $appRoot "data")) {
    throw "Portable build must not contain user data"
}

$size = (Get-ChildItem -LiteralPath $appRoot -Recurse -File | Measure-Object Length -Sum).Sum
Write-Host "Portable onedir build complete: $appRoot"
Write-Host ("Size: {0:N1} MiB" -f ($size / 1MB))
