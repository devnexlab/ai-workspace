"""Stock Research System routes - watchlist, screening, strategies (V1.2 new module)."""

from flask import Blueprint, request, jsonify
from config import get_db as _db
import json

bp = Blueprint('stocks', __name__)


# ---- Watchlist Management ----

@bp.route('/api/stocks/watchlist')
def list_watchlist():
    conn = _db()
    list_type = request.args.get('type', '')
    where = 'WHERE list_type=%s' if list_type else ''
    params = [list_type] if list_type else []

    rows = conn.execute(
        f'SELECT * FROM stock_watchlist {where} ORDER BY added_at DESC', params
    ).fetchall()
    conn.close()
    return jsonify({'list': [dict(r) for r in rows]})


@bp.route('/api/stocks/watchlist', methods=['POST'])
def add_to_watchlist():
    data = request.get_json(silent=True) or {}
    conn = _db()
    cur = conn.execute(
        '''INSERT INTO stock_watchlist
           (stock_code, stock_name, list_type, buy_price, quantity, notes)
           VALUES (%s, %s, %s, %s, %s, %s)''',
        (data.get('stock_code', ''), data.get('stock_name', ''),
         data.get('list_type', 'watch'), data.get('buy_price', 0),
         data.get('quantity', 0), data.get('notes', ''))
    )
    new_id = cur.lastrowid
    conn.commit()
    conn.close()
    return jsonify({'id': new_id, 'message': '已添加到自选股'})


@bp.route('/api/stocks/watchlist/<int:id>', methods=['PUT'])
def update_watchlist(id):
    data = request.get_json(silent=True) or {}
    conn = _db()
    fields = []
    params = []
    for k in ['stock_code', 'stock_name', 'list_type', 'buy_price', 'current_price', 'quantity', 'notes']:
        if k in data:
            fields.append(f'{k}=%s')
            params.append(data[k])
    if fields:
        params.append(id)
        conn.execute(f'UPDATE stock_watchlist SET {",".join(fields)} WHERE id=%s', params)
        conn.commit()
    conn.close()
    return jsonify({'message': '已更新'})


@bp.route('/api/stocks/watchlist/<int:id>', methods=['DELETE'])
def delete_from_watchlist(id):
    conn = _db()
    conn.execute('DELETE FROM stock_watchlist WHERE id=%s', (id,))
    conn.commit()
    conn.close()
    return jsonify({'message': '已删除'})


# ---- Technical Indicators ----

@bp.route('/api/stocks/indicators')
def get_indicators():
    """Get technical indicators for a stock (MACD, KDJ, RSI, MA, BOLL)."""
    code = request.args.get('code', '')
    if not code:
        return jsonify({'error': 'stock code required'}), 400

    # Return indicator configuration (real data would require market data API)
    indicators = {
        'code': code,
        'indicators': {
            'MACD': {'DIF': 0, 'DEA': 0, 'MACD': 0, 'signal': '待计算'},
            'KDJ': {'K': 0, 'D': 0, 'J': 0, 'signal': '待计算'},
            'RSI': {'RSI6': 0, 'RSI12': 0, 'RSI24': 0, 'signal': '待计算'},
            'MA': {'MA5': 0, 'MA10': 0, 'MA20': 0, 'MA60': 0, 'signal': '待计算'},
            'BOLL': {'UP': 0, 'MID': 0, 'LOW': 0, 'signal': '待计算'},
            'VOLUME': {'signal': '待计算'},
            'TREND': {'signal': '待计算'},
        },
        'note': '接入行情数据源后可显示实时技术指标。推荐接入 Tushare、AKShare 等免费数据源。'
    }
    return jsonify(indicators)


# ---- Screening ----

@bp.route('/api/stocks/screening', methods=['POST'])
def run_screening():
    """Run stock screening based on user-defined conditions."""
    data = request.get_json(silent=True) or {}
    conditions = data.get('conditions', [])

    # Store the screening request
    conn = _db()
    cur = conn.execute(
        '''INSERT INTO stock_screening (name, conditions_json, results_json, status)
           VALUES (%s, %s, %s, 'completed')''',
        (data.get('name', '条件筛选'),
         json.dumps(conditions, ensure_ascii=False),
         json.dumps([], ensure_ascii=False))
    )
    new_id = cur.lastrowid
    conn.commit()
    conn.close()

    # Return available condition types for the frontend
    available_conditions = [
        {'key': 'macd_golden_cross', 'label': 'MACD金叉', 'type': 'indicator'},
        {'key': 'ma_bullish', 'label': '均线多头排列', 'type': 'indicator'},
        {'key': 'volume_increase', 'label': '成交量放大', 'type': 'volume'},
        {'key': 'breakthrough', 'label': '突破平台', 'type': 'trend'},
        {'key': 'rsi_low', 'label': 'RSI低位', 'type': 'indicator'},
        {'key': 'boll_lower', 'label': '触及布林下轨', 'type': 'indicator'},
        {'key': 'pullback_support', 'label': '回踩支撑位', 'type': 'trend'},
        {'key': 'kdj_golden_cross', 'label': 'KDJ金叉', 'type': 'indicator'},
    ]

    return jsonify({
        'id': new_id,
        'conditions': conditions,
        'available': available_conditions,
        'results': [],
        'message': '筛选条件已保存。接入行情数据源后可返回实际结果。'
    })


