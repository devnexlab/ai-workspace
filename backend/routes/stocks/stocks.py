"""Stock Research System routes - watchlist, real screening, strategies."""

from flask import Blueprint, request, jsonify
from config import get_db as _db, get_setting, update_setting
import json
import threading

bp = Blueprint('stocks', __name__)


# ---- Watchlist ----

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
    fields, params = [], []
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


# ---- Pattern rules (configurable) ----

@bp.route('/api/stocks/pattern-rules')
def get_pattern_rules():
    from modules.stock_screener import list_default_rules
    saved = get_setting('stock', 'pattern_rules_json', '')
    rules = list_default_rules()
    if saved:
        try:
            custom = json.loads(saved)
            if isinstance(custom, list) and custom:
                # merge by key
                base = {r['key']: r for r in rules}
                for c in custom:
                    k = c.get('key')
                    if k and k in base:
                        base[k] = {**base[k], **c}
                    elif k:
                        base[k] = c
                rules = list(base.values())
        except Exception:
            pass
    return jsonify({
        'rules': rules,
        'defaults': list_default_rules(),
        'match_mode_default': get_setting('stock', 'match_mode', 'and') or 'and',
        'max_stocks_default': int(get_setting('stock', 'max_stocks', '300') or 300),
        'min_hits_default': int(get_setting('stock', 'min_hits', '1') or 1),
    })


@bp.route('/api/stocks/screening/<int:id>/cancel', methods=['POST'])
def cancel_screening(id):
    """标记取消（正在跑的线程会在下一轮进度写入时看到，并尽快结束不了时至少状态正确）。"""
    conn = _db()
    row = conn.execute('SELECT status FROM stock_screening WHERE id=%s', (id,)).fetchone()
    if not row:
        conn.close()
        return jsonify({'error': 'not found'}), 404
    if row['status'] in ('completed', 'failed', 'cancelled'):
        conn.close()
        return jsonify({'message': f'任务已是 {row["status"]}'})
    conn.execute(
        "UPDATE stock_screening SET status='cancelled', message='用户取消' WHERE id=%s",
        (id,)
    )
    conn.commit()
    conn.close()
    return jsonify({'message': '已取消'})


@bp.route('/api/stocks/pattern-rules', methods=['PUT'])
def save_pattern_rules():
    data = request.get_json(silent=True) or {}
    rules = data.get('rules')
    if rules is not None:
        update_setting('stock', 'pattern_rules_json', json.dumps(rules, ensure_ascii=False))
    if 'match_mode' in data:
        update_setting('stock', 'match_mode', str(data['match_mode']))
    if 'max_stocks' in data:
        update_setting('stock', 'max_stocks', str(int(data['max_stocks'])))
    if 'min_hits' in data:
        update_setting('stock', 'min_hits', str(int(data['min_hits'])))
    return jsonify({'message': '规则已保存'})


# ---- Indicators ----

