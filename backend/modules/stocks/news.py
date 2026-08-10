"""
股票情报：抓取东财/财联社等公开资讯 + 财经热搜。
早间推送到页面 → 对新闻 AI 分析总结 → 写入「今日股市简报」。
不做微信推送。
"""

from __future__ import annotations

import json
import re
from datetime import datetime, date

import requests

from config import get_db, update_setting

FINANCE_KEYWORDS = (
    '股', 'A股', '港股', '美股', '指数', '央行', '降准', '降息', '沪深', '创业板',
    '科创', '北交所', '涨停', '跌停', '证监会', '上市', '券商', '基金', '牛市',
    '熊市', 'IPO', '财报', '业绩', '市值', '成交', '两市', '上证', '深证', '恒生',
    '纳斯达克', '道琼斯', '原油', '黄金', '人民币', '汇率', '国债', '债券', '期货',
    '主力', '北向', '南向', '融资', '融券', '回购', '分红', '减持', '增持',
    'ST', '退市', '并购', '重组', '芯片', '新能源', '白酒', '银行', '地产',
)


def _pick(row: dict, *keys, default=''):
    for k in keys:
        if k in row and row[k] is not None and str(row[k]).strip() != '':
            return row[k]
    return default


def _df_records(df) -> list[dict]:
    if df is None or getattr(df, 'empty', True):
        return []
    cols = [str(c) for c in df.columns]
    out = []
    for _, series in df.iterrows():
        out.append({cols[i]: series.iloc[i] for i in range(len(cols))})
    return out


def _normalize_item(title, summary='', url='', source='', publish_time='', hot=0) -> dict | None:
    title = (title or '').strip()
    if not title or len(title) < 2:
        return None
    if isinstance(publish_time, datetime):
        publish_time = publish_time.strftime('%Y-%m-%d %H:%M:%S')
    elif hasattr(publish_time, 'isoformat'):
        publish_time = str(publish_time)
    else:
        publish_time = str(publish_time or '').strip()
    return {
        'title': title[:200],
        'summary': (summary or '').strip()[:800],
        'url': (url or '').strip(),
        'source': source or '财经资讯',
        'publish_time': publish_time,
        'hot': int(hot or 0),
    }


def _is_finance_title(title: str) -> bool:
    t = title or ''
    return any(k in t for k in FINANCE_KEYWORDS)


def fetch_eastmoney_global(limit=40) -> list[dict]:
    items = []
    try:
        import akshare as ak
        df = ak.stock_info_global_em()
        rows = _df_records(df)
        for row in rows[:limit]:
            vals = list(row.values())
            title = _pick(row, '标题', 'title', 'name', default=vals[0] if vals else '')
            summary = _pick(row, '摘要', 'summary', 'content', default=vals[1] if len(vals) > 1 else '')
            pub = _pick(row, '发布时间', '时间', 'publish_time', 'time', default=vals[2] if len(vals) > 2 else '')
            url = _pick(row, '链接', 'url', 'link', default=vals[3] if len(vals) > 3 else '')
            it = _normalize_item(title, summary, url, '东方财富', pub)
            if it:
                items.append(it)
    except Exception as e:
        print(f'[StockNews] eastmoney global failed: {e}')
    return items


def fetch_cls_telegraph(limit=30) -> list[dict]:
    """财联社电报。akshare 无直链时，补搜索页链接便于跳转。"""
    from urllib.parse import quote
    items = []
    try:
        import akshare as ak
        df = ak.stock_info_global_cls()
        rows = _df_records(df)
        for row in rows[:limit]:
            vals = list(row.values())
            title = _pick(row, '标题', 'title', default=vals[0] if vals else '')
            content = _pick(row, '内容', 'content', '摘要', default=vals[1] if len(vals) > 1 else '')
            d = _pick(row, '发布日期', '日期', default='')
            t = _pick(row, '发布时间', '时间', default='')
            pub = f'{d} {t}'.strip()
            # 接口无文章 URL：跳转财联社站内搜索（按标题）
            link = ''
            if title:
                link = f'https://www.cls.cn/searchPage?keyword={quote(str(title)[:80])}&type=telegram'
            it = _normalize_item(title, content, link, '财联社', pub)
            if it:
                items.append(it)
    except Exception as e:
        print(f'[StockNews] cls failed: {e}')
    return items


