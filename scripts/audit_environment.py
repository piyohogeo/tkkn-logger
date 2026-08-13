"""Read-only environment audit for the Tokkun '99 logger.

This script deliberately performs no package installation or environment
mutation.  It invokes the selected Conda environment by absolute path and
writes a small, reproducible audit bundle under artifacts/env_audit.
"""

from __future__ import annotations

import argparse
import csv
import ctypes
from ctypes import wintypes
import importlib
import importlib.metadata
import json
import os
from pathlib import Path
import platform
import shutil
import site
import struct
import subprocess
import sys
from typing import Any, Iterable


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT = PROJECT_ROOT / "artifacts" / "env_audit"
DEFAULT_CONDA = Path.home() / "Anaconda3" / "Scripts" / "conda.exe"
DEFAULT_ENV_PREFIX = Path.home() / "Anaconda3" / "envs" / "py310_pt20"
TARGET_PROCESS = "tkkn.exe"


def run(command: Iterable[os.PathLike[str] | str], timeout: int = 120) -> dict[str, Any]:
    argv = [os.fspath(part) for part in command]
    try:
        completed = subprocess.run(
            argv,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
            check=False,
        )
        return {
            "command": argv,
            "returncode": completed.returncode,
            "stdout": completed.stdout,
            "stderr": completed.stderr,
        }
    except (OSError, subprocess.TimeoutExpired) as exc:
        return {"command": argv, "returncode": None, "stdout": "", "stderr": str(exc)}


def command_text(result: dict[str, Any]) -> str:
    command = subprocess.list2cmdline(result["command"])
    chunks = [f"> {command}", f"exit_code: {result['returncode']}"]
    if result["stdout"].strip():
        chunks.extend(["", result["stdout"].rstrip()])
    if result["stderr"].strip():
        chunks.extend(["", "[stderr]", result["stderr"].rstrip()])
    return "\n".join(chunks) + "\n"


def write_text(path: Path, text: str) -> None:
    path.write_text(text, encoding="utf-8", newline="\n")


def version_of(distribution_names: Iterable[str]) -> str | None:
    for name in distribution_names:
        try:
            return importlib.metadata.version(name)
        except importlib.metadata.PackageNotFoundError:
            continue
    return None


def probe_import(module: str, distributions: Iterable[str]) -> dict[str, Any]:
    result: dict[str, Any] = {
        "available": False,
        "module": module,
        "distribution_version": version_of(distributions),
    }
    try:
        imported = importlib.import_module(module)
        result["available"] = True
        result["module_version"] = getattr(imported, "__version__", None)
        result["module_path"] = getattr(imported, "__file__", None)
    except Exception as exc:  # Import failures are audit data, not fatal errors.
        result["error"] = f"{type(exc).__name__}: {exc}"
    return result


def query_processes() -> list[dict[str, Any]]:
    tasklist = run(["tasklist.exe", "/fo", "csv", "/nh"])
    if tasklist["returncode"] != 0:
        return []
    rows: list[dict[str, Any]] = []
    for row in csv.reader(tasklist["stdout"].splitlines()):
        if len(row) >= 2 and row[0].casefold() == TARGET_PROCESS.casefold():
            rows.append({"image_name": row[0], "pid": int(row[1])})
    return rows


def query_windows() -> list[dict[str, Any]]:
    if os.name != "nt":
        return []
    user32 = ctypes.windll.user32
    windows: list[dict[str, Any]] = []
    enum_proc_type = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)

    def callback(hwnd: int, _lparam: int) -> bool:
        length = user32.GetWindowTextLengthW(hwnd)
        if length <= 0:
            return True
        title_buffer = ctypes.create_unicode_buffer(length + 1)
        user32.GetWindowTextW(hwnd, title_buffer, length + 1)
        title = title_buffer.value
        pid = wintypes.DWORD()
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        rect = wintypes.RECT()
        client = wintypes.RECT()
        user32.GetWindowRect(hwnd, ctypes.byref(rect))
        user32.GetClientRect(hwnd, ctypes.byref(client))
        point = wintypes.POINT(client.left, client.top)
        user32.ClientToScreen(hwnd, ctypes.byref(point))
        item: dict[str, Any] = {
            "hwnd": int(hwnd),
            "pid": pid.value,
            "title": title,
            "visible": bool(user32.IsWindowVisible(hwnd)),
            "minimized": bool(user32.IsIconic(hwnd)),
            "window_rect": [rect.left, rect.top, rect.right, rect.bottom],
            "client_origin_screen": [point.x, point.y],
            "client_size": [client.right - client.left, client.bottom - client.top],
        }
        get_dpi = getattr(user32, "GetDpiForWindow", None)
        if get_dpi is not None:
            item["dpi"] = int(get_dpi(hwnd))
        windows.append(item)
        return True

    callback_ref = enum_proc_type(callback)
    if not user32.EnumWindows(callback_ref, 0):
        return []
    target_pids = {entry["pid"] for entry in query_processes()}
    return [
        entry
        for entry in windows
        if entry["pid"] in target_pids or "特訓" in entry["title"]
    ]