@bp.route('/api/stocks/indicators')
def get_indicators():
    code = request.args.get('code', '')
    if not code:
        return jsonify({'error': 'stock code required'}), 400
    try:
        from modules.market_data import get_daily_bars
        from modules.stock_ta import add_indicators, latest_snapshot
        df = get_daily_bars(code, days=300)
        if df is None or df.empty:
            return jsonify({
                'code': code,
                'indicators': {},
                'note': '暂无行情数据，请稍后重试或检查代码',
            })
        df = add_indicators(df)
        snap = latest_snapshot(df)
        chart_cols = [
            'date', 'open', 'high', 'low', 'close', 'volume',
            'MA5', 'MA10', 'MA20', 'MA30', 'MA60', 'MA250',
        ]
        chart_df = df[[c for c in chart_cols if c in df.columns]].tail(120).copy()
        chart_df['date'] = chart_df['date'].dt.strftime('%Y-%m-%d')
        chart_df = chart_df.where(chart_df.notna(), None)
        return jsonify({
            'code': code,
            'indicators': {k: v for k, v in snap.items() if isinstance(v, dict)},
            'bars': chart_df.to_dict('records'),
            'close': snap.get('close'),
            'pct_hint': snap.get('pct_hint'),
            'note': '基于 AKShare 前复权日 K 计算；年线按250个交易日',
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500


# ---- Screening ----

def _update_screening(sid, **kwargs):
    conn = _db()
    fields, params = [], []
    for k, v in kwargs.items():
        fields.append(f'{k}=%s')
        params.append(v)
    params.append(sid)
    conn.execute(f'UPDATE stock_screening SET {",".join(fields)} WHERE id=%s', params)
    conn.commit()
    conn.close()


def _saved_pattern_rules():
    """读取设置里自定义规则；空则 None（走系统默认 enabled）。"""
    saved = get_setting('stock', 'pattern_rules_json', '') or ''
    if not saved.strip():
        return None
    try:
        data = json.loads(saved)
        return data if isinstance(data, list) and data else None
    except Exception:
        return None


def _run_screening_job(sid, payload):
    from modules.stock_screener import run_screen
    try:
        def progress(done, total):
            conn = _db()
            row = conn.execute('SELECT status FROM stock_screening WHERE id=%s', (sid,)).fetchone()
            conn.close()
            if row and row['status'] in ('cancelled', 'failed'):
                raise RuntimeError('cancelled')
            _update_screening(
                sid,
                status='running',
                message=f'扫描中 {done}/{total}',
            )

        conditions = payload.get('conditions') or []
        rules = payload.get('rules')
        # 未传勾选/规则时：用设置里保存的形态规则；再空则系统默认
        if not conditions and not rules:
            rules = _saved_pattern_rules()

        result = run_screen(
            conditions=conditions or None,
            rules=rules,
            match_mode=payload.get('match_mode') or get_setting('stock', 'match_mode', 'and') or 'and',
            min_hits=int(payload.get('min_hits') or get_setting('stock', 'min_hits', '1') or 1),
            max_stocks=int(payload.get('max_stocks') if payload.get('max_stocks') is not None else (get_setting('stock', 'max_stocks', '300') or 300)),
            workers=int(payload.get('workers') or 8),
            progress_cb=progress,
        )
        # 若用户已取消，不要覆盖 cancelled
        conn = _db()
        cur = conn.execute('SELECT status FROM stock_screening WHERE id=%s', (sid,)).fetchone()
        conn.close()
        if cur and cur['status'] == 'cancelled':
            return
        _update_screening(
            sid,
            status='completed',
            results_json=json.dumps(result.get('results') or [], ensure_ascii=False),
            message=result.get('message') or '完成',
            conditions_json=json.dumps({
                'conditions': payload.get('conditions') or [],
                'rules': result.get('rules') or [],
                'match_mode': result.get('match_mode'),
                'min_hits': result.get('min_hits'),
                'scanned': result.get('scanned'),
                'universe': result.get('universe'),
                'matched': result.get('matched'),
                'rule_stats': result.get('rule_stats') or [],
                'no_data': result.get('no_data'),
            }, ensure_ascii=False),
        )
    except Exception as e:
        if 'cancelled' in str(e).lower():
            _update_screening(sid, status='cancelled', message='用户取消')
        else:
            _update_screening(sid, status='failed', message=str(e)[:500])


@bp.route('/api/stocks/screening', methods=['POST'])
def run_screening():
    """
    启动筛选（后台执行）。
    body:
      conditions: ['MACD金叉', ...] 可选；空则用默认启用规则
      rules: [{key, enabled, params}] 可选，完整覆盖
      match_mode: or|and|min
      min_hits: int
      max_stocks: int  # 0=全市场（较慢）
      sync: bool  # true 则同步等待（小样本调试）
    """
    data = request.get_json(silent=True) or {}
    conditions = data.get('conditions') or []
    name = data.get('name') or '技术面筛选'

    conn = _db()
    cur = conn.execute(
        '''INSERT INTO stock_screening (name, conditions_json, results_json, status, message)
           VALUES (%s, %s, %s, 'running', %s)''',
        (name,
         json.dumps(conditions, ensure_ascii=False),
         json.dumps([], ensure_ascii=False),
         '任务已启动…')
    )
    new_id = cur.lastrowid
    conn.commit()
    conn.close()

    payload = {
        'conditions': conditions,
        'rules': data.get('rules'),
        'match_mode': data.get('match_mode'),
        'min_hits': data.get('min_hits'),
        'max_stocks': data.get('max_stocks'),
        'workers': data.get('workers'),
    }

    if data.get('sync'):
        _run_screening_job(new_id, payload)
        conn = _db()
        row = conn.execute('SELECT * FROM stock_screening WHERE id=%s', (new_id,)).fetchone()
        conn.close()
        row = dict(row)
        try:
            row['results'] = json.loads(row.get('results_json') or '[]')
        except Exception:
            row['results'] = []
        return jsonify({
            'id': new_id,
            'status': row.get('status'),
            'message': row.get('message'),
            'results': row['results'],
            'count': len(row['results']),
        })

    threading.Thread(target=_run_screening_job, args=(new_id, payload), daemon=True).start()
    return jsonify({
        'id': new_id,
        'status': 'running',
        'message': '筛选已在后台启动，请稍后刷新历史或轮询详情',
    })


@bp.route('/api/stocks/screening/<int:id>')
def get_screening(id):
    conn = _db()
    row = conn.execute('SELECT * FROM stock_screening WHERE id=%s', (id,)).fetchone()
    conn.close()
    if not row:
        return jsonify({'error': 'not found'}), 404
    item = dict(row)
    try:
        item['results'] = json.loads(item.get('results_json') or '[]')
    except Exception:
        item['results'] = []
    try:
        cond = json.loads(item.get('conditions_json') or '[]')
        item['conditions'] = cond
        if isinstance(cond, dict):
            item['rule_stats'] = cond.get('rule_stats') or []
    except Exception:
        item['conditions'] = item.get('conditions_json')
    return jsonify(item)


@bp.route('/api/stocks/screening/history')
def screening_history():
    conn = _db()
    rows = conn.execute(
        'SELECT id, name, conditions_json, status, message, created_at, '
        'LENGTH(results_json) as results_len FROM stock_screening '
        'ORDER BY created_at DESC LIMIT 30'
    ).fetchall()
    # also parse matched count lightly
    out = []
    for r in rows:
        item = dict(r)
        try:
            cond = json.loads(item.get('conditions_json') or '[]')
            if isinstance(cond, dict):
                item['matched'] = cond.get('matched')
                item['condition_labels'] = [
                    x.get('label') if isinstance(x, dict) else x
                    for x in (cond.get('rules') or cond.get('conditions') or [])
                ]
            elif isinstance(cond, list):
                item['condition_labels'] = cond
        except Exception:
            item['condition_labels'] = []
        out.append(item)
    conn.close()
    return jsonify({'list': out})


# ---- Strategies ----

@bp.route('/api/stocks/strategies')
def list_strategies():
    conn = _db()
    rows = conn.execute('SELECT * FROM stock_strategy ORDER BY created_at DESC').fetchall()
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
         json.dumps(data.get('rules', data.get('rules_json', {})), ensure_ascii=False
                    ) if not isinstance(data.get('rules_json'), str) else data.get('rules_json'))
    )
    new_id = cur.lastrowid
    conn.commit()
    conn.close()
    return jsonify({'id': new_id, 'message': '策略已创建'})


