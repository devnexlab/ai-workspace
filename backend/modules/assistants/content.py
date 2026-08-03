"""兼容旧 key=content：转发到运营管理助手。"""

from __future__ import annotations

# 保留文件以免旧 import 报错；真正实现见 operations.py
from .operations import OperationsAssistant, get_operations_board, run_operations_assistant  # noqa: F401
