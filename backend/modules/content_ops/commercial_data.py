"""
官方/商业数据台接入（巨量算数、蝉妈妈、新榜等）。

各家很少有统一公开 API，本模块做成「可配置 HTTP 适配器」：
在设置里填 Base URL / Key / 榜单路径与字段映射后，即可拉取并归一化为选题。
不爬登录页、不用 Cookie/Playwright。
"""

from __future__ import annotations

import json
import re
from datetime import datetime
from typing import Any

import requests

from config import get_settings_by_category

# (settings_category, platform_key, display_label)
COMMERCIAL_PROVIDERS = [
    ('commercial_julang', 'julang', '巨量算数', '抖音官方趋势洞察；填企业/代理 API'),
    ('commercial_chanmama', 'chanmama', '蝉妈妈', '电商与内容数据；填已开通接口'),
    ('commercial_xinbang', 'xinbang', '新榜', '新媒体榜单；填企业 API Key'),
    ('commercial_custom', 'custom', '自定义数据源', '飞瓜/卡思/自建网关等 JSON 接口'),
]


def list_commercial_providers():
    """返回各数据台配置与就绪状态（不含密钥明文）。"""
    rows = []
    for cat, key, label, desc in COMMERCIAL_PROVIDERS:
        cfg = get_settings_by_category(cat) or {}
        enabled = str(cfg.get('enabled', 'false')).lower() == 'true'
        has_key = bool((cfg.get('api_key') or '').strip())
        has_base = bool((cfg.get('api_base_url') or '').strip())
        ready = (not enabled) or (has_base and has_key)
        rows.append({
            'key': key,
            'category': cat,
            'platform': 'commercial_custom' if key == 'custom' else key,
            'label': label,
            'desc': desc,
            'builtin': True,
            'color': {
                'julang': 'blue',
                'chanmama': 'orange',
                'xinbang': 'purple',
                'custom': 'cyan',
            }.get(key, 'blue'),
            'enabled': enabled,
            'ready': ready,
            'configured': has_base and has_key,
            'message': (
                f'{label}已关闭'
                if not enabled
                else (
                    f'{label}就绪'
                    if ready
                    else f'{label}已开启但未配齐 Base URL / API Key'
                )
            ),
        })
    return rows


def _parse_json_maybe(raw: str, default=None):
    text = (raw or '').strip()
    if not text:
        return default if default is not None else {}
    try:
        return json.loads(text)
    except (json.JSONDecodeError, TypeError):
        return default if default is not None else {}


def _dig(obj: Any, path: str):
    """按点分路径取嵌套字段，如 data.list。"""
    if not path:
        return obj
    cur = obj
    for part in path.split('.'):
        part = part.strip()
        if not part:
            continue
        if isinstance(cur, dict):
            cur = cur.get(part)
        elif isinstance(cur, list) and part.isdigit():
            idx = int(part)
            cur = cur[idx] if 0 <= idx < len(cur) else None
        else:
            return None
        if cur is None:
            return None
    return cur


def _pick_field(row: dict, candidates: str, default=''):
    names = [n.strip() for n in (candidates or '').split(',') if n.strip()]
    for name in names:
        if name in row and row[name] not in (None, ''):
            return row[name]
    return default


def _to_int(val, default=0):
    if val is None or val == '':
        return default
    if isinstance(val, bool):
        return int(val)
    if isinstance(val, (int, float)):
        return int(val)
    try:
        s = re.sub(r'[^\d.]', '', str(val))
        if not s:
            return default
        return int(float(s))
    except (TypeError, ValueError):
        return default


def _fill_placeholders(text: str, cfg: dict) -> str:
    if not text:
        return text
    out = text
    for key in ('api_key', 'api_secret', 'api_base_url'):
        out = out.replace('{{' + key + '}}', str(cfg.get(key) or ''))
    return out


