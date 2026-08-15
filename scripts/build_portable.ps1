param(
    [string]$FfmpegRoot = "C:\tools\ffmpeg",
    [switch]$SkipTests
)

$ErrorActionPreference = "Stop"
$projectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$python = Join-Path $projectRoot ".venv\Scripts\python.exe"
$distRoot = Join-Path $projectRoot "dist"
$appRoot = Join-Path $distRoot "Tokkun99Logger"
$workRoot = Join-Path $projectRoot "build\pyinstaller"
$ffmpegRootResolved = (Resolve-Path -LiteralPath $FfmpegRoot).Path
$ffmpegManifestPath = Join-Path $projectRoot "packaging\ffmpeg-manifest.json"

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

$ffmpeg = Join-Path $ffmpegRootResolved "bin\ffmpeg.exe"
$ffmpegManifest = Get-Content -Raw -Encoding UTF8 -LiteralPath $ffmpegManifestPath | ConvertFrom-Json
foreach ($required in @(
    $ffmpeg,
    (Join-Path $ffmpegRootResolved "LICENSE"),
    (Join-Path $ffmpegRootResolved "README.txt"),
    (Join-Path $projectRoot "data\template\states\v1\profile.json"),
    (Join-Path $projectRoot "data\template\glyphs\v1\profile.json")
)) {
    if (-not (Test-Path -LiteralPath $required -PathType Leaf)) {
        throw "Required build input not found: $required"
    }
}
$actualFfmpegHash = (Get-FileHash -Algorithm SHA256 -LiteralPath $ffmpeg).Hash
if ($actualFfmpegHash -ne $ffmpegManifest.sha256) {
    throw "FFmpeg SHA-256 does not match packaging/ffmpeg-manifest.json: $actualFfmpegHash"
}

if (-not $SkipTests) {
    & $python -m pytest -q
    if ($LASTEXITCODE -ne 0) { throw "Tests failed" }
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
& $python -c "import pathlib, sys; sys.path.insert(0, sys.argv[1]); from tokkun99_logger import __version__; pathlib.Path(sys.argv[2]).write_text(__version__ + '\n', encoding='utf-8')" `
    (Join-Path $projectRoot "src") `
    (Join-Path $appRoot "VERSION.txt")
if ($LASTEXITCODE -ne 0) { throw "Version metadata generation failed" }
& $python (Join-Path $projectRoot "scripts\collect_portable_licenses.py") `
    --output (Join-Path $appRoot "LICENSES") `
    --ffmpeg-root $ffmpegRootResolved `
    --ffmpeg-manifest $ffmpegManifestPath
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
