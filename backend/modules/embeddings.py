"""
文本向量化：优先走当前启用厂商的 OpenAI 兼容 /embeddings；
不可用时回退到本地哈希向量，保证检索链路可落地。
"""

from __future__ import annotations

import hashlib
import math
import re
from typing import Iterable

import requests

from config import get_ai_config

# 各厂商常见 embedding 模型；无官方兼容接口的填空串走本地回退
EMBEDDING_MODELS = {
    'zhipu': 'embedding-2',
    'openai': 'text-embedding-3-small',
    'qwen': 'text-embedding-v2',
    'moonshot': 'text-embedding-v1',
    'deepseek': '',
    'volcano': '',
    'volcengine': '',
    'doubao': '',
}

LOCAL_DIM = 384
_CJK = re.compile(r'[\u4e00-\u9fff]')


def _l2_normalize(vec: list[float]) -> list[float]:
    norm = math.sqrt(sum(x * x for x in vec)) or 1.0
    return [x / norm for x in vec]


def local_embed(text: str, dim: int = LOCAL_DIM) -> list[float]:
    """确定性本地向量：字符/二元组哈希，中文友好，无需外部依赖。"""
    vec = [0.0] * dim
    t = (text or '').strip().lower()
    if not t:
        return vec
    for i, ch in enumerate(t):
        h = int(hashlib.md5(ch.encode('utf-8')).hexdigest(), 16) % dim
        weight = 1.6 if _CJK.match(ch) else 1.0
        vec[h] += weight
        if i + 1 < len(t):
            bigram = t[i:i + 2]
            h2 = int(hashlib.md5(bigram.encode('utf-8')).hexdigest(), 16) % dim
            vec[h2] += 1.2
    # 简单词袋
    for token in re.split(r'[\s,，。；;、！!？?：:（）()【】\[\]/\\|]+', t):
        token = token.strip()
        if len(token) < 2:
            continue
        h = int(hashlib.md5(token.encode('utf-8')).hexdigest(), 16) % dim
        vec[h] += 2.0
    return _l2_normalize(vec)


def cosine_similarity(a: list[float], b: list[float]) -> float:
    if not a or not b:
        return 0.0
    n = min(len(a), len(b))
    return sum(a[i] * b[i] for i in range(n))


def _embed_via_api(texts: list[str], config: dict) -> tuple[list[list[float]], str] | None:
    api_key = (config.get('api_key') or '').strip()
    base_url = (config.get('base_url') or '').strip().rstrip('/')
    provider = (config.get('provider') or '').strip().lower()
    model = EMBEDDING_MODELS.get(provider, '')
    if not api_key or not base_url or not model:
        return None

    url = f'{base_url}/embeddings'
    headers = {
        'Content-Type': 'application/json',
        'Authorization': f'Bearer {api_key}',
    }
    # 部分厂商一次一条更稳
    vectors: list[list[float]] = []
    try:
        # 批量优先
        payload = {'model': model, 'input': texts}
        resp = requests.post(url, json=payload, headers=headers, timeout=45)
        if resp.status_code == 200:
            data = resp.json().get('data') or []
            data = sorted(data, key=lambda x: x.get('index', 0))
            for item in data:
                emb = item.get('embedding')
                if not emb:
                    return None
                vectors.append(_l2_normalize([float(x) for x in emb]))
            if len(vectors) == len(texts):
                return vectors, model
        # 逐条重试
        vectors = []
        for text in texts:
            resp = requests.post(
                url,
                json={'model': model, 'input': text},
                headers=headers,
                timeout=45,
            )
            if resp.status_code != 200:
                return None
            data = resp.json().get('data') or []
            if not data or not data[0].get('embedding'):
                return None
            vectors.append(_l2_normalize([float(x) for x in data[0]['embedding']]))
        return vectors, model
    except Exception:
        return None


def embed_texts(texts: Iterable[str]) -> tuple[list[list[float]], str]:
    """
    Returns:
        (vectors, model_name)  model_name 为 API 模型名或以 local- 开头的本地标记
    """
    items = [((t or '')[:4000]) for t in texts]
    if not items:
        return [], 'local-empty'
    try:
        config = get_ai_config()
    except Exception:
        config = {}
    api_result = _embed_via_api(items, config or {})
    if api_result:
        return api_result
    return [local_embed(t) for t in items], f'local-hash-{LOCAL_DIM}'


def embed_query(text: str) -> tuple[list[float], str]:
    vecs, model = embed_texts([text])
    return (vecs[0] if vecs else local_embed(text)), model
