"""股票情报：财经新闻 → 股市简报 → AI 分析总结（三者分开）。"""

from flask import Blueprint, request, jsonify

from modules import stock_news as sn

bp = Blueprint('stock_briefing', __name__)


def _serialize(row: dict | None) -> dict:
    if not row:
        return {}
    return {
        'brief_date': str(row.get('brief_date') or ''),
        'news': row.get('news') or [],
        'brief_md': row.get('brief_md') or '',
        'ai_analysis_md': row.get('ai_analysis_md') or '',
        'source_message': row.get('source_message') or '',
        'updated_at': str(row.get('updated_at') or '') if row.get('updated_at') else '',
        'message': row.get('message') or row.get('source_message') or '',
        'model': row.get('model'),
        'tokens': row.get('tokens'),
    }


@bp.route('/api/stock-news')
def list_stock_news():
    refresh = str(request.args.get('refresh', '')).lower() in ('1', 'true', 'yes')
    if refresh:
        row = sn.refresh_news_to_page()
        return jsonify({
            **_serialize(row),
            'list': row.get('news') or [],
            'total': len(row.get('news') or []),
            'ok': True,
        })
    row = sn.get_today_briefing()
    if not row:
        return jsonify({'list': [], 'total': 0, 'brief_date': sn._today(), 'message': '暂无数据，请先获取财经新闻'})
    news = row.get('news') or []
    return jsonify({
        **_serialize(row),
        'list': news,
        'total': len(news),
    })


@bp.route('/api/stock-news/refresh', methods=['POST'])
def refresh_stock_news():
    try:
        row = sn.refresh_news_to_page()
        return jsonify({
            **_serialize(row),
            'list': row.get('news') or [],
            'total': len(row.get('news') or []),
            'ok': True,
        })
    except Exception as e:
        return jsonify({'ok': False, 'error': str(e)}), 500


@bp.route('/api/stock-briefing/today', methods=['GET', 'POST'])
def stock_briefing_today():
    if request.method == 'GET':
        row = sn.get_today_briefing()
        if not row:
            return jsonify({
                'exists': False,
                'brief_date': sn._today(),
                'news': [],
                'brief_md': '',
                'ai_analysis_md': '',
            })
        return jsonify({'exists': True, **_serialize(row)})

    # POST：生成今日股市简报（与 AI 分析分开）
    data = request.get_json(silent=True) or {}
    force = bool(data.get('force', True))
    use_llm = data.get('use_llm', True)
    if isinstance(use_llm, str):
        use_llm = use_llm.lower() in ('1', 'true', 'yes')
    try:
        row = sn.build_stock_briefing(force=force, use_llm=bool(use_llm))
        return jsonify({'exists': True, 'ok': True, **_serialize(row)})
    except Exception as e:
        return jsonify({'ok': False, 'error': str(e)}), 500


@bp.route('/api/stock-briefing/build', methods=['POST'])
def stock_briefing_build():
    """生成今日股市简报。"""
    data = request.get_json(silent=True) or {}
    force = bool(data.get('force', True))
    use_llm = data.get('use_llm', True)
    if isinstance(use_llm, str):
        use_llm = use_llm.lower() in ('1', 'true', 'yes')
    try:
        row = sn.build_stock_briefing(force=force, use_llm=bool(use_llm))
        return jsonify({'ok': True, **_serialize(row)})
    except Exception as e:
        return jsonify({'ok': False, 'error': str(e)}), 500


@bp.route('/api/stock-briefing/analyze', methods=['POST'])
def stock_briefing_analyze():
    """AI 分析总结（独立于股市简报）。"""
    data = request.get_json(silent=True) or {}
    force = bool(data.get('force', True))
    try:
        row = sn.analyze_briefing(force=force)
        return jsonify({'ok': True, **_serialize(row)})
    except Exception as e:
        return jsonify({'ok': False, 'error': str(e)}), 500