@bp.route('/api/stocks/strategies/<int:id>', methods=['PUT'])
def update_strategy(id):
    data = request.get_json(silent=True) or {}
    conn = _db()
    fields, params = [], []
    for k in ['name', 'description', 'strategy_type', 'rules_json', 'score', 'hit_rate',
              'total_trades', 'winning_trades', 'status']:
        if k in data:
            fields.append(f'{k}=%s')
            val = data[k]
            if k == 'rules_json' and not isinstance(val, str):
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


# ---- AI Review ----

@bp.route('/api/stocks/review', methods=['POST'])
def ai_review():
    from modules.ai_writer import call_llm
    data = request.get_json(silent=True) or {}
    conn = _db()
    holdings = conn.execute(
        "SELECT * FROM stock_watchlist WHERE list_type = 'holding'"
    ).fetchall()
    strategies = conn.execute(
        "SELECT * FROM stock_strategy WHERE status = 'active'"
    ).fetchall()
    conn.close()

    holding_info = '; '.join(
        [f"{r['stock_name']}({r['stock_code']}) 买入:{r['buy_price']}" for r in holdings]
    ) or '暂无持仓'
    strategy_info = '; '.join(
        [f"{r['name']}({r['strategy_type']}) 胜率:{r['hit_rate']}" for r in strategies]
    ) or '暂无策略'
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
        resp, _tokens, _model = call_llm(prompt, system_prompt='你是专业的股票交易分析师，擅长复盘分析。')
        import re
        json_match = re.search(r'\{[\s\S]*\}', resp)
        result = json.loads(json_match.group()) if json_match else {'reason_analysis': resp[:500]}
        return jsonify({'review': result, 'message': 'AI复盘完成'})
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@bp.route('/api/stocks/note', methods=['POST'])
def stock_to_knowledge():
    """从股票一键写入知识库笔记。"""
    data = request.get_json(silent=True) or {}
    code = data.get('stock_code') or data.get('code') or ''
    name = data.get('stock_name') or data.get('name') or ''
    title = data.get('title') or f'交易笔记 {name}({code})'.strip()
    content = data.get('content') or data.get('notes') or ''
    tags = data.get('tags') or f'股票,{code},{name}'.strip(',')
    conn = _db()
    cur = conn.execute(
        '''INSERT INTO knowledge_item
           (title, content, source_type, category, tags, source_url, stock_code)
           VALUES (%s, %s, 'stock', %s, %s, %s, %s)''',
        (title, content, data.get('category') or '股票交易', tags, code, code)
    )
    new_id = cur.lastrowid
    conn.commit()
    conn.close()
    return jsonify({'id': new_id, 'message': '已写入知识库'})
