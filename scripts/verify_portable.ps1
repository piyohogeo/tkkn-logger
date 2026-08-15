param(
    [string]$AppRoot = ""
)

$ErrorActionPreference = "Stop"
$projectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
if ([string]::IsNullOrWhiteSpace($AppRoot)) {
    $AppRoot = Join-Path $projectRoot "dist\Tokkun99Logger"
}
$appRootResolved = (Resolve-Path -LiteralPath $AppRoot).Path
$executable = Join-Path $appRootResolved "Tokkun99Logger.exe"
$bundledFfmpeg = Join-Path $appRootResolved "_internal\ffmpeg.exe"
$ffmpegManifestPath = Join-Path $appRootResolved "LICENSES\FFmpeg-MANIFEST.json"
$dataRoot = Join-Path $appRootResolved "data"
$createdData = $false

if (Test-Path -LiteralPath $dataRoot) {
    throw "Verification requires a clean portable directory without data: $dataRoot"
}
foreach ($required in @(
    $executable,
    $bundledFfmpeg,
    (Join-Path $appRootResolved "_internal\template\states\v1\profile.json"),
    (Join-Path $appRootResolved "_internal\template\glyphs\v1\profile.json"),
    (Join-Path $appRootResolved "LICENSES\THIRD_PARTY_NOTICES.txt"),
    (Join-Path $appRootResolved "LICENSES\FFmpeg-LGPL-3.0-or-later.txt"),
    (Join-Path $appRootResolved "LICENSES\FFmpeg-BUILD.txt"),
    $ffmpegManifestPath,
    (Join-Path $appRootResolved "README.txt"),
    (Join-Path $appRootResolved "VERSION.txt")
)) {
    if (-not (Test-Path -LiteralPath $required -PathType Leaf)) {
        throw "Required portable file not found: $required"
    }
}

$ffmpegManifest = Get-Content -Raw -Encoding UTF8 -LiteralPath $ffmpegManifestPath | ConvertFrom-Json
$actualFfmpegHash = (Get-FileHash -Algorithm SHA256 -LiteralPath $bundledFfmpeg).Hash
if ($actualFfmpegHash -ne $ffmpegManifest.ffmpeg_sha256) {
    throw "Bundled ffmpeg.exe SHA-256 does not match its manifest: $actualFfmpegHash"
}
$ffmpegVersion = (& $bundledFfmpeg -hide_banner -version 2>&1 | Out-String)
if ($LASTEXITCODE -ne 0) { throw "Bundled ffmpeg.exe could not start" }
if ($ffmpegVersion -match "--enable-gpl" -or $ffmpegVersion -match "--enable-nonfree") {
    throw "Bundled FFmpeg contains a forbidden GPL or nonfree configuration"
}
if ($ffmpegVersion -notmatch "--arch=x86_64" -or $ffmpegVersion -notmatch "--enable-version3") {
    throw "Bundled FFmpeg is not the expected Windows x64 LGPL v3 build"
}
$mpeg4Help = (& $bundledFfmpeg -hide_banner -h encoder=mpeg4 2>&1 | Out-String)
if ($LASTEXITCODE -ne 0 -or $mpeg4Help -notmatch "Encoder mpeg4 \[MPEG-4 part 2\]") {
    throw "Bundled FFmpeg standard mpeg4 encoder is unavailable"
}

$savedPath = $env:PATH
$savedPythonHome = $env:PYTHONHOME
$savedPythonPath = $env:PYTHONPATH
$portableProcess = $null
$verificationFailure = $null
$shutdownFailure = $null
try {
    $env:PATH = "C:\Windows\System32;C:\Windows"
    Remove-Item Env:PYTHONHOME -ErrorAction SilentlyContinue
    Remove-Item Env:PYTHONPATH -ErrorAction SilentlyContinue

    $portableProcess = Start-Process -FilePath $executable -PassThru
    Start-Sleep -Seconds 4
    $portableProcess.Refresh()
    if ($portableProcess.HasExited) {
        throw "Portable GUI exited during startup with code $($portableProcess.ExitCode)"
    }
    if ($portableProcess.MainWindowTitle -notmatch "Logger$") {
        throw "Unexpected portable GUI title: $($portableProcess.MainWindowTitle)"
    }
    if (-not (Test-Path -LiteralPath (Join-Path $dataRoot "log\tokkun99-logger.log"))) {
        throw "Portable data/log was not created beside the executable"
    }
    $createdData = $true

}
catch {
    $verificationFailure = $_
}
finally {
    if ($null -ne $portableProcess) {
        try {
            $portableProcess.Refresh()
            if (-not $portableProcess.HasExited) {
                if (-not $portableProcess.CloseMainWindow()) {
                    throw "Could not request a safe GUI shutdown"
                }
                if (-not $portableProcess.WaitForExit(15000)) {
                    throw "Portable GUI did not finish its safe shutdown; process was left running"
                }
            }
        }
        catch {
            $shutdownFailure = $_
        }
    }
    $env:PATH = $savedPath
    if ($null -ne $savedPythonHome) { $env:PYTHONHOME = $savedPythonHome }
    if ($null -ne $savedPythonPath) { $env:PYTHONPATH = $savedPythonPath }
}

if ($null -ne $shutdownFailure) { throw $shutdownFailure }
if ($null -ne $verificationFailure) { throw $verificationFailure }

if ($createdData) {
    $resolvedData = (Resolve-Path -LiteralPath $dataRoot).Path
    $allowedPrefix = $appRootResolved.TrimEnd('\') + '\'
    if (-not $resolvedData.StartsWith($allowedPrefix, [StringComparison]::OrdinalIgnoreCase)) {
        throw "Refusing to remove test data outside the portable directory: $resolvedData"
    }
    Remove-Item -LiteralPath $resolvedData -Recurse -Force
}

Write-Host "Portable GUI verification passed without Python/Conda on PATH: $appRootResolved"
