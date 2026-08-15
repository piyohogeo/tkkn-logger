param(
    [string]$Version = "0.1.0",
    [string]$ExpectedTag = "",
    [switch]$SkipTests,
    [switch]$SkipPortableSmoke
)

$ErrorActionPreference = "Stop"
$projectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$python = Join-Path $projectRoot ".venv\Scripts\python.exe"
$workRoot = Join-Path $projectRoot "build\release-v$Version"
$distRoot = Join-Path $workRoot "dist"
$appRoot = Join-Path $distRoot "Tokkun99Logger"
$releaseRoot = Join-Path $projectRoot "release"
$archiveName = "Tokkun99Logger-v$Version-windows-x64.zip"
$archivePath = Join-Path $releaseRoot $archiveName
$checksumPath = Join-Path $releaseRoot "SHA256SUMS.txt"
$componentManifestPath = Join-Path $projectRoot "packaging\ffmpeg-components.json"
$recipeManifestPath = Join-Path $projectRoot "packaging\ffmpeg-build-recipes.json"
$recipeLicenseManifestPath = Join-Path $projectRoot "packaging\ffmpeg-recipe-licenses.json"
$nestedLicenseManifestPath = Join-Path $projectRoot "packaging\ffmpeg-nested-licenses.json"
$vendoredLicenseManifestPath = Join-Path $projectRoot "packaging\ffmpeg-vendored-licenses.json"
$additionalSourceManifestPath = Join-Path $projectRoot "packaging\ffmpeg-additional-source-classification.json"
$rav1eCargoManifestPath = Join-Path $projectRoot "packaging\rav1e-cargo-licenses.json"

if ($Version -notmatch '^\d+\.\d+\.\d+$') { throw "Invalid release version: $Version" }
$componentManifest = Get-Content -Raw -Encoding UTF8 -LiteralPath $componentManifestPath | ConvertFrom-Json
if ($componentManifest.release_ready -ne $true) {
    throw "FFmpeg external-component notices are incomplete; refusing to build Release artifacts"
}
$recipeManifest = Get-Content -Raw -Encoding UTF8 -LiteralPath $recipeManifestPath | ConvertFrom-Json
if ($recipeManifest.release_ready -ne $true) {
    throw "FFmpeg transitive build-recipe notices are incomplete; refusing to build Release artifacts"
}
$recipeLicenseManifest = Get-Content -Raw -Encoding UTF8 -LiteralPath $recipeLicenseManifestPath | ConvertFrom-Json
if ($recipeLicenseManifest.release_ready -ne $true) {
    throw "FFmpeg nested dependency review is incomplete; refusing to build Release artifacts"
}
$nestedLicenseManifest = Get-Content -Raw -Encoding UTF8 -LiteralPath $nestedLicenseManifestPath | ConvertFrom-Json
if ($nestedLicenseManifest.release_ready -ne $true) {
    throw "FFmpeg explicit nested-source notices are incomplete; refusing to build Release artifacts"
}
$vendoredLicenseManifest = Get-Content -Raw -Encoding UTF8 -LiteralPath $vendoredLicenseManifestPath | ConvertFrom-Json
if ($vendoredLicenseManifest.release_ready -ne $true) {
    throw "FFmpeg vendored code review is incomplete; refusing to build Release artifacts"
}
$additionalSourceManifest = Get-Content -Raw -Encoding UTF8 -LiteralPath $additionalSourceManifestPath | ConvertFrom-Json
if ($additionalSourceManifest.release_ready -ne $true) {
    throw "FFmpeg multi-source recipe review is incomplete; refusing to build Release artifacts"
}
$rav1eCargoManifest = Get-Content -Raw -Encoding UTF8 -LiteralPath $rav1eCargoManifestPath | ConvertFrom-Json
$rav1eRiskAccepted = $rav1eCargoManifest.unattested_build_risk_acceptance.accepted -eq $true
if ($rav1eCargoManifest.release_ready -ne $true -or (
    $rav1eCargoManifest.actual_build_lock_attested -ne $true -and -not $rav1eRiskAccepted
)) {
    throw "rav1e Cargo dependency attestation is incomplete and its documented risk has not been accepted; refusing to build Release artifacts"
}
if (-not [string]::IsNullOrWhiteSpace($ExpectedTag) -and $ExpectedTag -ne "v$Version") {
    throw "Tag $ExpectedTag does not match application version $Version"
}
$applicationVersion = & $python -c "import sys; sys.path.insert(0, sys.argv[1]); from tokkun99_logger import __version__; print(__version__)" (Join-Path $projectRoot "src")
if ($LASTEXITCODE -ne 0 -or $applicationVersion.Trim() -ne $Version) {
    throw "Application version $applicationVersion does not match Release version $Version"
}
if (Test-Path -LiteralPath (Join-Path $appRoot "data")) {
    throw "Release staging contains data and will not be overwritten: $appRoot\data"
}