def _build_headers(cfg: dict) -> dict:
    headers = {
        'User-Agent': 'ai-workspace-commercial-data/1.0',
        'Accept': 'application/json',
    }
    extra = _parse_json_maybe(cfg.get('extra_headers') or '', {})
    if isinstance(extra, dict):
        headers.update({str(k): str(v) for k, v in extra.items()})

    api_key = (cfg.get('api_key') or '').strip()
    auth_type = (cfg.get('auth_type') or 'bearer').strip().lower()
    if not api_key or auth_type == 'none':
        return headers

    if auth_type == 'bearer':
        headers['Authorization'] = f'Bearer {api_key}'
    elif auth_type == 'header':
        name = (cfg.get('auth_header_name') or 'X-Api-Key').strip() or 'X-Api-Key'
        headers[name] = api_key
    # query 鉴权在 params 里处理
    return headers


def _build_params(cfg: dict) -> dict:
    params = _parse_json_maybe(cfg.get('query_params') or '', {})
    if not isinstance(params, dict):
        params = {}
    api_key = (cfg.get('api_key') or '').strip()
    if (cfg.get('auth_type') or '').strip().lower() == 'query' and api_key:
        key_name = (cfg.get('auth_header_name') or 'apikey').strip() or 'apikey'
        params[key_name] = api_key
    return params


def _normalize_rows(payload: Any, cfg: dict, platform_key: str, label: str, limit: int):
    list_path = (cfg.get('list_json_path') or 'data').strip()
    raw_list = _dig(payload, list_path) if list_path else payload

    # 常见兜底：根就是数组，或 data/list/items/result
    if not isinstance(raw_list, list):
        if isinstance(payload, list):
            raw_list = payload
        elif isinstance(payload, dict):
            for alt in ('data', 'list', 'items', 'result', 'rows', 'records'):
                cand = payload.get(alt)
                if isinstance(cand, list):
                    raw_list = cand
                    break
                if isinstance(cand, dict):
                    for nested in ('list', 'items', 'rows', 'records', 'data'):
                        if isinstance(cand.get(nested), list):
                            raw_list = cand[nested]
                            break
                if isinstance(raw_list, list):
                    break

    if not isinstance(raw_list, list):
        return []

    title_fields = cfg.get('title_field') or 'title,name,word,keyword,topic'
    hot_fields = cfg.get('hot_field') or 'hot,hot_value,hotValue,score,index,heat,num'
    url_fields = cfg.get('url_field') or 'url,link,rawUrl,share_url'

    items = []
    for i, row in enumerate(raw_list[:limit]):
        if not isinstance(row, dict):
            if isinstance(row, str) and row.strip():
                row = {'title': row.strip()}
            else:
                continue
        title = str(_pick_field(row, title_fields, '') or '').strip()
        if not title:
            continue
        hot = _to_int(_pick_field(row, hot_fields, 0), 0)
        url = str(_pick_field(row, url_fields, '') or '')
        items.append({
            'platform': platform_key,
            'title': title,
            'author': label,
            'likes': hot,
            'comments': 0,
            'favorites': 0,
            'shares': 0,
            'url': url,
            'cover': str(_pick_field(row, 'cover,img,image,pic', '') or ''),
            'keyword': '商业数据台',
            'source_type': 'commercial',
            'content_kind': 'hotspot',
            'hot_rank': i + 1,
            'analysis': f'来源：{label}',
            'publish_time': datetime.now().strftime('%Y-%m-%d %H:%M'),
        })
    return items


