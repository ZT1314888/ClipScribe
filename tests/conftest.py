"""pytest 全局夹具：把数据目录指向临时目录，避免污染真实 data/。"""

import pytest

from app.config import settings


@pytest.fixture(autouse=True)
def _tmp_data_dir(tmp_path, monkeypatch):
    """每个测试用独立临时 data 目录（settings 是单例，直接改字段）。"""
    monkeypatch.setattr(settings, "data_dir", tmp_path)
    yield