@bp.route('/api/stocks/screening/history')
def screening_history():
    conn = _db()
    rows = conn.execute(
        'SELECT * FROM stock_screening ORDER BY created_at DESC LIMIT 20'
    ).fetchall()
    conn.close()
    return jsonify({'list': [dict(r) for r in rows]})


# ---- AI Strategies ----

@bp.route('/api/stocks/strategies')
def list_strategies():
    conn = _db()
    rows = conn.execute(
        'SELECT * FROM stock_strategy ORDER BY created_at DESC'
    ).fetchall()
    conn.close()
    return jsonify({'list': [dict(r) for r in rows]})


@bp.route('/api/stocks/strategies', methods=['POST'])
def create_strategy():
    data = request.get_json(silent=True) or {}
    conn = _db()
    cur = conn.execute(
        '''INSERT INTO stock_strategy
           (name, description, strategy_type, rules_json, status)
           VALUES (%s, %s, %s, %s, 'active')''',
        (data.get('name', ''), data.get('description', ''),
         data.get('strategy_type', 'trend'),
         json.dumps(data.get('rules', {}), ensure_ascii=False))
    )
    new_id = cur.lastrowid
    conn.commit()
    conn.close()
    return jsonify({'id': new_id, 'message': '策略已创建'})


@bp.route('/api/stocks/strategies/<int:id>', methods=['PUT'])
def update_strategy(id):
    data = request.get_json(silent=True) or {}
    conn = _db()
    fields = []
    params = []
    for k in ['name', 'description', 'strategy_type', 'rules_json', 'score', 'hit_rate', 'total_trades', 'winning_trades', 'status']:
        if k in data:
            fields.append(f'{k}=%s')
            val = data[k]
            if k == 'rules_json' and isinstance(val, dict):
                val = json.dumps(val, ensure_ascii=False)
            params.append(val)
    if fields:
        params.append(id)
        conn.execute(f'UPDATE stock_strategy SET {",".join(fields)} WHERE id=%s', params)
        conn.commit()
    conn.close()
    return jsonify({'message': '策略已更新'})


@bp.route('/api/stocks/strategies/<int:id>', methods=['DELETE'])
def delete_strategy(id):
    conn = _db()
    conn.execute('DELETE FROM stock_strategy WHERE id=%s', (id,))
    conn.commit()
    conn.close()
    return jsonify({'message': '策略已删除'})


# ---- AI Review (复盘) ----

@bp.route('/api/stocks/review', methods=['POST'])
def ai_review():
    """AI reviews today's trading: success/failure analysis, strategy improvement suggestions."""
    from modules.ai_writer import call_llm
    data = request.get_json(silent=True) or {}

    conn = _db()
    # Get holding stocks
    holdings = conn.execute(
        "SELECT * FROM stock_watchlist WHERE list_type = 'holding'"
    ).fetchall()
    # Get active strategies
    strategies = conn.execute(
        "SELECT * FROM stock_strategy WHERE status = 'active'"
    ).fetchall()
    conn.close()

    holding_info = '; '.join([f"{r['stock_name']}({r['stock_code']}) 买入:{r['buy_price']}" for r in holdings]) or '暂无持仓'
    strategy_info = '; '.join([f"{r['name']}({r['strategy_type']}) 胜率:{r['hit_rate']}" for r in strategies]) or '暂无策略'

    user_input = data.get('input', '')

    prompt = f"""请进行今日股票交易复盘：

当前持仓：{holding_info}
活跃策略：{strategy_info}
用户补充信息：{user_input}

请以JSON格式返回复盘分析：
{{
  "success_trades": "今日成功交易分析",
  "failure_trades": "今日失败交易分析",
  "reason_analysis": "原因分析",
  "strategy_suggestions": "策略改进建议",
  "win_rate_trend": "历史胜率变化趋势"
}}"""

    try:
        resp, _tokens, _model = call_llm(prompt, system_prompt="你是专业的股票交易分析师，擅长复盘分析。")
        import re
        json_match = re.search(r'\{[\s\S]*\}', resp)
        if json_match:
            result = json.loads(json_match.group())
        else:
            result = {'reason_analysis': resp[:500]}

        return jsonify({'review': result, 'message': 'AI复盘完成'})
    except Exception as e:
        return jsonify({'error': str(e)}), 500