def query_monitors() -> list[dict[str, Any]]:
    if os.name != "nt":
        return []
    user32 = ctypes.windll.user32
    monitors: list[dict[str, Any]] = []

    class MonitorInfo(ctypes.Structure):
        _fields_ = [
            ("cbSize", wintypes.DWORD),
            ("rcMonitor", wintypes.RECT),
            ("rcWork", wintypes.RECT),
            ("dwFlags", wintypes.DWORD),
        ]

    callback_type = ctypes.WINFUNCTYPE(
        wintypes.BOOL, wintypes.HMONITOR, wintypes.HDC, ctypes.POINTER(wintypes.RECT), wintypes.LPARAM
    )

    def callback(hmonitor: int, _hdc: int, _rect: Any, _lparam: int) -> bool:
        info = MonitorInfo()
        info.cbSize = ctypes.sizeof(info)
        if user32.GetMonitorInfoW(hmonitor, ctypes.byref(info)):
            monitors.append(
                {
                    "rect": [info.rcMonitor.left, info.rcMonitor.top, info.rcMonitor.right, info.rcMonitor.bottom],
                    "work_rect": [info.rcWork.left, info.rcWork.top, info.rcWork.right, info.rcWork.bottom],
                    "primary": bool(info.dwFlags & 1),
                }
            )
        return True

    callback_ref = callback_type(callback)
    user32.EnumDisplayMonitors(0, None, callback_ref, 0)
    return monitors


def target_probe() -> dict[str, Any]:
    packages = {
        "opencv": probe_import("cv2", ["opencv-python", "opencv-contrib-python"]),
        "dxcam": probe_import("dxcam", ["dxcam"]),
        "mss": probe_import("mss", ["mss"]),
        "win32gui": probe_import("win32gui", ["pywin32"]),
        "win32process": probe_import("win32process", ["pywin32"]),
        "win32api": probe_import("win32api", ["pywin32"]),
        "numpy": probe_import("numpy", ["numpy"]),
        "pillow": probe_import("PIL", ["Pillow"]),
        "imagehash": probe_import("imagehash", ["ImageHash"]),
        "scipy": probe_import("scipy", ["scipy"]),
        "pydantic": probe_import("pydantic", ["pydantic"]),
    }
    return {
        "audit_mode": "read_only",
        "python": {
            "version": platform.python_version(),
            "executable": sys.executable,
            "implementation": platform.python_implementation(),
            "architecture_bits": struct.calcsize("P") * 8,
            "user_site_enabled": site.ENABLE_USER_SITE,
            "user_site_path": site.getusersitepackages(),
        },
        "system": {
            "platform": platform.platform(),
            "windows_version": platform.win32_ver(),
            "machine": platform.machine(),
        },
        "packages": packages,
        "target_process_name": TARGET_PROCESS,
        "target_processes": query_processes(),
        "target_windows": query_windows(),
        "monitors": query_monitors(),
    }


def find_ffmpeg(env_prefix: Path) -> tuple[Path | None, Path | None, list[str]]:
    search_dirs = [env_prefix / "Library" / "bin", env_prefix / "Scripts", env_prefix]
    notes: list[str] = []

    def locate(name: str) -> Path | None:
        path_value = shutil.which(name)
        if path_value:
            return Path(path_value)
        for directory in search_dirs:
            candidate = directory / f"{name}.exe"
            if candidate.is_file():
                notes.append(f"Found {name} outside PATH in selected Conda environment.")
                return candidate
        return None

    return locate("ffmpeg"), locate("ffprobe"), notes


