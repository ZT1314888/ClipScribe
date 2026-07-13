"""音频抽取/归一化 —— 用系统 ffmpeg。

把上传的视频/音频归一化为 wav / 单声道 / 16k，供 faster-whisper 使用。
若上传的本身就是音频，仍走一遍 ffmpeg 归一化，保证格式一致。
"""

import shutil
import subprocess
from pathlib import Path

from app.core.paths import task_media_paths


class AudioExtractionError(RuntimeError):
    pass


def ffmpeg_available() -> bool:
    return shutil.which("ffmpeg") is not None


def extract_audio(task_id: str, source_path: str) -> str:
    """把 source_path 归一化为 16k 单声道 wav，返回音频文件路径。"""
    if not ffmpeg_available():
        raise AudioExtractionError(
            "未找到 ffmpeg，无法抽取音频。请安装 ffmpeg，或直接上传已抽好的音频。"
        )

    _media_dir, audio_dir = task_media_paths(task_id)
    out_path = audio_dir / "audio.wav"

    cmd = [
        "ffmpeg",
        "-y",
        "-i",
        str(source_path),
        "-vn",
        "-ac",
        "1",
        "-ar",
        "16000",
        "-f",
        "wav",
        str(out_path),
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0 or not out_path.exists():
        tail = (proc.stderr or proc.stdout or "").strip()[-500:]
        raise AudioExtractionError(f"ffmpeg 抽音频失败：{tail}")
    return str(out_path)


def guess_is_media(filename: str) -> bool:
    ext = Path(filename).suffix.lower()
    return ext in {
        ".mp3",
        ".mp4",
        ".m4a",
        ".wav",
        ".webm",
        ".mkv",
        ".ogg",
        ".flac",
        ".mov",
        ".avi",
    }
