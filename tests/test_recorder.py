from __future__ import annotations

from pathlib import Path
import shutil
import subprocess

import pytest

from tokkun99_logger.recorder import RunRecorder


FFMPEG = Path(r"C:\tools\ffmpeg\bin\ffmpeg.exe")
FFPROBE = Path(r"C:\tools\ffmpeg\bin\ffprobe.exe")


@pytest.mark.skipif(not FFMPEG.is_file() or not FFPROBE.is_file(), reason="Local FFmpeg is unavailable")
def test_ffmpeg_recorder_writes_h264_with_preroll(tmp_path) -> None:
    recorder = RunRecorder(
        ffmpeg_path=FFMPEG,
        width=16,
        height=16,
        fps=5,
        pre_roll_seconds=1,
    )
    red = bytes([0, 0, 255]) * (16 * 16)
    green = bytes([0, 255, 0]) * (16 * 16)
    for _ in range(3):
        recorder.observe(red)
    output = tmp_path / "run.mp4"
    recorder.start(output)
    for _ in range(3):
        recorder.observe(green)

    finalized = recorder.finalize()

    assert finalized == output
    assert output.is_file() and output.stat().st_size > 0
    assert not (tmp_path / "run.partial.mp4").exists()
    probe = subprocess.run(
        [
            FFPROBE,
            "-v",
            "error",
            "-select_streams",
            "v:0",
            "-show_entries",
            "stream=codec_name,nb_frames",
            "-of",
            "default=noprint_wrappers=1",
            output,
        ],
        capture_output=True,
        text=True,
        check=True,
    )
    assert "codec_name=h264" in probe.stdout
    assert "nb_frames=6" in probe.stdout


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
