"""语音转写 —— faster-whisper 封装 + mock 跳过。

config.mock_transcribe=True 时返回占位转写稿，保证无 GPU/无模型时也能端到端验收。
真实模式默认 small 模型，缓存到 data/models。
"""

from app.config import settings
from app.core.paths import models_dir

_MOCK_TRANSCRIPT = (
    "大家好 呃 今天给大家分享一个我自己一直在用的小方法 就是那个 "
    "怎么说呢 就是很多人问我说 诶你这个效率为什么这么高 其实核心就一点 "
    "就是把重复的事情自动化 好 那我们直接进入正题 第一个点非常重要 "
    "就是你一定要先把流程理清楚 不要一上来就动手 最后记得点赞关注 我们下期见"
)

# 模块级缓存，避免每次任务重复加载模型
_model = None


def _load_model():
    global _model
    if _model is None:
        from faster_whisper import WhisperModel

        _model = WhisperModel(
            settings.whisper_model_size,
            device=settings.whisper_device,
            compute_type=settings.whisper_compute_type,
            download_root=str(models_dir()),
        )
    return _model


def transcribe(audio_path: str) -> str:
    """把音频转写为文字。mock 模式返回占位稿。"""
    if settings.mock_transcribe:
        return _MOCK_TRANSCRIPT

    model = _load_model()
    segments, _info = model.transcribe(audio_path, language="zh", beam_size=5)
    return "".join(seg.text for seg in segments).strip()