def fetch_provider(category: str, platform_key: str, label: str, cfg: dict | None = None):
    """
    拉取单个商业数据源。
    返回 (items, error_message)。error_message 为空表示成功（即便 0 条）。
    """
    cfg = dict(cfg or get_settings_by_category(category) or {})
    if str(cfg.get('enabled', 'false')).lower() != 'true':
        return [], f'{label}未启用'

    base = (cfg.get('api_base_url') or '').strip().rstrip('/')
    path = (cfg.get('endpoint_path') or '').strip()
    api_key = (cfg.get('api_key') or '').strip()
    if not base:
        return [], f'{label}未配置 API Base URL'
    if not api_key and (cfg.get('auth_type') or 'bearer').lower() != 'none':
        return [], f'{label}未配置 API Key'

    if path.startswith('http://') or path.startswith('https://'):
        url = path
    else:
        if path and not path.startswith('/'):
            path = '/' + path
        url = f'{base}{path}' if path else base

    method = (cfg.get('http_method') or 'GET').strip().upper()
    if method not in ('GET', 'POST'):
        method = 'GET'

    try:
        limit = max(1, min(100, int(cfg.get('limit') or 30)))
    except (TypeError, ValueError):
        limit = 30

    headers = _build_headers(cfg)
    params = _build_params(cfg)
    body = None
    if method == 'POST':
        raw_body = _fill_placeholders(cfg.get('request_body') or '', cfg)
        body = _parse_json_maybe(raw_body, {})
        if not isinstance(body, dict):
            body = {}

    try:
        resp = requests.request(
            method,
            url,
            headers=headers,
            params=params or None,
            json=body if method == 'POST' else None,
            timeout=25,
        )
    except requests.RequestException as e:
        return [], f'{label}请求失败: {e}'

    if resp.status_code >= 400:
        snippet = (resp.text or '')[:200]
        return [], f'{label} HTTP {resp.status_code}: {snippet}'

    try:
        payload = resp.json()
    except ValueError:
        return [], f'{label}返回非 JSON'

    items = _normalize_rows(payload, cfg, platform_key, label, limit)
    if not items:
        return [], f'{label}已连通但未解析到标题（请检查列表路径/字段映射）'
    return items, ''


def fetch_all_commercial(provider_keys=None):
    """
    拉取已启用的商业数据台。
    provider_keys: 可选，传 category 后缀如 julang / chanmama，或完整 category。
    """
    wanted = None
    if provider_keys:
        wanted = set()
        for k in provider_keys:
            k = (k or '').strip()
            if not k:
                continue
            if k.startswith('commercial_'):
                wanted.add(k)
            else:
                wanted.add(f'commercial_{k}')

    all_items = []
    ok_labels = []
    errors = []

    for cat, key, label, _desc in COMMERCIAL_PROVIDERS:
        if wanted is not None and cat not in wanted:
            continue
        cfg = get_settings_by_category(cat) or {}
        if str(cfg.get('enabled', 'false')).lower() != 'true':
            continue
        platform_key = 'commercial_custom' if key == 'custom' else key
        items, err = fetch_provider(cat, platform_key, label, cfg)
        if items:
            all_items.extend(items)
            ok_labels.append(f'{label}{len(items)}')
        elif err:
            errors.append(err)

    # 去重
    seen = set()
    unique = []
    for it in all_items:
        t = (it.get('title') or '').strip()
        if not t or t in seen:
            continue
        seen.add(t)
        unique.append(it)

    if unique:
        msg = f'商业数据台 {len(unique)} 条（{"/".join(ok_labels)}）'
        if errors:
            msg += f'；部分失败：{"；".join(errors[:3])}'
        return unique, msg

    if errors:
        return [], '；'.join(errors[:5])
    return [], '没有已启用且配置完整的商业数据源，请到「设置 · 官方数据台」配置'


def test_provider(provider_key: str):
    """试拉单个源，用于设置页连通性检查。"""
    key = (provider_key or '').strip()
    if key.startswith('commercial_'):
        cat = key
    else:
        cat = f'commercial_{key}'

    meta = next((p for p in COMMERCIAL_PROVIDERS if p[0] == cat), None)
    if not meta:
        return {'ok': False, 'message': f'未知数据源: {provider_key}', 'items': []}

    _, key, label, _desc = meta
    platform_key = 'commercial_custom' if key == 'custom' else key
    # 试拉时临时视为启用
    cfg = get_settings_by_category(cat) or {}
    cfg = dict(cfg)
    cfg['enabled'] = 'true'
    items, err = fetch_provider(cat, platform_key, label, cfg)
    if err and not items:
        return {'ok': False, 'message': err, 'items': []}
    return {
        'ok': True,
        'message': f'{label}试拉成功 {len(items)} 条',
        'items': [
            {'title': x.get('title'), 'likes': x.get('likes'), 'url': x.get('url')}
            for x in items[:5]
        ],
        'total': len(items),
    }