def render_summary(probe: dict[str, Any], conda_ok: bool, ffmpeg: Path | None, ffprobe: Path | None) -> str:
    packages = probe.get("packages", {})

    def status(name: str) -> str:
        item = packages.get(name, {})
        if not item.get("available"):
            return "未導入"
        version = item.get("module_version") or item.get("distribution_version") or "版不明"
        return f"導入済み ({version})"

    capture_available = [name for name in ("dxcam", "mss") if packages.get(name, {}).get("available")]
    pywin32_available = all(packages.get(name, {}).get("available") for name in ("win32gui", "win32process", "win32api"))
    missing_core = [name for name in ("opencv", "numpy", "pillow") if not packages.get(name, {}).get("available")]
    env_root = str(Path(probe.get("python", {}).get("executable", ".")).parent).casefold()
    external_packages = [
        name
        for name, item in packages.items()
        if item.get("module_path") and not str(item["module_path"]).casefold().startswith(env_root)
    ]
    opencv_version_mismatch = (
        packages.get("opencv", {}).get("module_version")
        and packages.get("opencv", {}).get("distribution_version")
        and not str(packages["opencv"]["distribution_version"]).startswith(str(packages["opencv"]["module_version"]))
    )
    recommend_dedicated = bool(missing_core or not capture_available or not pywin32_available or external_packages or opencv_version_mismatch)
    recommendation = "専用環境 `tokkun99_logger` の新規作成" if recommend_dedicated else "既存 `py310_pt20` の流用候補"
    reasons: list[str] = []
    if missing_core:
        reasons.append("画像処理の基礎依存に不足があります: " + ", ".join(missing_core))
    if not capture_available:
        reasons.append("キャプチャ候補の `dxcam` / `mss` がどちらも見つかりません。")
    if not pywin32_available:
        reasons.append("対象ウィンドウ連携用の `pywin32` 一式が揃っていません。")
    if external_packages:
        reasons.append("ユーザー共通site-packagesから読み込まれる依存があります: " + ", ".join(external_packages))
    if opencv_version_mismatch:
        reasons.append("OpenCVの配布メタデータと実際に読み込まれるモジュールの版が食い違っています。")
    if not reasons:
        reasons.append("主要依存が既に揃っており、追加変更を小さくできる見込みです。")
    windows = probe.get("target_windows", [])
    window_note = "監査時に対象ウィンドウは見つかりませんでした。" if not windows else f"監査時に対象候補を {len(windows)} 件検出しました。"
    lines = [
        "# Phase 0 環境監査サマリー",
        "",
        "## 結論",
        "",
        f"推奨: **{recommendation}**",
        "",
        *[f"- {reason}" for reason in reasons],
        "",
        "この監査ではインストール、更新、アンインストール、Conda環境の書き換えを行っていません。",
        "",
        "## 対象環境",
        "",
        f"- Python: {probe.get('python', {}).get('version', '不明')} ({probe.get('python', {}).get('architecture_bits', '不明')} bit)",
        f"- 実行ファイル: `{probe.get('python', {}).get('executable', '不明')}`",
        f"- ユーザーsite-packages: {'有効' if probe.get('python', {}).get('user_site_enabled') else '無効'} (`{probe.get('python', {}).get('user_site_path', '不明')}`)",
        f"- Conda調査: {'成功' if conda_ok else '一部失敗（個別レポート参照）'}",
        f"- ffmpeg: `{ffmpeg}`" if ffmpeg else "- ffmpeg: 未検出",
        f"- ffprobe: `{ffprobe}`" if ffprobe else "- ffprobe: 未検出",
        "",
        "## 主要パッケージ",
        "",
        "| 用途 | 状態 |",
        "|---|---|",
        f"| OpenCV | {status('opencv')} |",
        f"| NumPy | {status('numpy')} |",
        f"| Pillow | {status('pillow')} |",
        f"| dxcam | {status('dxcam')} |",
        f"| mss | {status('mss')} |",
        f"| pywin32 / win32gui | {status('win32gui')} |",
        f"| ImageHash | {status('imagehash')} |",
        f"| SciPy | {status('scipy')} |",
        f"| Pydantic | {status('pydantic')} |",
        "",
        "## 実機観測",
        "",
        f"- {window_note}",
        f"- モニター数: {len(probe.get('monitors', []))}",
        "- この工程では実フレームのキャプチャ試験はまだ行っていません。Phase 1で候補方式を比較します。",
        "",
        "## 次の変更案（未実施）",
        "",
        "### A. `py310_pt20` を流用",
        "",
        "`mss` または `dxcam` を追加すれば開始できますが、OpenCVの重複とユーザーsite-packages混入を解消する必要があります。既存のPyTorch用途へ影響するため非推奨です。",
        "",
        "### B. 専用環境を作成（推奨）",
        "",
        "`environment.proposed.yml` のとおり、Python 3.10.18の `tokkun99_logger` を新規作成し、Phase 1に必要な NumPy 1.26.4、OpenCV 4.11.0.86、mss 10.2.0、pywin32 312、pytest 9.0.2 だけを導入します。ユーザーsite-packagesを無効にして起動し、既存FFmpegを利用します。`py310_pt20` とGPU対応PyTorchは変更しません。Pillow、ImageHash、dxcam等は実測で必要になるまで追加しません。",
        "",
        "## 生成物",
        "",
        "詳細は同じディレクトリの `conda_env_list.txt`、`py310_pt20_conda_list.txt`、`py310_pt20_pip_list.txt`、`ffmpeg_report.txt`、`capture_probe.json` を参照してください。",
        "",
    ]
    return "\n".join(lines)


