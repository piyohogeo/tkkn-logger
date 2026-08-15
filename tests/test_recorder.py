from __future__ import annotations

import os
from pathlib import Path
import subprocess

import pytest

from tokkun99_logger.recorder import RunRecorder


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_FFMPEG_ROOT = (
    PROJECT_ROOT
    / "build"
    / "ffmpeg-lgpl"
    / "extracted"
    / "ffmpeg-n8.1.2-34-g9b6c8969e0-win64-lgpl-8.1"
    / "bin"
)
FFMPEG = Path(os.environ.get("TOKKUN99_TEST_FFMPEG", DEFAULT_FFMPEG_ROOT / "ffmpeg.exe"))
FFPROBE = Path(os.environ.get("TOKKUN99_TEST_FFPROBE", DEFAULT_FFMPEG_ROOT / "ffprobe.exe"))


@pytest.mark.skipif(not FFMPEG.is_file() or not FFPROBE.is_file(), reason="Local FFmpeg is unavailable")
def test_ffmpeg_recorder_writes_mpeg4_with_preroll(tmp_path) -> None:
    recorder = RunRecorder(
        ffmpeg_path=FFMPEG,
        width=320,
        height=240,
        fps=5,
        pre_roll_seconds=1,
    )
    previous_message = bytes([255, 255, 255]) * (320 * 240)
    red = bytes([0, 0, 255]) * (320 * 240)
    green = bytes([0, 255, 0]) * (320 * 240)
    for _ in range(2):
        recorder.observe(previous_message)
    recorder.clear_pre_roll()
    for _ in range(3):
        recorder.observe(red)
    output = tmp_path / "run.mp4"
    recorder.start(output)
    partial = tmp_path / "run.mp4.incomplete"
    assert recorder.partial_path == partial
    assert not output.exists()
    for _ in range(3):
        recorder.observe(green)

    finalized = recorder.finalize()

    assert finalized == output
    assert output.is_file() and output.stat().st_size > 0
    assert not partial.exists()
    probe = subprocess.run(
        [
            FFPROBE,
            "-v",
            "error",
            "-select_streams",
            "v:0",
            "-show_entries",
            "stream=codec_name,pix_fmt,width,height,avg_frame_rate,nb_frames",
            "-of",
            "default=noprint_wrappers=1",
            output,
        ],
        capture_output=True,
        text=True,
        check=True,
    )
    assert "codec_name=mpeg4" in probe.stdout
    assert "width=320" in probe.stdout
    assert "height=240" in probe.stdout
    assert "pix_fmt=yuv420p" in probe.stdout
    assert "avg_frame_rate=5/1" in probe.stdout
    assert "nb_frames=6" in probe.stdout


def test_recorder_builds_fixed_mpeg4_command(tmp_path) -> None:
    fake_ffmpeg = tmp_path / "ffmpeg.exe"
    fake_ffmpeg.touch()
    recorder = RunRecorder(ffmpeg_path=fake_ffmpeg, width=320, height=240, fps=30)

    command = recorder.build_command(tmp_path / "run.mp4.incomplete")

    assert command[command.index("-c:v") + 1] == "mpeg4"
    assert command[command.index("-q:v") + 1] == "1"
    assert command[command.index("-pix_fmt") + 1] == "yuv420p"
    assert command[command.index("-movflags") + 1] == "+faststart"
    assert command[command.index("-f", command.index("-i")) + 1] == "mp4"
    assert "libx264" not in command
    assert "-preset" not in command
    assert "-crf" not in command


def test_recorder_rejects_wrong_frame_size() -> None:
    if not FFMPEG.is_file():
        pytest.skip("Local FFmpeg is unavailable")
    recorder = RunRecorder(ffmpeg_path=FFMPEG, width=16, height=16, fps=5)

    with pytest.raises(ValueError, match="BGR bytes"):
        recorder.observe(b"too short")


@pytest.mark.skipif(not FFMPEG.is_file() or not FFPROBE.is_file(), reason="Local FFmpeg is unavailable")
def test_pause_keeps_process_open_and_resume_appends_frames(tmp_path) -> None:
    recorder = RunRecorder(
        ffmpeg_path=FFMPEG,
        width=16,
        height=16,
        fps=5,
        pre_roll_seconds=0,
    )
    frame = bytes([255, 255, 255]) * (16 * 16)
    output = tmp_path / "paused.mp4"
    recorder.start(output)
    recorder.observe(frame)
    recorder.pause()
    assert recorder.active is True
    assert recorder.paused is True
    for _ in range(20):
        recorder.observe(frame)
    assert recorder.frames_written == 1
    recorder.resume()
    recorder.observe(frame)
    recorder.finalize()

    probe = subprocess.run(
        [
            FFPROBE,
            "-v",
            "error",
            "-select_streams",
            "v:0",
            "-show_entries",
            "stream=nb_frames",
            "-of",
            "default=noprint_wrappers=1",
            output,
        ],
        capture_output=True,
        text=True,
        check=True,
    )
    assert "nb_frames=2" in probe.stdout


@pytest.mark.skipif(not FFMPEG.is_file() or not FFPROBE.is_file(), reason="Local FFmpeg is unavailable")
def test_append_hold_repeats_frame_without_waiting(tmp_path) -> None:
    recorder = RunRecorder(
        ffmpeg_path=FFMPEG,
        width=16,
        height=16,
        fps=5,
        pre_roll_seconds=0,
    )
    frame = bytes([255, 255, 255]) * (16 * 16)
    output = tmp_path / "message-hold.mp4"
    recorder.start(output)
    recorder.observe(frame)
    recorder.append_hold(frame, 2.0)
    recorder.finalize()

    probe = subprocess.run(
        [
            FFPROBE,
            "-v",
            "error",
            "-select_streams",
            "v:0",
            "-show_entries",
            "stream=nb_frames",
            "-of",
            "default=noprint_wrappers=1",
            output,
        ],
        capture_output=True,
        text=True,
        check=True,
    )
    assert "nb_frames=11" in probe.stdout
