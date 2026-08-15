from __future__ import annotations

import threading

import pytest

from tokkun99_logger.app_paths import AppPaths
from tokkun99_logger.capture import TargetWindowUnavailable
from tokkun99_logger.config import LoggerConfig
from tokkun99_logger.logger_service import LoggerService


def service(tmp_path, events) -> LoggerService:
    return LoggerService(
        LoggerConfig(),
        AppPaths(tmp_path / "template", tmp_path / "data", tmp_path / "ffmpeg.exe"),
        events.append,
    )


def test_service_converts_worker_exception_to_structured_events(tmp_path, monkeypatch) -> None:
    events = []
    value = service(tmp_path, events)
    monkeypatch.setattr(value, "_execute", lambda: (_ for _ in ()).throw(ValueError("bad")))

    assert value.run() == 1
    assert [event.kind for event in events] == ["service_starting", "error", "service_stopped"]
    assert events[1].data["error_type"] == "ValueError"
    assert value.running is False


def test_auto_monitor_treats_target_loss_as_a_normal_stop(tmp_path, monkeypatch) -> None:
    events = []
    value = LoggerService(
        LoggerConfig(auto_monitor=True),
        AppPaths(tmp_path / "template", tmp_path / "data", tmp_path / "ffmpeg.exe"),
        events.append,
    )
    monkeypatch.setattr(
        value,
        "_execute",
        lambda: (_ for _ in ()).throw(TargetWindowUnavailable("closed")),
    )

    assert value.run() == 0
    assert [event.kind for event in events] == [
        "service_starting",
        "target_lost",
        "service_stopped",
    ]


def test_manual_monitor_reports_target_loss_as_an_error(tmp_path, monkeypatch) -> None:
    events = []
    value = service(tmp_path, events)
    monkeypatch.setattr(
        value,
        "_execute",
        lambda: (_ for _ in ()).throw(TargetWindowUnavailable("closed")),
    )

    assert value.run() == 1
    assert [event.kind for event in events] == [
        "service_starting",
        "error",
        "service_stopped",
    ]


def test_service_rejects_concurrent_run_and_accepts_stop_request(tmp_path, monkeypatch) -> None:
    entered = threading.Event()
    release = threading.Event()
    value = service(tmp_path, [])

    def blocking_execute() -> None:
        entered.set()
        release.wait(2)

    monkeypatch.setattr(value, "_execute", blocking_execute)
    worker = threading.Thread(target=value.run)
    worker.start()
    assert entered.wait(1)
    with pytest.raises(RuntimeError, match="already running"):
        value.run()
    value.request_stop()
    assert value.stop_event.is_set()
    release.set()
    worker.join(2)
    assert not worker.is_alive()


def test_stop_requested_before_run_releases_instance_lock(tmp_path, monkeypatch) -> None:
    events = []
    value = service(tmp_path, events)
    released = []

    class FakeLock:
        def __init__(self, _path) -> None:
            pass

        def acquire(self) -> None:
            pass

        def release(self) -> None:
            released.append(True)

    monkeypatch.setattr("tokkun99_logger.logger_service.InstanceLock", FakeLock)
    monkeypatch.setattr("tokkun99_logger.app_paths.AppPaths.validate", lambda _self: None)
    value.request_stop()

    assert value.run() == 0
    assert released == [True]
    assert events[-1].kind == "service_stopped"


def test_zero_duration_startup_closes_capture_and_lock(tmp_path, monkeypatch) -> None:
    events = []
    value = LoggerService(
        LoggerConfig(duration_seconds=0),
        AppPaths(tmp_path / "template", tmp_path / "data", tmp_path / "ffmpeg.exe"),
        events.append,
    )
    closed = []
    released = []

    class FakeLock:
        def __init__(self, _path) -> None:
            pass

        def acquire(self) -> None:
            pass

        def release(self) -> None:
            released.append(True)

    class FakeStorage:
        def __init__(self, *_args) -> None:
            pass

        def initialize(self) -> None:
            pass

    class FakeCapture:
        def close(self) -> None:
            closed.append(True)

    class FakeRecorder:
        active = False
        paused = False
        frames_written = 0

        def __init__(self, **_kwargs) -> None:
            pass

    class FakeWindow:
        hwnd = 1
        client_size = (320, 240)
        client_origin = (0, 0)

    monkeypatch.setattr("tokkun99_logger.app_paths.AppPaths.validate", lambda _self: None)
    monkeypatch.setattr("tokkun99_logger.logger_service.InstanceLock", FakeLock)
    monkeypatch.setattr("tokkun99_logger.logger_service.Storage", FakeStorage)
    monkeypatch.setattr(
        "tokkun99_logger.logger_service.recover_partial_videos",
        lambda _root: type("Recovery", (), {"recovered": ()})(),
    )
    monkeypatch.setattr("tokkun99_logger.logger_service.ensure_disk_capacity", lambda *_a, **_k: None)
    monkeypatch.setattr("tokkun99_logger.logger_service.ResultReader", lambda _path: object())
    monkeypatch.setattr("tokkun99_logger.logger_service.StateClassifier", lambda _path: object())
    monkeypatch.setattr("tokkun99_logger.logger_service.DebouncedStateDetector", lambda *_a, **_k: object())
    monkeypatch.setattr("tokkun99_logger.logger_service.RunRecorder", FakeRecorder)
    monkeypatch.setattr("tokkun99_logger.logger_service.locate_window", lambda: FakeWindow())
    monkeypatch.setattr("tokkun99_logger.logger_service.create_capture", lambda *_a: FakeCapture())

    assert value.run() == 0
    assert closed == [True]
    assert released == [True]
    assert "target_found" in [event.kind for event in events]
