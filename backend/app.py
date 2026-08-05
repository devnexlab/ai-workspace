"""
AI Video Channel Auto-Operation System - Backend (Python/Flask)

入口仅负责：创建应用、注册路由、启动服务。
业务路由按功能模块分包，见 routes/。
基础设施配置见 config.py / .env。
"""

import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from flask import Flask, jsonify
from flask.json.provider import DefaultJSONProvider
from flask_cors import CORS
from datetime import date, datetime, time as dt_time

from config import FLASK_DEBUG, FLASK_HOST, FLASK_PORT, FLASK_THREADED, get_db
from database import init_db
from routes import register_blueprints


class LocalTimeJSONProvider(DefaultJSONProvider):
    """无时区 datetime 按北京墙钟输出，避免被标成 GMT 后前端再 +8 小时。"""

    def default(self, o):
        if isinstance(o, datetime):
            return o.strftime('%Y-%m-%d %H:%M:%S')
        if isinstance(o, date):
            return o.strftime('%Y-%m-%d')
        if isinstance(o, dt_time):
            return o.strftime('%H:%M:%S')
        return super().default(o)


def create_app():
    app = Flask(__name__)
    app.json = LocalTimeJSONProvider(app)
    CORS(app)
    register_blueprints(app)

    @app.route('/api/health')
    def health():
        return jsonify({'status': 'ok', 'ts': int(time.time() * 1000)})

    @app.errorhandler(404)
    def not_found(e):
        return jsonify({'error': 'not found'}), 404

    @app.errorhandler(500)
    def server_error(e):
        return jsonify({'error': str(e)}), 500

    # 挂在 create_app：debug reloader 子进程也会走到这里
    try:
        from modules.content_ops.scheduler import start_daily_scheduler
        start_daily_scheduler()
    except Exception as e:
        print(f'[Server] Daily scheduler not started: {e}')

    try:
        from modules.stock_watchlist_scheduler import start_watchlist_scheduler
        start_watchlist_scheduler()
    except Exception as e:
        print(f'[Server] Watchlist scheduler not started: {e}')
    try:
        from modules.stock_universe import start_universe_scheduler
        start_universe_scheduler()
    except Exception as e:
        print(f'[Server] Universe scheduler not started: {e}')

    return app


def _reset_stuck_tasks():
    """服务器重启后，把仍标记为 processing/running 的任务重置为 failed。"""
    try:
        conn = get_db()
        # 注意：必须包含 subtitle_status，否则一键全流程中断后字幕会永久卡在 processing
        conn.execute(
            "UPDATE video_task SET "
            "voice_status=CASE WHEN voice_status='processing' THEN 'failed' ELSE voice_status END, "
            "subtitle_status=CASE WHEN subtitle_status='processing' THEN 'failed' ELSE subtitle_status END, "
            "video_status=CASE WHEN video_status='processing' THEN 'failed' ELSE video_status END, "
            "export_status=CASE WHEN export_status='processing' THEN 'failed' ELSE export_status END, "
            "error_msg='服务器重启导致任务中断，请重新执行' "
            "WHERE voice_status='processing' OR subtitle_status='processing' "
            "OR video_status='processing' OR export_status='processing'"
        )
        changes = conn.total_changes
        # 股票筛选后台线程会随重启一起死掉，DB 里不能继续挂 running
        conn.execute(
            "UPDATE stock_screening SET status='failed', "
            "message=COALESCE(NULLIF(message,''), '扫描中断') || '（服务器重启，任务已中断，请重新筛选）' "
            "WHERE status IN ('running', 'pending')"
        )
        conn.commit()
        conn.close()
        if changes:
            print(f'[Server] Reset {changes} stuck processing tasks to failed')
        print('[Server] Cleared stuck stock screening jobs')
    except Exception as e:
        print(f'[Server] Warning: could not reset stuck tasks: {e}')


app = create_app()


if __name__ == '__main__':
    init_db()
    _reset_stuck_tasks()
    print(f'[Server] Starting on http://localhost:{FLASK_PORT}')
    app.run(
        host=FLASK_HOST,
        port=FLASK_PORT,
        debug=FLASK_DEBUG,
        threaded=FLASK_THREADED,
    )
