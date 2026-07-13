"""OpenAI-compatible LLM 客户端封装 + mock 跳过。

清洗/结构拆解/改写共用。config.mock_llm=True 时不发网络请求，
由调用方（text_pipeline）用模板生成占位输出。
"""

from app.config import settings


class LLMError(RuntimeError):
    pass


_client = None


def _get_client():
    global _client
    if _client is None:
        from openai import OpenAI

        if not settings.llm_api_key:
            raise LLMError("未配置 LLM_API_KEY，且未开启 mock 模式。")
        _client = OpenAI(base_url=settings.llm_base_url, api_key=settings.llm_api_key)
    return _client


def is_mock() -> bool:
    return settings.mock_llm


def complete(system_prompt: str, user_prompt: str) -> str:
    """单轮补全。调用方需自行处理 mock（is_mock 为 True 时不应调用本函数）。"""
    client = _get_client()
    try:
        resp = client.chat.completions.create(
            model=settings.llm_model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            temperature=0.7,
        )
    except Exception as e:  # noqa: BLE001  网络/额度等运行期错误统一上抛
        raise LLMError(f"LLM 调用失败：{e}") from e
    return (resp.choices[0].message.content or "").strip()
