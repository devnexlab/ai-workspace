"""
路由模块注册中心。

按功能域分包：
  system    - 总览、系统设置、健康检查
  content   - 爆款采集、文案、素材
  video     - 视频生产
  publish   - 发布
  crm       - 客户与跟进
  knowledge - AI 知识库
  stocks    - 股票研究
  agents    - Agent 与工作流
"""

from .system.dashboard import bp as dashboard_bp
from .system.settings import bp as settings_bp
from .system.platforms import bp as platforms_bp
from .system.wechat_oa import bp as wechat_oa_bp
from .content.hot_topics import bp as hot_topics_bp
from .content.scripts import bp as scripts_bp
from .content.materials import bp as materials_bp
from .video.videos import bp as videos_bp
from .publish.publish import bp as publish_bp
from .crm.customers import bp as customers_bp
from .crm.follows import bp as follows_bp
from .crm.leads import bp as leads_bp
from .knowledge.knowledge import bp as knowledge_bp
from .stocks.stocks import bp as stocks_bp
from .stocks.stock_briefing import bp as stock_briefing_bp
from .agents.agents import bp as agents_bp
from .agents.workflows import bp as workflows_bp

ALL_BLUEPRINTS = [
    dashboard_bp,
    settings_bp,
    platforms_bp,
    wechat_oa_bp,
    hot_topics_bp,
    scripts_bp,
    materials_bp,
    videos_bp,
    publish_bp,
    customers_bp,
    follows_bp,
    leads_bp,
    knowledge_bp,
    stocks_bp,
    stock_briefing_bp,
    agents_bp,
    workflows_bp,
]


def register_blueprints(app):
    for bp in ALL_BLUEPRINTS:
        app.register_blueprint(bp)