$buildArguments = @(
    "-NoProfile", "-ExecutionPolicy", "Bypass", "-File",
    (Join-Path $projectRoot "scripts\build_portable.ps1"),
    "-DistRoot", $distRoot
)
if ($SkipTests) { $buildArguments += "-SkipTests" }
& powershell.exe @buildArguments
if ($LASTEXITCODE -ne 0) { throw "Portable Release build failed" }

if (-not $SkipPortableSmoke) {
    & powershell.exe -NoProfile -ExecutionPolicy Bypass -File `
        (Join-Path $projectRoot "scripts\verify_portable.ps1") -AppRoot $appRoot
    if ($LASTEXITCODE -ne 0) { throw "Portable smoke verification failed" }
}
if (Test-Path -LiteralPath (Join-Path $appRoot "data")) {
    throw "Portable verification left data in the Release payload"
}

New-Item -ItemType Directory -Force -Path $releaseRoot | Out-Null
foreach ($output in @($archivePath, $checksumPath)) {
    $fullOutput = [IO.Path]::GetFullPath($output)
    if (-not $fullOutput.StartsWith($releaseRoot.TrimEnd('\') + '\', [StringComparison]::OrdinalIgnoreCase)) {
        throw "Refusing to replace a path outside the Release directory: $fullOutput"
    }
    if (Test-Path -LiteralPath $fullOutput) { Remove-Item -LiteralPath $fullOutput -Force }
}
$zipMinimumTime = [DateTime]::new(1980, 1, 1, 0, 0, 0, [DateTimeKind]::Local)
Get-ChildItem -LiteralPath $appRoot -Recurse -File | Where-Object {
    $_.LastWriteTime -lt $zipMinimumTime
} | ForEach-Object {
    # Some crates preserve pre-1980 archive timestamps, which ZIP cannot encode.
    # Normalize only the disposable Release staging copy; source files are untouched.
    $_.LastWriteTime = $zipMinimumTime
}
Compress-Archive -LiteralPath $appRoot -DestinationPath $archivePath -CompressionLevel Optimal
$hash = (Get-FileHash -Algorithm SHA256 -LiteralPath $archivePath).Hash.ToLowerInvariant()
[IO.File]::WriteAllText($checksumPath, "$hash  $archiveName`n", [Text.UTF8Encoding]::new($false))

$verifyArguments = @(
    (Join-Path $projectRoot "scripts\verify_release_artifacts.py"),
    "--release-dir", $releaseRoot,
    "--version", $Version
)
if (-not [string]::IsNullOrWhiteSpace($ExpectedTag)) {
    $verifyArguments += @("--expected-tag", $ExpectedTag)
}
& $python @verifyArguments
if ($LASTEXITCODE -ne 0) { throw "Release artifact verification failed" }

Write-Host "Release artifacts complete: $releaseRoot"
Write-Host "$hash  $archiveName"