def fetch_finance_hot_search(limit=20) -> list[dict]:
    items = []
    try:
        from modules.content_ops.hotspots import fetch_weibo_hot, fetch_baidu_hot
        for row in (fetch_weibo_hot(30) or []) + (fetch_baidu_hot(30) or []):
            title = row.get('title') or ''
            if not _is_finance_title(title):
                continue
            it = _normalize_item(
                title,
                summary=row.get('keyword') or '财经热搜',
                url=row.get('url') or '',
                source=row.get('author') or row.get('platform') or '财经热搜',
                publish_time=row.get('publish_time') or '',
                hot=int(row.get('likes') or 0),
            )
            if it:
                items.append(it)
            if len(items) >= limit:
                break
    except Exception as e:
        print(f'[StockNews] finance hot failed: {e}')
    return items


def fetch_eastmoney_fallback(limit=30) -> list[dict]:
    items = []
    url = (
        'https://np-listapi.eastmoney.com/comm/web/getNewsByColumns'
        '?client=web&biz=web_news_col&column=350&order=1'
        f'&needInteractData=0&page_index=1&page_size={limit}&req_trace=stock-news'
    )
    try:
        resp = requests.get(
            url,
            headers={'User-Agent': 'Mozilla/5.0', 'Referer': 'https://finance.eastmoney.com/'},
            timeout=12,
        )
        if resp.status_code != 200:
            return items
        data = resp.json() or {}
        rows = ((data.get('data') or {}).get('list')) or data.get('list') or []
        for row in rows[:limit]:
            title = row.get('title') or row.get('Title') or ''
            summary = row.get('digest') or row.get('summary') or row.get('Digest') or ''
            link = row.get('url') or row.get('Url') or row.get('art_url') or ''
            if link and not str(link).startswith('http'):
                link = f'https://finance.eastmoney.com{link}'
            pub = row.get('showTime') or row.get('datetime') or row.get('date') or ''
            it = _normalize_item(title, summary, link, '东方财富', pub)
            if it:
                items.append(it)
    except Exception as e:
        print(f'[StockNews] eastmoney http fallback failed: {e}')
    return items


def fetch_all_stock_news(limit=50) -> tuple[list[dict], str]:
    merged: list[dict] = []
    sources_ok = []
    seen = set()

    def _add(batch, label):
        nonlocal merged
        if not batch:
            return
        sources_ok.append(label)
        for it in batch:
            key = re.sub(r'\s+', '', it['title'])[:40]
            if not key or key in seen:
                continue
            seen.add(key)
            merged.append(it)

    _add(fetch_eastmoney_global(40), '东财快讯')
    _add(fetch_cls_telegraph(25), '财联社')
    _add(fetch_finance_hot_search(15), '财经热搜')

    if len(merged) < 8:
        _add(fetch_eastmoney_fallback(30), '东财API')

    merged.sort(key=lambda x: (int(x.get('hot') or 0), str(x.get('publish_time') or '')), reverse=True)
    merged = merged[:limit]
    src = '/'.join(sources_ok) if sources_ok else '无可用源'
    return merged, f'财经资讯 {len(merged)} 条（{src}）'


def _today() -> str:
    return date.today().isoformat()


def get_today_briefing(conn=None) -> dict | None:
    own = conn is None
    if own:
        conn = get_db()
    row = conn.execute(
        'SELECT * FROM stock_daily_briefing WHERE brief_date=%s',
        (_today(),),
    ).fetchone()
    if own:
        conn.close()
    if not row:
        return None
    d = dict(row)
    news = d.get('news_json') or '[]'
    if isinstance(news, str):
        try:
            d['news'] = json.loads(news)
        except json.JSONDecodeError:
            d['news'] = []
    else:
        d['news'] = news
    return d


