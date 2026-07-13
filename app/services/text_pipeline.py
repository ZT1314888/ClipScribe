"""两步 LLM 文案处理流程（补充计划第 5 节）。

第一步 clean：基于转写稿生成清洗稿（去口水词、加标点、分段）。
第二步 analyze_and_rewrite：基于人工确认后的转写稿 + 清洗稿，
    生成简版结构拆解（开头钩子/核心卖点/节奏转折/结尾行动）
    与三类改写（口播稿/种草笔记文案/标题和开头钩子）。

mock 模式用模板占位，保证无 Key 也能端到端跑通。
"""

from app.services import llm

_CLEAN_SYSTEM = (
    "你是中文短视频文案编辑。把口语转写稿整理成通顺可读的文字："
    "去掉口水词与语气词，补全标点，合理分段，不改变原意，不新增事实。"
)

_ANALYZE_SYSTEM = (
    "你是短视频编导。基于给定文案做简版结构拆解，"
    "严格输出四部分：开头钩子、核心卖点、节奏转折、结尾行动，每部分一到两句。"
)

_REWRITE_SYSTEMS = {
    "oral": "你是口播稿撰稿人。把内容改写成适合出镜口播的稿子，口语化、有节奏。",
    "note": "你是种草博主。把内容改写成小红书风格种草笔记，有emoji和分点。",
    "title": "你是标题党克制版编导。产出3个标题和1个开头钩子，抓人但不夸大。",
}


def clean(transcript: str) -> str:
    """第一步：清洗稿。"""
    if llm.is_mock():
        paras = _mock_segment(transcript)
        return "【清洗稿（mock）】\n\n" + "\n\n".join(paras)
    return llm.complete(_CLEAN_SYSTEM, transcript)


def analyze(source_text: str) -> str:
    """第二步-a：结构拆解。source_text 优先传人工修订稿/清洗稿。"""
    if llm.is_mock():
        return (
            "【结构拆解（mock）】\n"
            "- 开头钩子：用一个高效率的反差问题抓住注意力。\n"
            "- 核心卖点：把重复工作自动化，效率翻倍。\n"
            "- 节奏转折：先理清流程再动手，避免返工。\n"
            "- 结尾行动：点赞关注，下期见。"
        )
    return llm.complete(_ANALYZE_SYSTEM, source_text)


def rewrite(source_text: str) -> dict[str, str]:
    """第二步-b：三类改写。返回 {oral, note, title}。"""
    if llm.is_mock():
        return {
            "oral": "【口播稿（mock）】大家好，今天分享一个提效小方法……（此处为占位）",
            "note": "【种草笔记（mock）】✨提效神器分享｜3步告别重复劳动\n1️⃣理清流程……",
            "title": "【标题与钩子（mock）】\n1. 我是这样把效率翻倍的\n"
            "2. 别再手动做这件事了\n3. 高手都在用的提效法\n钩子：你每天在重复浪费时间吗？",
        }
    return {
        key: llm.complete(system, source_text)
        for key, system in _REWRITE_SYSTEMS.items()
    }


def _mock_segment(transcript: str) -> list[str]:
    """把占位转写稿粗略分段，模拟清洗效果。"""
    words = transcript.replace(" 呃 ", "").replace(" 呃", "").split()
    text = "".join(words)
    # 简单按长度切两段
    mid = len(text) // 2
    return [text[:mid] + "。", text[mid:] + "。"]
