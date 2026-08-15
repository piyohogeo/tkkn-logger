from pathlib import Path
import os
import sys

from PyInstaller.utils.hooks import collect_submodules


project_root = Path(SPECPATH).resolve().parent
source_root = project_root / "src"
template_root = project_root / "data" / "template"
ffmpeg_root = Path(os.environ.get("TOKKUN99_FFMPEG_ROOT", r"C:\tools\ffmpeg")).resolve()
ffmpeg_path = ffmpeg_root / "bin" / "ffmpeg.exe"

if not template_root.is_dir():
    raise SystemExit(f"Template directory not found: {template_root}")
if not ffmpeg_path.is_file():
    raise SystemExit(f"FFmpeg not found: {ffmpeg_path}")

hidden_imports = sorted(
    set(
        collect_submodules("mss")
        + collect_submodules("windows_capture")
        + ["pywintypes", "win32api"]
    )
)

runtime_binaries = [(str(ffmpeg_path), ".")]
conda_runtime = Path(sys.base_prefix) / "Library" / "bin"
for runtime_name in (
    "ffi.dll",
    "libbz2.dll",
    "liblzma.dll",
    "sqlite3.dll",
    "tcl86t.dll",
    "tk86t.dll",
):
    runtime_path = conda_runtime / runtime_name
    if runtime_path.is_file():
        runtime_binaries.append((str(runtime_path), "."))

a = Analysis(
    [str(project_root / "packaging" / "portable_entry.py")],
    pathex=[str(source_root)],
    binaries=runtime_binaries,
    datas=[(str(template_root), "template")],
    hiddenimports=hidden_imports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=["pytest"],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="Tokkun99Logger",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name="Tokkun99Logger",
)