def _rule_brief_md(news: list[dict], message: str) -> str:
    today = datetime.now().strftime('%Y年%m月%d日')
    lines = [
        f'# 今日股市简报（{today}）',
        '',
        f'> 数据来源：{message}',
        '',
        '## 要点速览',
        '',
    ]
    for i, it in enumerate(news[:12], 1):
        title = it.get('title') or ''
        src = it.get('source') or ''
        summary = (it.get('summary') or '').strip()
        lines.append(f'{i}. **{title}**（{src}）')
        if summary:
            lines.append(f'   - {summary[:120]}')
    lines.extend([
        '',
        '## 说明',
        '',
        '以上为公开资讯聚合，仅供参考，不构成投资建议。',
    ])
    return '\n'.join(lines)


def save_news_only(news: list[dict], message: str) -> dict:
    """早间推送到页面：只更新新闻列表，保留已有简报。"""
    conn = get_db()
    today = _today()
    news_json = json.dumps(news, ensure_ascii=False)
    existing = conn.execute(
        'SELECT brief_md, ai_analysis_md FROM stock_daily_briefing WHERE brief_date=%s',
        (today,),
    ).fetchone()
    brief_md = (existing['brief_md'] if existing else '') or ''
    ai_md = (existing['ai_analysis_md'] if existing else '') or ''
    conn.execute(
        '''INSERT INTO stock_daily_briefing
           (brief_date, news_json, brief_md, ai_analysis_md, source_message, updated_at)
           VALUES (%s, %s, %s, %s, %s, CURRENT_TIMESTAMP)
           ON CONFLICT (brief_date) DO UPDATE SET
             news_json = EXCLUDED.news_json,
             source_message = EXCLUDED.source_message,
             updated_at = CURRENT_TIMESTAMP''',
        (today, news_json, brief_md, ai_md, message),
    )
    conn.commit()
    conn.close()
    return get_today_briefing() or {}


def save_brief_md_only(brief_md: str, message: str | None = None) -> dict:
    """只更新今日股市简报，保留新闻与 AI 分析。"""
    conn = get_db()
    today = _today()
    row = get_today_briefing(conn)
    if not row:
        conn.close()
        raise Exception('暂无财经新闻，请先获取早间资讯')
    news_json = json.dumps(row.get('news') or [], ensure_ascii=False)
    ai_md = row.get('ai_analysis_md') or ''
    src = message or row.get('source_message') or ''
    conn.execute(
        '''INSERT INTO stock_daily_briefing
           (brief_date, news_json, brief_md, ai_analysis_md, source_message, updated_at)
           VALUES (%s, %s, %s, %s, %s, CURRENT_TIMESTAMP)
           ON CONFLICT (brief_date) DO UPDATE SET
             brief_md = EXCLUDED.brief_md,
             source_message = COALESCE(NULLIF(EXCLUDED.source_message, ''), stock_daily_briefing.source_message),
             updated_at = CURRENT_TIMESTAMP''',
        (today, news_json, brief_md, ai_md, src),
    )
    conn.commit()
    conn.close()
    return get_today_briefing() or {}


def save_analysis_only(ai_analysis_md: str) -> dict:
    """只更新 AI 分析总结，保留新闻与股市简报。"""
    conn = get_db()
    today = _today()
    row = get_today_briefing(conn)
    if not row:
        conn.close()
        raise Exception('暂无财经新闻，请先获取早间资讯')
    conn.execute(
        '''UPDATE stock_daily_briefing
           SET ai_analysis_md=%s, updated_at=CURRENT_TIMESTAMP
           WHERE brief_date=%s''',
        (ai_analysis_md, today),
    )
    conn.commit()
    conn.close()
    return get_today_briefing() or {}


