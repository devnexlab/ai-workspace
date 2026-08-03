"""助手基类：各业务助手继承并注册到 registry。"""

from __future__ import annotations


class BaseAssistant:
    """业务助手抽象。

    - key: 唯一标识，与 ai_agent.agent_type 对齐
    - events: 可声明监听的业务事件（文档/约定用途，真正触发由业务路由调用）
    """

    key: str = ''
    label: str = ''
    description: str = ''
    # 例: ('customer.create', 'customer.follow', 'manual')
    events: tuple = ()
    # True = 未在 Agent 中心建档时也默认启用
    default_enabled: bool = True
    # 是否提供看板
    has_board: bool = False

    def run(self, **context) -> dict:
        """执行一次助手任务。子类必须实现。"""
        raise NotImplementedError(f'{self.key} run() not implemented')

    def board(self, **params) -> dict | None:
        """可选：返回该助手的看板数据。"""
        return None
