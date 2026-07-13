"""统一时间工具：全仓使用 naive UTC。

SQLite 不持久化 tzinfo，从库读回的 datetime 是 naive 的。若代码里混用
aware（datetime.now(timezone.utc)）与库读回的 naive 值做运算/比较，会报
"can't subtract offset-naive and offset-aware datetimes"。因此统一用 naive UTC。
"""

from datetime import datetime, timezone


def utcnow() -> datetime:
    """当前 UTC 时间，naive（不带 tzinfo），与 SQLite 读回值一致。"""
    return datetime.now(timezone.utc).replace(tzinfo=None)