def save_briefing(news: list[dict], brief_md: str, message: str, ai_analysis_md: str | None = None) -> dict:
    """完整写入；ai_analysis_md=None 时保留原分析。"""
    conn = get_db()
    today = _today()
    news_json = json.dumps(news, ensure_ascii=False)
    if ai_analysis_md is None:
        existing = conn.execute(
            'SELECT ai_analysis_md FROM stock_daily_briefing WHERE brief_date=%s',
            (today,),
        ).fetchone()
        ai_md = (existing['ai_analysis_md'] if existing else '') or ''
        conn.execute(
            '''INSERT INTO stock_daily_briefing
               (brief_date, news_json, brief_md, ai_analysis_md, source_message, updated_at)
               VALUES (%s, %s, %s, %s, %s, CURRENT_TIMESTAMP)
               ON CONFLICT (brief_date) DO UPDATE SET
                 news_json = EXCLUDED.news_json,
                 brief_md = EXCLUDED.brief_md,
                 source_message = EXCLUDED.source_message,
                 updated_at = CURRENT_TIMESTAMP''',
            (today, news_json, brief_md, ai_md, message),
        )
    else:
        conn.execute(
            '''INSERT INTO stock_daily_briefing
               (brief_date, news_json, brief_md, ai_analysis_md, source_message, updated_at)
               VALUES (%s, %s, %s, %s, %s, CURRENT_TIMESTAMP)
               ON CONFLICT (brief_date) DO UPDATE SET
                 news_json = EXCLUDED.news_json,
                 brief_md = EXCLUDED.brief_md,
                 ai_analysis_md = EXCLUDED.ai_analysis_md,
                 source_message = EXCLUDED.source_message,
                 updated_at = CURRENT_TIMESTAMP''',
            (today, news_json, brief_md, ai_analysis_md, message),
        )
    conn.commit()
    conn.close()
    return get_today_briefing() or {}


def refresh_news_to_page(auto_brief: bool = True) -> dict:
    """抓取财经新闻并推送到页面；默认随后自动生成今日股市简报。"""
    news, message = fetch_all_stock_news(50)
    row = save_news_only(news, message)
    row['refreshed'] = True
    row['message'] = message
    if auto_brief and news:
        try:
            row = build_stock_briefing(force=True, row=row, use_llm=True)
            row['message'] = f'{message}；已自动生成今日股市简报'
        except Exception as e:
            # 简报失败不阻断新闻入库；回退规则简报
            print(f'[StockNews] auto brief failed: {e}')
            try:
                row = build_stock_briefing(force=True, row=row, use_llm=False)
                row['message'] = f'{message}；已生成规则简报（AI 简报失败：{e}）'
            except Exception as e2:
                row['brief_error'] = str(e2)
                row['message'] = f'{message}；简报生成失败：{e2}'
    return row


def refresh_and_build_briefing(use_llm: bool = False) -> dict:
    """兼容旧调用。"""
    row = refresh_news_to_page()
    if use_llm:
        return build_stock_briefing(force=True, row=row, use_llm=True)
    return row


