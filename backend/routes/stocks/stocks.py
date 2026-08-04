"""Stock Research System routes - watchlist, real screening, strategies."""

from flask import Blueprint, request, jsonify
from config import get_db as _db, get_setting, update_setting
import json
import re
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
           (stock_code, stock_name, list_type, buy_price, quantity, notes,
            target_price, alert_below_cost, alert_on_target)
           VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)''',
        (data.get('stock_code', ''), data.get('stock_name', ''),
         data.get('list_type', 'watch'), data.get('buy_price', 0),
         data.get('quantity', 0), data.get('notes', ''),
         data.get('target_price', 0) or 0,
         bool(data.get('alert_below_cost', True)),
         bool(data.get('alert_on_target', True)))
    )
    new_id = cur.lastrowid
    conn.commit()
    conn.close()
    return jsonify({'id': new_id, 'message': '已添加到自选股'})


@bp.route('/api/stocks/watchlist/refresh-prices', methods=['POST'])
def refresh_watchlist_prices_api():
    """手动/定时刷新自选股现价（盈亏由买入价与现价计算）。"""
    try:
        from modules.stock_watchlist_scheduler import refresh_watchlist_prices
        result = refresh_watchlist_prices(force_spot=True)
        return jsonify(result)
    except Exception as e:
        return jsonify({'error': str(e), 'message': '刷新现价失败'}), 500


@bp.route('/api/stocks/watchlist/<int:id>', methods=['PUT'])
def update_watchlist(id):
    data = request.get_json(silent=True) or {}
    conn = _db()
    fields, params = [], []
    for k in ['stock_code', 'stock_name', 'list_type', 'buy_price', 'current_price', 'quantity',
              'notes', 'target_price', 'alert_below_cost', 'alert_on_target']:
        if k in data:
            fields.append(f'{k}=%s')
            val = data[k]
            if k in ('alert_below_cost', 'alert_on_target'):
                val = bool(val)
            params.append(val)
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

def _json_safe(value):
    """把 NaN/Inf/numpy 标量转成 JSON 合法值（浏览器 JSON.parse 不接受 NaN）。"""
    if value is None:
        return None
    if isinstance(value, float):
        if value != value or value in (float('inf'), float('-inf')):
            return None
        return value
    if isinstance(value, dict):
        return {k: _json_safe(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_safe(v) for v in value]
    # numpy / pandas 标量
    if hasattr(value, 'item') and not isinstance(value, (bytes, str)):
        try:
            return _json_safe(value.item())
        except Exception:
            return None
    return value


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
                'bars': [],
                'note': '暂无行情数据，请稍后重试或检查代码',
            })
        df = add_indicators(df)
        snap = latest_snapshot(df)
        chart_cols = [
            'date', 'open', 'high', 'low', 'close', 'volume',
            'MA5', 'MA10', 'MA20', 'MA30', 'MA60', 'MA250',
        ]
        chart_df = df[[c for c in chart_cols if c in df.columns]].tail(120).copy()
        # 缓存读出后 date 可能已是字符串，兼容两种情况
        if hasattr(chart_df['date'].dtype, 'tz') or str(chart_df['date'].dtype).startswith('datetime'):
            chart_df['date'] = chart_df['date'].dt.strftime('%Y-%m-%d')
        else:
            chart_df['date'] = chart_df['date'].astype(str).str.slice(0, 10)
        # DataFrame.where(..., None) 对 float 列会把 None 再变成 NaN，必须用 to_json 才能得到 null
        bars = json.loads(chart_df.to_json(orient='records', date_format='iso'))
        return jsonify(_json_safe({
            'code': code,
            'indicators': {k: v for k, v in snap.items() if isinstance(v, dict)},
            'bars': bars,
            'close': snap.get('close'),
            'pct_hint': snap.get('pct_hint'),
            'note': '基于腾讯/新浪前复权日 K 计算；年线按250个交易日（不足时为空）',
        }))
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

def _strategy_rules_blob(data) -> str:
    """把用户文字策略编译成可执行 JSON 存库。"""
    from modules.stock_screener import build_strategy_payload
    text = data.get('rules_text')
    if text is None:
        raw = data.get('rules_json', data.get('rules', ''))
        if isinstance(raw, dict):
            text = raw.get('text') or ''
        elif isinstance(raw, str):
            text = raw
        else:
            text = json.dumps(raw, ensure_ascii=False) if raw else ''
    payload = build_strategy_payload(text or '', data.get('status') or 'active')
    if data.get('match_mode'):
        payload['match_mode'] = data['match_mode']
    if data.get('min_hits') is not None:
        payload['min_hits'] = int(data['min_hits'])
    return json.dumps(payload, ensure_ascii=False)


@bp.route('/api/stocks/strategies/parse', methods=['POST'])
def parse_strategy():
    """预览：文字描述 → 将用于筛选的条件。"""
    from modules.stock_screener import parse_strategy_text
    data = request.get_json(silent=True) or {}
    text = data.get('text') or data.get('rules_text') or ''
    return jsonify(parse_strategy_text(text))


@bp.route('/api/stocks/strategies')
def list_strategies():
    from modules.stock_screener import strategy_from_row
    conn = _db()
    rows = conn.execute('SELECT * FROM stock_strategy ORDER BY created_at DESC').fetchall()
    conn.close()
    out = [strategy_from_row(dict(r)) for r in rows]
    active_only = (request.args.get('active') or '').lower() in ('1', 'true', 'yes')
    if active_only:
        out = [x for x in out if (x.get('status') or '') == 'active']
    return jsonify({'list': out})


@bp.route('/api/stocks/strategies', methods=['POST'])
def create_strategy():
    data = request.get_json(silent=True) or {}
    rules_blob = _strategy_rules_blob(data)
    status = data.get('status') or 'active'
    conn = _db()
    cur = conn.execute(
        '''INSERT INTO stock_strategy
           (name, description, strategy_type, rules_json, status)
           VALUES (%s, %s, %s, %s, %s)''',
        (data.get('name', ''), data.get('description', ''),
         data.get('strategy_type', 'trend'), rules_blob, status)
    )
    new_id = cur.lastrowid
    conn.commit()
    row = conn.execute('SELECT * FROM stock_strategy WHERE id=%s', (new_id,)).fetchone()
    conn.close()
    from modules.stock_screener import strategy_from_row
    return jsonify({'id': new_id, 'message': '策略已创建', 'strategy': strategy_from_row(dict(row))})


@bp.route('/api/stocks/strategies/<int:id>', methods=['PUT'])
def update_strategy(id):
    data = request.get_json(silent=True) or {}
    conn = _db()
    fields, params = [], []
    if 'rules_text' in data or 'rules_json' in data or 'rules' in data:
        data = {**data, 'rules_json': _strategy_rules_blob(data)}
    for k in ['name', 'description', 'strategy_type', 'rules_json', 'score', 'hit_rate',
              'total_trades', 'winning_trades', 'status']:
        if k in data:
            fields.append(f'{k}=%s')
            params.append(data[k])
    if fields:
        params.append(id)
        conn.execute(f'UPDATE stock_strategy SET {",".join(fields)} WHERE id=%s', params)
        conn.commit()
    row = conn.execute('SELECT * FROM stock_strategy WHERE id=%s', (id,)).fetchone()
    conn.close()
    if not row:
        return jsonify({'error': 'not found'}), 404
    from modules.stock_screener import strategy_from_row
    return jsonify({'message': '策略已更新', 'strategy': strategy_from_row(dict(row))})


@bp.route('/api/stocks/strategies/<int:id>', methods=['DELETE'])
def delete_strategy(id):
    conn = _db()
    conn.execute('DELETE FROM stock_strategy WHERE id=%s', (id,))
    conn.commit()
    conn.close()
    return jsonify({'message': '策略已删除'})


# ---- AI Review ----

def _safe_parse_llm_json(text: str):
    """尽量从模型输出里抠出 JSON；失败返回 None。"""
    if not text:
        return None
    raw = str(text).strip()
    # 去掉 markdown 代码块
    if raw.startswith('```'):
        raw = re.sub(r'^```(?:json)?\s*', '', raw, flags=re.IGNORECASE)
        raw = re.sub(r'\s*```$', '', raw)
    match = re.search(r'\{[\s\S]*\}', raw)
    if not match:
        return None
    blob = match.group()
    candidates = [blob]
    # 常见脏格式：中文引号、尾逗号、多余换行
    fixed = (
        blob.replace('\u201c', '"').replace('\u201d', '"')
            .replace('\u2018', "'").replace('\u2019', "'")
            .replace('＂', '"').replace('＇', "'")
    )
    fixed = re.sub(r',\s*([}\]])', r'\1', fixed)
    candidates.append(fixed)
    for item in candidates:
        try:
            data = json.loads(item)
            if isinstance(data, dict):
                return data
        except Exception:
            continue
    return None


@bp.route('/api/stocks/review', methods=['POST'])
def ai_review():
    """支持两类输入：
    1) 今日买卖记录复盘
    2) 持仓/下一步怎么操作（没有成交记录也可以）
    """
    from modules.ai_writer import call_llm
    data = request.get_json(silent=True) or {}
    conn = _db()
    holdings = conn.execute(
        "SELECT * FROM stock_watchlist WHERE list_type = 'holding' ORDER BY added_at DESC"
    ).fetchall()
    watch = conn.execute(
        "SELECT stock_code, stock_name, list_type, buy_price, current_price, notes "
        "FROM stock_watchlist WHERE list_type IN ('watch','observe','holding') "
        "ORDER BY added_at DESC LIMIT 30"
    ).fetchall()
    strategies = conn.execute(
        "SELECT id, name, strategy_type, hit_rate, status FROM stock_strategy WHERE status = 'active'"
    ).fetchall()
    conn.close()

    def _fmt_row(r):
        name = r.get('stock_name') or ''
        code = r.get('stock_code') or ''
        buy = r.get('buy_price') or 0
        cur = r.get('current_price') or 0
        qty = r.get('quantity') or 0
        pnl = ''
        try:
            if buy and cur:
                pct = (float(cur) - float(buy)) / float(buy) * 100
                pnl = f' 盈亏:{pct:+.1f}%'
        except Exception:
            pass
        note = f" 备注:{(r.get('notes') or '')[:40]}" if r.get('notes') else ''
        return f"{name}({code}) 成本:{buy} 现价:{cur} 数量:{qty}{pnl}{note}"

    holding_info = '; '.join(_fmt_row(dict(r)) for r in holdings) or '系统自选中暂无“持仓”记录'
    watch_info = '; '.join(
        f"{r['stock_name'] or ''}({r['stock_code']})[{r['list_type']}]"
        for r in watch
    ) or '无'
    strategy_info = '; '.join(
        f"{r['name']}({r['strategy_type']})" for r in strategies
    ) or '暂无启用策略'
    user_input = (data.get('input') or '').strip()

    # 给持仓补一点技术面快照，便于模型谈“接下来怎么操作”
    tech_briefs = []
    try:
        from modules.market_data import get_daily_bars
        from modules.stock_ta import add_indicators, latest_snapshot
        codes = []
        for r in holdings:
            c = str(r['stock_code'] or '').zfill(6)
            if c.isdigit() and c not in codes:
                codes.append(c)
        # 用户文字里也可能直接写了代码
        for m in re.findall(r'\b(\d{6})\b', user_input):
            if m not in codes:
                codes.append(m)
        for code in codes[:5]:
            df = get_daily_bars(code, days=120)
            if df is None or df.empty:
                continue
            snap = latest_snapshot(add_indicators(df))
            ma = snap.get('MA') or {}
            macd = snap.get('MACD') or {}
            tech_briefs.append(
                f"{code} 收盘:{snap.get('close')} 涨跌约:{snap.get('pct_hint')}% "
                f"MA信号:{ma.get('signal')} MACD:{macd.get('signal')} "
                f"MA5:{ma.get('MA5')} MA20:{ma.get('MA20')} MA60:{ma.get('MA60')}"
            )
    except Exception as e:
        tech_briefs.append(f'技术面快照获取失败: {e}')

    tech_info = '；'.join(tech_briefs) or '无可用技术面快照'

    prompt = f"""你是A股交易顾问。用户可能是在做「今日买卖复盘」，也可能是在问「持仓怎么办/下一步怎么操作」。
两种都要认真回答，不要因为没有今日成交就敷衍说“暂无交易记录”。

【系统持仓】
{holding_info}

【自选/观察】
{watch_info}

【启用中的策略名称】
{strategy_info}

【技术面快照（供参考，可能延迟）】
{tech_info}

【用户描述】
{user_input or '（用户未补充文字，请基于系统持仓给出复盘与操作思路）'}

要求：
1. 若用户在问持仓/浮亏/下一步，重点写 position_view、next_actions、risk_warning。
2. 若用户写了买卖记录，再写 success_trades / failure_trades。
3. 没有买卖记录时，success_trades/failure_trades 写空字符串即可，不要写“暂无xxx”。
4. 建议要具体可执行（继续持有/减仓比例/加仓条件/止损位思路），并说明依据；同时声明不构成投资建议。
5. 只返回 JSON，不要 markdown。字段值都是字符串。

{{
  "situation_summary": "用2-4句话概括当前处境",
  "position_view": "对持仓标的的看法（强弱、关键位、是否与策略一致）",
  "next_actions": "接下来怎么操作：分情景给出（例如反弹减仓/跌破某条件止损/企稳再看）",
  "risk_warning": "主要风险与无效条件",
  "success_trades": "今日成功交易分析（没有则空字符串）",
  "failure_trades": "今日失败交易分析（没有则空字符串）",
  "reason_analysis": "原因分析（为何亏损/为何卡住）",
  "strategy_suggestions": "策略与纪律改进建议",
  "win_rate_trend": "若无法评估胜率趋势，写对后续观察重点即可"
}}"""
    try:
        resp, _tokens, _model = call_llm(
            prompt,
            system_prompt=(
                '你是专业、务实的A股交易顾问。只输出合法 JSON。'
                '字符串里如需引号请使用中文直角引号或避免引号。'
                '回答要具体，禁止空洞套话。'
            ),
            temperature=0.4,
            max_tokens=2200,
        )
        result = _safe_parse_llm_json(resp)
        keys = (
            'situation_summary', 'position_view', 'next_actions', 'risk_warning',
            'success_trades', 'failure_trades', 'reason_analysis',
            'strategy_suggestions', 'win_rate_trend',
        )
        if not result:
            result = {
                'situation_summary': '',
                'position_view': '',
                'next_actions': '',
                'risk_warning': '',
                'success_trades': '',
                'failure_trades': '',
                'reason_analysis': (resp or '').strip()[:2000] or '模型未返回有效内容',
                'strategy_suggestions': '',
                'win_rate_trend': '',
            }
        else:
            for key in keys:
                val = result.get(key, '')
                if isinstance(val, (list, dict)):
                    result[key] = json.dumps(val, ensure_ascii=False)
                elif val is None:
                    result[key] = ''
                else:
                    result[key] = str(val)
            # 清掉无意义占位
            for key in ('success_trades', 'failure_trades', 'win_rate_trend'):
                t = (result.get(key) or '').strip()
                if t.startswith('暂无') or t in ('无', '无记录', '无交易', 'N/A', 'n/a'):
                    result[key] = ''
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
