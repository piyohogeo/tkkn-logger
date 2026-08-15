"""Minimal Tkinter/ttk front end for the logger service."""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass, replace
import logging
import os
from pathlib import Path
import queue
import threading
import tkinter as tk
from tkinter import messagebox, ttk

from .app_paths import AppPaths
from .config import LoggerConfig
from .dashboard import DashboardStats, load_dashboard
from .logger_events import LoggerEvent
from .logger_service import LoggerService
from .storage import Storage


LOGGER = logging.getLogger(__name__)


@dataclass(frozen=True)
class GuiState:
    service_state: str = "停止中"
    game_detection: str = "未検出"
    game_state: str = "UNKNOWN"
    recording_state: str = "待機"
    recording_seconds: float = 0.0
    last_error: str = ""


def apply_event(state: GuiState, event: LoggerEvent) -> GuiState:
    data = event.data
    if event.kind == "service_starting":
        return replace(state, service_state="開始中", last_error="")
    if event.kind == "target_found":
        width, height = data.get("target_size", (320, 240))
        return replace(state, game_detection=f"検出済み / {width}x{height}")
    if event.kind == "service_started":
        return replace(state, service_state="監視中")
    if event.kind == "state_changed":
        return replace(state, game_state=str(data.get("game_state", "UNKNOWN")))
    if event.kind == "recording_started":
        return replace(state, recording_state="録画中", recording_seconds=0.0)
    if event.kind == "recording_paused":
        return replace(state, recording_state="一時停止")
    if event.kind == "recording_resumed":
        return replace(state, recording_state="録画中")
    if event.kind == "recording_finished":
        return replace(state, recording_state="待機", recording_seconds=0.0)
    if event.kind == "service_status":
        recording = bool(data.get("recording"))
        paused = bool(data.get("recording_paused"))
        return replace(
            state,
            game_state=str(data.get("game_state", state.game_state)),
            recording_state="一時停止" if paused else ("録画中" if recording else "待機"),
            recording_seconds=float(data.get("recording_seconds", 0.0)),
        )
    if event.kind == "error":
        return replace(state, service_state="エラー", last_error=event.message)
    if event.kind == "service_stopped":
        return replace(
            state,
            service_state="停止中",
            game_detection="未検出",
            game_state="UNKNOWN",
            recording_state="待機",
            recording_seconds=0.0,
        )
    return state


def ensure_data_directory(paths: AppPaths) -> Path:
    target = paths.data_root.resolve()
    target.mkdir(parents=True, exist_ok=True)
    return target