def build_stock_briefing(force: bool = True, row: dict | None = None, use_llm: bool = True) -> dict:
    """根据页面新闻生成「今日股市简报」（与 AI 分析分开）。"""
    row = row or get_today_briefing()
    if not row or not (row.get('news') or []):
        row = refresh_news_to_page()
    news = row.get('news') or []
    if not news:
        raise Exception('暂无财经新闻，请先获取早间资讯')

    if not force and (row.get('brief_md') or '').strip():
        return row

    rule_md = _rule_brief_md(news, row.get('source_message') or '')
    brief_md = rule_md
    tokens = 0
    model = ''
    if use_llm:
        try:
            from modules.ai.writer import call_llm
            today = datetime.now().strftime('%Y年%m月%d日')
            bullets = '\n'.join(
                f"- [{it.get('source')}] {it.get('title')}：{(it.get('summary') or '')[:100]}"
                for it in news[:20]
            )
            prompt = f"""今天是{today}。请根据下列财经新闻整理一份「今日股市简报」（Markdown）。
这是资讯归纳简报，不要写市场情绪判断、风险提示、可跟进关注点（这些留给单独的 AI 分析步骤）。

只输出以下结构：
# 今日股市简报（日期）
> 数据来源：……
## 要点速览
1. **标题**（来源）
   - 一句话摘要
（约 8-12 条即可，按重要性）
## 板块与题材
- 用条目概括当日活跃板块
## 公司与个股动态
- 挑有代表性的公司新闻

要求：语言简洁；不要编造新闻未提及的事实；文末不要加长篇免责声明以外的投研推演。

新闻列表：
{bullets}
"""
            content, tokens, model = call_llm(
                prompt,
                system_prompt='你是财经资讯编辑，只归纳给定新闻，输出 Markdown 简报。',
                temperature=0.3,
                max_tokens=1600,
            )
            if (content or '').strip():
                brief_md = content.strip()
        except Exception as e:
            print(f'[StockNews] build briefing LLM failed, use rule draft: {e}')

    out = save_briefing(
        news,
        brief_md,
        row.get('source_message') or f'简报基于 {len(news)} 条资讯',
        ai_analysis_md=None,
    )
    out['tokens'] = tokens
    out['model'] = model
    out['message'] = '今日股市简报已生成'
    return out


def analyze_briefing(force: bool = True) -> dict:
    """对新闻（及已有简报）做 AI 分析总结，写入独立字段 ai_analysis_md。"""
    row = get_today_briefing()
    if not row or not (row.get('news') or []):
        row = refresh_news_to_page()
    news = row.get('news') or []
    if not news:
        raise Exception('暂无财经新闻，请先获取早间资讯')

    if not force and (row.get('ai_analysis_md') or '').strip():
        return row

    brief = (row.get('brief_md') or '').strip()
    bullets = '\n'.join(
        f"- [{it.get('source')}] {it.get('title')}：{(it.get('summary') or '')[:80]}"
        for it in news[:20]
    )
    brief_hint = ''
    if brief:
        brief_hint = '已有股市简报（可参考，勿简单复述）：\n' + brief[:2000]
    from modules.ai.writer import call_llm
    prompt = f"""请对下列财经新闻做「AI 分析总结」（Markdown），这是投研向解读，
与「今日股市简报」分开展示。

必须包含：
1. 市场情绪（偏多/中性/谨慎 + 理由）
2. 主线题材（2-4 条）
3. 风险提示
4. 可跟进关注点（观察清单，非荐股）
5. 文末注明不构成投资建议

不要编造新闻未提及的具体涨跌幅。

新闻列表：
{bullets}

{brief_hint}
"""
    content, tokens, model = call_llm(
        prompt,
        system_prompt='你是资深投研助理，输出结构化 Markdown 分析，结论克制。',
        temperature=0.35,
        max_tokens=1600,
    )
    analysis = (content or '').strip()
    if not analysis:
        raise Exception('AI 未返回有效分析内容')
    out = save_analysis_only(analysis)
    out['tokens'] = tokens
    out['model'] = model
    out['message'] = 'AI 分析总结已完成'
    return out


def summarize_news_to_briefing(force: bool = True, row: dict | None = None) -> dict:
    """兼容旧名：改为生成股市简报。"""
    return build_stock_briefing(force=force, row=row, use_llm=True)


def run_stock_briefing_job(auto_push: bool = False) -> dict:
    """定时任务：早间把财经新闻推送到股票情报页（不做微信推送）。"""
    _ = auto_push
    row = refresh_news_to_page()
    result = {
        'ok': True,
        'brief_date': row.get('brief_date') or _today(),
        'news_count': len(row.get('news') or []),
        'message': row.get('message') or row.get('source_message') or 'ok',
        'pushed_to_page': True,
    }
    update_setting('system', 'stock_briefing_last_run', datetime.now().isoformat(timespec='seconds'))
    update_setting('system', 'stock_briefing_last_date', _today())
    return result
