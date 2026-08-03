"""兼容入口：请优先使用 modules.assistants。

本文件转发到多助手框架中的「客户管理助手」，避免旧 import 断裂。
"""

from modules.assistants.customer import (  # noqa: F401
    get_assistant_board,
    get_customer_board,
    run_customer_assistant,
)

__all__ = [
    'get_assistant_board',
    'get_customer_board',
    'run_customer_assistant',
]