class LoggerGui:
    def __init__(self, root: tk.Tk, paths: AppPaths) -> None:
        self.root = root
        self.paths = paths
        self.events: queue.Queue[LoggerEvent] = queue.Queue()
        self.service: LoggerService | None = None
        self.worker: threading.Thread | None = None
        self.closing = False
        self.state = GuiState()
        self.recent_messages: deque[str] = deque(maxlen=8)

        root.title("特訓'99 Logger")
        root.resizable(False, False)
        root.protocol("WM_DELETE_WINDOW", self.close)
        root.report_callback_exception = self._report_callback_exception
        self._build()
        self._refresh_stats()
        self._render_state()
        root.after(100, self._poll_events)

    def _build(self) -> None:
        frame = ttk.Frame(self.root, padding=14)
        frame.grid(sticky="nsew")
        frame.columnconfigure(1, weight=1)

        self.game_var = tk.StringVar()
        self.state_var = tk.StringVar()
        self.recording_var = tk.StringVar()
        self.survival_var = tk.StringVar(value="—")
        self.bullets_var = tk.StringVar(value="—")
        self.messages_var = tk.StringVar(value="0種類 / 確認済み0種類")
        self.runs_var = tk.StringVar(value="run: 0 / 要レビュー: 0")
        self.status_var = tk.StringVar(value="停止中")
        self.mode_var = tk.StringVar(value="records_only")
        self.capture_var = tk.StringVar(value="wgc")

        rows = (
            ("ゲーム", self.game_var),
            ("状態", self.state_var),
            ("録画", self.recording_var),
            ("生存時間記録", self.survival_var),
            ("弾数記録", self.bullets_var),
            ("メッセージ", self.messages_var),
            ("集計", self.runs_var),
        )
        for row, (label, variable) in enumerate(rows):
            ttk.Label(frame, text=f"{label}:").grid(row=row, column=0, sticky="w", pady=2)
            ttk.Label(frame, textvariable=variable, width=42).grid(
                row=row, column=1, columnspan=2, sticky="w", pady=2
            )

        ttk.Separator(frame).grid(row=7, column=0, columnspan=3, sticky="ew", pady=10)
        ttk.Label(frame, text="保持モード:").grid(row=8, column=0, sticky="w")
        self.mode_combo = ttk.Combobox(
            frame,
            textvariable=self.mode_var,
            values=("records_only", "collect_samples", "collect_all"),
            state="readonly",
            width=20,
        )
        self.mode_combo.grid(row=8, column=1, sticky="w")
        ttk.Label(frame, text="キャプチャ:").grid(row=9, column=0, sticky="w", pady=4)
        self.capture_combo = ttk.Combobox(
            frame,
            textvariable=self.capture_var,
            values=("wgc", "mss"),
            state="readonly",
            width=20,
        )
        self.capture_combo.grid(row=9, column=1, sticky="w", pady=4)
        ttk.Label(frame, text="WGCが既定 / MSSは代替").grid(row=9, column=2, sticky="w")

        buttons = ttk.Frame(frame)
        buttons.grid(row=10, column=0, columnspan=3, sticky="w", pady=(10, 6))
        self.start_button = ttk.Button(buttons, text="監視開始", command=self.start)
        self.stop_button = ttk.Button(buttons, text="停止", command=self.stop)
        self.open_button = ttk.Button(buttons, text="データを開く", command=self.open_data)
        self.start_button.grid(row=0, column=0, padx=(0, 6))
        self.stop_button.grid(row=0, column=1, padx=6)
        self.open_button.grid(row=0, column=2, padx=6)

        ttk.Label(frame, textvariable=self.status_var, wraplength=470).grid(
            row=11, column=0, columnspan=3, sticky="w", pady=(4, 4)
        )
        self.log = tk.Text(frame, width=68, height=8, state="disabled", wrap="word")
        self.log.grid(row=12, column=0, columnspan=3, sticky="ew")

    def start(self) -> None:
        if self.worker is not None and self.worker.is_alive():
            return
        try:
            config = LoggerConfig(
                capture_backend=self.capture_var.get(),  # type: ignore[arg-type]
                retention_mode=self.mode_var.get(),  # type: ignore[arg-type]
            )
        except ValueError as exc:
            messagebox.showerror("設定エラー", str(exc), parent=self.root)
            return
        self.service = LoggerService(config, self.paths, self.events.put)
        self.worker = threading.Thread(target=self.service.run, name="tokkun99-logger", daemon=False)
        self.worker.start()
        self.start_button.configure(state="disabled")
        self.stop_button.configure(state="normal")
        self.mode_combo.configure(state="disabled")
        self.capture_combo.configure(state="disabled")

    def stop(self) -> None:
        if self.service is None or self.worker is None or not self.worker.is_alive():
            return
        self.service.request_stop()
        self.state = replace(self.state, service_state="停止処理中…")
        self.status_var.set("停止処理中…録画とデータを安全に確定しています")
        self.stop_button.configure(state="disabled")

    def open_data(self) -> None:
        try:
            target = ensure_data_directory(self.paths)
            if os.name != "nt":
                raise OSError("データフォルダ表示はWindows専用です")
            os.startfile(target)  # type: ignore[attr-defined]
        except OSError as exc:
            messagebox.showerror("フォルダを開けません", str(exc), parent=self.root)

    def _report_callback_exception(self, exception_type, exception, traceback) -> None:
        LOGGER.error(
            "Tkinter callback failed",
            exc_info=(exception_type, exception, traceback),
        )
        messagebox.showerror(
            "GUIエラー", f"{exception_type.__name__}: {exception}", parent=self.root
        )

    def close(self) -> None:
        if self.worker is not None and self.worker.is_alive():
            self.closing = True
            self.stop()
            self.start_button.configure(state="disabled")
            self.open_button.configure(state="disabled")
            return
        self.root.destroy()

    def _poll_events(self) -> None:
        while True:
            try:
                event = self.events.get_nowait()
            except queue.Empty:
                break
            self.state = apply_event(self.state, event)
            if event.kind != "service_status":
                self.recent_messages.append(f"{event.timestamp[11:19]} {event.message}")
                self._render_log()
            if event.kind.startswith("run_"):
                self._refresh_stats()
            if event.kind == "error":
                messagebox.showerror("ロガーエラー", event.message, parent=self.root)
            if event.kind == "service_stopped":
                self._set_stopped_controls()
                if self.closing:
                    self.root.destroy()
                    return
            self._render_state()
        self.root.after(100, self._poll_events)

    def _set_stopped_controls(self) -> None:
        self.start_button.configure(state="normal")
        self.stop_button.configure(state="disabled")
        self.open_button.configure(state="normal")
        self.mode_combo.configure(state="readonly")
        self.capture_combo.configure(state="readonly")

    def _render_state(self) -> None:
        self.game_var.set(self.state.game_detection)
        self.state_var.set(self.state.game_state)
        marker = "● " if self.state.recording_state == "録画中" else ""
        minutes, seconds = divmod(round(self.state.recording_seconds), 60)
        self.recording_var.set(
            f"{marker}{self.state.recording_state} {minutes:02d}:{seconds:02d}"
        )
        self.status_var.set(self.state.last_error or self.state.service_state)
        if self.state.service_state == "停止中" and not self.closing:
            self._set_stopped_controls()

    def _render_log(self) -> None:
        self.log.configure(state="normal")
        self.log.delete("1.0", "end")
        self.log.insert("end", "\n".join(self.recent_messages))
        self.log.configure(state="disabled")

    def _refresh_stats(self) -> None:
        try:
            storage = Storage(self.paths.layout.database, self.paths.data_root)
            stats = load_dashboard(storage)
        except Exception as exc:
            self.status_var.set(f"統計を読み込めません: {exc}")
            return
        self._render_stats(stats)

    def _render_stats(self, stats: DashboardStats) -> None:
        self.survival_var.set(
            f"{stats.survival_record.value / 1000:.3f}秒"
            if stats.survival_record
            else "記録なし"
        )
        self.bullets_var.set(
            f"{stats.bullet_record.value}発" if stats.bullet_record else "記録なし"
        )
        self.messages_var.set(
            f"{stats.message_clusters}種類 / 確認済み{stats.verified_messages}種類"
        )
        self.runs_var.set(
            f"{stats.total_runs} / 完了{stats.complete_runs} / 要レビュー{stats.needs_review_runs}"
        )


def run_gui(paths: AppPaths) -> None:
    root = tk.Tk()
    LoggerGui(root, paths)
    root.mainloop()