def audit(output: Path, conda: Path, env_prefix: Path) -> int:
    output.mkdir(parents=True, exist_ok=True)
    python = env_prefix / "python.exe"
    if not python.is_file():
        raise SystemExit(f"Target Python not found: {python}")

    conda_results = {
        "version": run([conda, "--version"]),
        "info": run([conda, "info"]),
        "env_list": run([conda, "env", "list"]),
        "list": run([conda, "list", "--prefix", env_prefix]),
        "explicit": run([conda, "list", "--explicit", "--prefix", env_prefix]),
        "export": run([conda, "env", "export", "--prefix", env_prefix]),
    }
    write_text(output / "conda_env_list.txt", command_text(conda_results["version"]) + "\n" + command_text(conda_results["info"]) + "\n" + command_text(conda_results["env_list"]))
    write_text(output / "py310_pt20_conda_list.txt", command_text(conda_results["list"]))
    write_text(output / "py310_pt20_conda_explicit.txt", command_text(conda_results["explicit"]))
    write_text(output / "py310_pt20_environment.yml", conda_results["export"]["stdout"] or command_text(conda_results["export"]))

    python_report = run([python, "--version"])
    pip_version = run([python, "-m", "pip", "--version"])
    pip_list = run([python, "-m", "pip", "list", "--format=columns"])
    write_text(output / "py310_pt20_pip_list.txt", command_text(python_report) + "\n" + command_text(pip_version) + "\n" + command_text(pip_list))

    probe_result = run([python, Path(__file__).resolve(), "--target-probe-json"])
    if probe_result["returncode"] == 0:
        probe = json.loads(probe_result["stdout"])
    else:
        probe = {"probe_error": probe_result["stderr"], "packages": {}, "target_windows": [], "monitors": []}
    isolated_result = run([python, "-s", Path(__file__).resolve(), "--target-probe-json"])
    if isolated_result["returncode"] == 0:
        probe["without_user_site"] = json.loads(isolated_result["stdout"])
    else:
        probe["without_user_site"] = {"probe_error": isolated_result["stderr"]}
    write_text(output / "capture_probe.json", json.dumps(probe, ensure_ascii=False, indent=2) + "\n")

    ffmpeg, ffprobe, ffmpeg_notes = find_ffmpeg(env_prefix)
    ffmpeg_parts = ["Read-only FFmpeg discovery", "", *(ffmpeg_notes or ["No additional discovery notes."]), ""]
    for label, executable, arguments in (
        ("ffmpeg version", ffmpeg, ["-hide_banner", "-version"]),
        ("ffprobe version", ffprobe, ["-hide_banner", "-version"]),
        ("available H.264 encoders", ffmpeg, ["-hide_banner", "-encoders"]),
    ):
        ffmpeg_parts.append(f"## {label}")
        if executable is None:
            ffmpeg_parts.extend(["not found", ""])
            continue
        result = run([executable, *arguments])
        if label == "available H.264 encoders" and result["returncode"] == 0:
            result["stdout"] = "\n".join(line for line in result["stdout"].splitlines() if "264" in line.casefold()) + "\n"
        ffmpeg_parts.extend([command_text(result), ""])
    write_text(output / "ffmpeg_report.txt", "\n".join(ffmpeg_parts))

    conda_ok = all(result["returncode"] == 0 for result in conda_results.values())
    write_text(output / "summary.md", render_summary(probe, conda_ok, ffmpeg, ffprobe))
    print(f"Audit written to {output}")
    return 0


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--conda", type=Path, default=DEFAULT_CONDA)
    parser.add_argument("--env-prefix", type=Path, default=DEFAULT_ENV_PREFIX)
    parser.add_argument("--target-probe-json", action="store_true", help=argparse.SUPPRESS)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if args.target_probe_json:
        print(json.dumps(target_probe(), ensure_ascii=False))
        return 0
    if not args.conda.is_file():
        raise SystemExit(f"Conda executable not found: {args.conda}")
    return audit(args.output.resolve(), args.conda.resolve(), args.env_prefix.resolve())


if __name__ == "__main__":
    raise SystemExit(main())
