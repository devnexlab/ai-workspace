"""
AI script generation module - calls real LLM APIs.

Supported providers:
  - zhipu (智谱 GLM): https://open.bigmodel.cn
  - openai (GPT): https://api.openai.com
  - qwen (通义千问): https://dashscope.aliyuncs.com
  - deepseek (深度求索): https://api.deepseek.com
  - moonshot (月之暗面): https://api.moonshot.cn

All providers use OpenAI-compatible chat/completions API format.
The user configures provider + API key + model in Settings.
"""

import json
import re
import requests
from config import get_ai_config, get_setting


# Default base URLs for each provider
PROVIDER_URLS = {
    'zhipu': 'https://open.bigmodel.cn/api/paas/v4',
    'openai': 'https://api.openai.com/v1',
    'qwen': 'https://dashscope.aliyuncs.com/compatible-mode/v1',
    'deepseek': 'https://api.deepseek.com/v1',
    'moonshot': 'https://api.moonshot.cn/v1',
}

# Recommended models per provider
PROVIDER_MODELS = {
    'zhipu': 'glm-4-flash',
    'openai': 'gpt-4o-mini',
    'qwen': 'qwen-plus',
    'deepseek': 'deepseek-chat',
    'moonshot': 'moonshot-v1-8k',
}

DEFAULT_BRAND_ENDING = '祁实说实话，替你的保单说话，给你最放心的选择。关注我，来找我。'

# 分龄泛流量受众描述
AGE_AUDIENCE = {
    '20s': '20-29岁年轻人，关注职场起步、恋爱婚姻、租房买房、社交压力',
    '30s': '30-39岁成家立业人群，关注育儿、房贷、升职加薪、家庭责任',
    '40s': '40-49岁中年人群，关注健康预警、父母养老、子女教育、事业瓶颈',
    '50s': '50-59岁人群，关注养生、退休规划、子女成家、慢性病',
    '60s': '60-69岁退休人群，关注养老金、看病报销、隔代带娃、防骗',
    '70s': '70-79岁长辈，关注健康、子女孝顺、就医方便、防忽悠，语言要通俗慢',
    '80s': '80岁以上高龄长辈，关注陪护、慢性病、防骗、子女陪伴，语速更慢、句子更短、少用网络词',
    'all': '20-80岁泛流量用户，口语易懂，强共鸣、强分享动机，适合短视频转发',
}

CONTENT_TYPE_HINTS = {
    'traffic': (
        '这是【泛流量涨粉文案】：不硬广保险，先讲人生/家庭/健康/职场/情感共鸣话题，'
        '目标是高完播、高转发、吸引关注。结尾再自然留钩子。'
    ),
    'insurance': (
        '这是【保险专业文案】：讲避坑、理赔、家庭保障、医保与商保差异等干货，'
        '建立专业信任，但不要恐吓推销，要真诚靠谱。'
    ),
}


def call_llm(prompt, system_prompt=None, temperature=None, max_tokens=None):
    """
    Call the configured LLM.

    Returns:
        tuple: (content: str, tokens_used: int, model: str)
    """
    config = get_ai_config()
    api_key = config.get('api_key', '').strip()

    if not api_key:
        raise Exception('AI API Key 未配置，请在系统设置中填写')

    provider = config.get('provider', 'zhipu')
    base_url = config.get('base_url', '').strip() or PROVIDER_URLS.get(provider, PROVIDER_URLS['zhipu'])
    model = config.get('model', '').strip() or PROVIDER_MODELS.get(provider, 'glm-4-flash')
    temp = float(temperature) if temperature else float(config.get('temperature', '0.7'))
    max_tok = int(max_tokens) if max_tokens else int(config.get('max_tokens', '2000'))

    url = f'{base_url.rstrip("/")}/chat/completions'
    headers = {
        'Content-Type': 'application/json',
        'Authorization': f'Bearer {api_key}',
    }

    messages = []
    if system_prompt:
        messages.append({'role': 'system', 'content': system_prompt})
    messages.append({'role': 'user', 'content': prompt})

    payload = {
        'model': model,
        'messages': messages,
        'temperature': temp,
        'max_tokens': max_tok,
    }

    try:
        resp = requests.post(url, json=payload, headers=headers, timeout=60)
    except requests.exceptions.Timeout:
        raise Exception(f'AI 请求超时（60秒），请检查网络或稍后重试')
    except requests.exceptions.ConnectionError:
        raise Exception(f'无法连接到 AI 服务: {url}，请检查 base_url 配置')

    # Check if response is JSON (some proxies return HTML on wrong URL)
    content_type = resp.headers.get('Content-Type', '')
    if not content_type.startswith('application/json'):
        # If we got HTML, the base_url is likely wrong (missing /v1)
        if 'text/html' in content_type:
            raise Exception(
                f'AI 服务返回了 HTML 而非 JSON，请检查 base_url 是否正确（可能需要加 /v1）。'
                f'当前 URL: {url}'
            )
        raise Exception(
            f'AI 服务返回了非 JSON 响应 (Content-Type: {content_type})，'
            f'状态码: {resp.status_code}，响应: {resp.text[:200]}'
        )

    if resp.status_code != 200:
        try:
            err_data = resp.json()
            err_msg = err_data.get('error', {}).get('message', '') or str(err_data)
        except Exception:
            err_msg = resp.text[:300]
        raise Exception(f'AI 服务返回错误 (HTTP {resp.status_code}): {err_msg}')

    data = resp.json()
    content = data['choices'][0]['message']['content']
    tokens_used = data.get('usage', {}).get('total_tokens', 0)
    return content, tokens_used, model


# ---- Prompt templates ----

SYSTEM_PROMPT = """你是短视频口播编剧，专为保险从业者「祁实说实话」打造全网泛流量与保险干货文案。
要求：开头3秒抓人；标准成片为约60秒口播；正文（content）须写满约280-360字（汉字），朗读约55-65秒，信息量充足，不要写成短金句堆砌；
口语化、适合朗读；有观点、有例子、有递进；强共鸣可转发；结尾必须引导「关注我，来找我」，形成品牌记忆。
你只返回JSON，不要多余解释。"""

TONE_DESC = {
    'professional': '专业权威',
    'casual': '轻松口语化',
    'passionate': '激情澎湃',
    'humorous': '幽默风趣',
    'serious': '严肃认真',
    'friendly': '亲切友好',
}


def get_brand_ending():
    """读取系统固定收口，缺省用品牌默认。"""
    ending = (get_setting('system', 'fixed_ending', '') or '').strip()
    if not ending or ending.startswith('其实说实话'):
        return DEFAULT_BRAND_ENDING
    return ending


def apply_brand_ending(script):
    """强制所有文案使用统一品牌收口。"""
    ending = get_brand_ending()
    script['ending'] = ending
    # 正文末尾若未包含品牌名，轻量提示（收口字段已固定，不重复硬塞进 content）
    return script


def build_script_prompt(topic, style='干货分享', duration='60秒',
                        audience='', tone='casual', extra_req='',
                        content_type='traffic', age_band='all'):
    """Build the prompt for generating a video script from a hot topic."""
    tone_text = TONE_DESC.get(tone, tone)
    brand_ending = get_brand_ending()

    if not audience:
        audience = AGE_AUDIENCE.get(age_band, AGE_AUDIENCE['all'])
    type_hint = CONTENT_TYPE_HINTS.get(content_type, CONTENT_TYPE_HINTS['traffic'])

    audience_line = f'目标受众: {audience}\n'
    tone_line = f'语气风格: {tone_text}\n'
    extra_line = f'额外要求: {extra_req}\n' if extra_req else ''

    if isinstance(topic, dict):
        topic_block = f"""爆款标题/热点: {topic.get('title', '')}
平台: {topic.get('platform', '')}
爆款数据: 点赞{topic.get('likes', 0)} 评论{topic.get('comments', 0)} 转发{topic.get('shares', 0)}
热点分析: {topic.get('analysis', '') or '无'}"""
    else:
        topic_block = f'创作主题: {topic}'

    return f"""根据以下信息，创作一条原创短视频口播文案（适合视频号/抖音/小红书，约60秒口播）。

{topic_block}
内容类型提示: {type_hint}
风格要求: {style}
视频时长: {duration}（正文 content 必须约280-360字，按每秒约5字语速朗读约60秒；禁止少于250字）
{audience_line}{tone_line}{extra_line}
品牌固定收口（ending 字段必须原样使用，一个字都不要改）:
{brand_ending}

创作规则:
1. 结合实时热点或爆款标题做「同题异构」原创，禁止照抄原文
2. 开头 hook 必须痛点/反差/好奇，3秒留人
3. 正文结构建议：钩子承接 → 讲清一个具体现象/故事 → 给出观点或避坑 → 轻量行动建议；口语化，中老年也能听懂
4. 多用短句，可有口语停顿感（“你看”“说实话”“很多人不知道”），但字数必须写够
5. 泛流量文案不要上来就卖保险；保险文案用案例/避坑建立信任
6. ending 必须等于上面的品牌固定收口原文
7. content 字段不要偷懒缩写，不要只写提纲式几句

请返回JSON（只返回JSON）:
{{
  "title": "视频标题（吸引眼球，15字以内）",
  "hook": "开头3秒钩子（一句话）",
  "content": "正文口播（280-360字，口语化，完整可朗读约60秒）",
  "ending": "{brand_ending}",
  "cover_text": "封面大字（5-10字）",
  "tags": "标签，逗号分隔，3-5个"
}}"""


def build_rewrite_prompt(script_text, style='更口语化'):
    """Build prompt for rewriting an existing script."""
    brand_ending = get_brand_ending()
    return f"""重写以下短视频文案，要求{style}，标准成片约60秒口播。

原文案:
{script_text}

要求：正文 content 约280-360字（不少于250字），口语化、信息完整，适合朗读约60秒。
ending 必须原样使用：{brand_ending}

请返回JSON格式（只返回JSON）:
{{
  "title": "标题",
  "hook": "开头钩子",
  "content": "正文内容（280-360字）",
  "ending": "{brand_ending}",
  "cover_text": "封面文案",
  "tags": "标签"
}}"""


def _to_str(val):
    """Ensure a value is a string (LLMs sometimes return lists for tags etc.)."""
    if isinstance(val, list):
        return ','.join(str(v) for v in val)
    if isinstance(val, (int, float, bool)):
        return str(val)
    return val or ''


def parse_script_response(result):
    """Parse the LLM response into structured script data."""
    json_match = re.search(r'\{[\s\S]*\}', result)
    if json_match:
        try:
            data = json.loads(json_match.group())
            return {
                'title': _to_str(data.get('title', '')),
                'hook': _to_str(data.get('hook', '')),
                'content': _to_str(data.get('content', '')),
                'ending': _to_str(data.get('ending', '')),
                'cover_text': _to_str(data.get('cover_text', '')),
                'tags': _to_str(data.get('tags', '')),
            }
        except json.JSONDecodeError:
            pass

    return {
        'title': 'AI生成文案',
        'hook': '',
        'content': result[:500],
        'ending': '',
        'cover_text': '',
        'tags': '',
    }


def generate_script(topic, style='干货分享', duration='60秒',
                    audience='', tone='casual', extra_req='',
                    content_type='traffic', age_band='all'):
    """
    Generate a complete video script from a hot topic.
    Always applies brand fixed ending.
    """
    prompt = build_script_prompt(
        topic, style, duration, audience, tone, extra_req,
        content_type=content_type, age_band=age_band,
    )
    result, tokens, model = call_llm(prompt, system_prompt=SYSTEM_PROMPT)
    script = parse_script_response(result)
    apply_brand_ending(script)
    script['tokens_used'] = tokens
    script['model_name'] = model
    script['content_type'] = content_type
    script['age_band'] = age_band
    return script


def rewrite_script(script_text, style='更口语化'):
    """Rewrite an existing script in a different style."""
    prompt = build_rewrite_prompt(script_text, style)
    result, tokens, model = call_llm(prompt, system_prompt=SYSTEM_PROMPT)
    script = parse_script_response(result)
    apply_brand_ending(script)
    script['tokens_used'] = tokens
    script['model_name'] = model
    return script


# ============================================================
# AI Narration Rewrite - transform script into natural spoken narration
# ============================================================

NARRATION_SYSTEM_PROMPT = """你是一个专业的短视频旁白编剧，擅长将文案改写为适合语音朗读的自然口播文本。
你的改写特点：
- 口语化，像跟朋友聊天一样自然
- 有节奏感和情感起伏，不是照本宣科
- 适合AI语音合成，读起来流畅自然
你只返回纯文本旁白内容，不要包含任何标注、说明或格式标记。"""


NARRATION_PRESETS = {
    'storytelling': '用讲故事的口吻，像在跟朋友分享一个有趣的发现，语气亲切自然，有悬念和情感起伏',
    'documentary': '模仿纪录片旁白，沉稳大气，有深度感，节奏舒缓但有力量',
    'energetic': '热情激动，像直播带货一样有感染力，语速稍快，充满能量',
    'suspense': '悬疑推理风格，制造紧张感，节奏有张有弛，关键信息前适当停顿',
    'casual': '轻松随意，像日常聊天，偶尔加入语气词，不做作不刻意',
    'professional': '专业但不生硬，像行业专家在做分享，有权威感但平易近人',
    'emotional': '走心感人，语速偏慢，有情感共鸣，适合励志或温情类内容',
    'humorous': '幽默风趣，像段子手在讲故事，轻松好笑但有干货',
}


def build_narration_prompt(script_data, narration_prompt):
    """Build the prompt for AI to rewrite script as natural narration.

    Args:
        script_data: dict with hook, content, ending, title
        narration_prompt: user's custom prompt controlling narration style

    Returns:
        prompt string for the LLM
    """
    original_text = ''
    if script_data.get('hook'):
        original_text += script_data['hook'] + '\n'
    if script_data.get('content'):
        original_text += script_data['content']
    if script_data.get('ending'):
        original_text += '\n' + script_data['ending']

    return f"""将以下短视频文案改写为自然流畅的口播旁白文本。

改写要求：
{narration_prompt}

改写规则：
1. 适合语音朗读，口语化，有节奏感和情感起伏
2. 不要照本宣科地念稿子，要像讲故事、聊天一样自然
3. 可以适当加入语气词和过渡语（如"你知道吗"、"其实啊"、"说真的"、"你想想看"等）
4. 保持核心信息和价值不变，但表达方式更生动自然
5. 可以适当调整句子长短搭配，短句更有力量感
6. 不要添加任何标注、说明、括号注释或舞台指示
7. 只返回纯文本旁白内容
8. 保持适当长度，不要大幅增加或减少字数

原文案：
{original_text}

请直接返回改写后的旁白文本："""


def generate_narration(script_data, narration_prompt):
    """
    Use AI to transform script into a natural narration style.

    Instead of reading the script word-by-word, this rewrites the text
    into a conversational, storytelling format that sounds human when
    read by TTS.

    Args:
        script_data: dict with hook, content, ending, title
        narration_prompt: user's custom prompt for narration style
                         (e.g. "用讲故事的口吻，加入悬念")

    Returns:
        str: the rewritten narration text
    """
    prompt = build_narration_prompt(script_data, narration_prompt)
    result, tokens, model = call_llm(
        prompt,
        system_prompt=NARRATION_SYSTEM_PROMPT,
        temperature=0.8,  # Slightly higher temperature for more creative narration
        max_tokens=2000,
    )

    # Clean up the result: remove any markdown formatting, extra whitespace
    narration = result.strip()
    # Remove potential markdown code blocks
    narration = re.sub(r'^```[a-z]*\n?', '', narration)
    narration = re.sub(r'\n?```$', '', narration)
    # Remove any stage direction brackets like [暂停] (停顿) etc.
    narration = re.sub(r'[\[【(]\s*(暂停|停顿|语气|强调|缓慢|快速|激昂|低沉|停)\s*[\]】)]', '', narration)
    # Normalize whitespace
    narration = re.sub(r'\n{3,}', '\n\n', narration).strip()

    return narration


# ============================================================
# AI Scene Segmentation - split narration into visual scenes with material matching
# ============================================================

SCENE_SYSTEM_PROMPT = """你是一个专业的短视频分镜师，擅长将旁白文本拆分为视觉场景段落。
你的任务：
1. 将旁白按语义拆分为3-8个场景（每个场景1-3句话）
2. 为每个场景提取关键词，用于匹配画面素材
3. 根据可用素材列表，为每个场景匹配最合适的素材
你只返回JSON数组格式，不要有多余解释。"""


def build_scene_prompt(narration_text, materials_info=None):
    """Build prompt for AI scene segmentation with material matching.

    Args:
        narration_text: the full narration text to split
        materials_info: list of {index, name, type, tags} for matching
    """
    # Build material list description
    if materials_info:
        mat_lines = []
        for m in materials_info:
            tags_str = f' (标签: {m["tags"]})' if m.get('tags') else ''
            mat_lines.append(f'{m["index"]}. [{m["type"]}] {m["name"]}{tags_str}')
        material_block = f"""可用素材列表：
{chr(10).join(mat_lines)}

请为每个场景从素材列表中选择最匹配的素材（填material_index为素材序号，从0开始）。"""
    else:
        material_block = "无可用素材，material_index填-1。"

    return f"""将以下旁白文本拆分为视觉场景段落。

旁白文本：
{narration_text}

{material_block}

拆分规则：
1. 按语义自然断句，每个场景1-3句话，保持旁白原文不变
2. 场景数3-8个，根据旁白长度灵活调整
3. 每个场景提取2-4个关键词，用于画面匹配
4. 尽量让每个素材都被使用，不要重复使用同一素材（除非素材数少于场景数）
5. scene_text必须是旁白原文的子串，不要改写

请返回JSON数组（只返回JSON）：
[
  {{
    "text": "场景旁白文本（原文片段）",
    "keywords": ["关键词1", "关键词2"],
    "material_index": 0,
    "visual_desc": "建议画面描述"
  }}
]"""


def generate_scenes(narration_text, materials_info=None):
    """
    Use AI to split narration into visual scenes with material matching.

    Args:
        narration_text: the full narration text
        materials_info: list of {index, name, type, tags} for auto-matching
                       (if None or empty, scenes are generated without material assignment)

    Returns:
        list of scene dicts: {index, text, keywords, material_index, visual_desc}
    """
    prompt = build_scene_prompt(narration_text, materials_info)
    result, tokens, model = call_llm(
        prompt,
        system_prompt=SCENE_SYSTEM_PROMPT,
        temperature=0.5,
        max_tokens=3000,
    )

    # Parse JSON array from response
    scenes = _parse_scenes_response(result, narration_text)

    print(f'[AI] Generated {len(scenes)} scenes (model={model}, tokens={tokens})')
    return scenes


def _parse_scenes_response(result, narration_text):
    """Parse AI response into scene list.

    Handles JSON wrapped in markdown code blocks.
    Falls back to simple sentence splitting if parsing fails.
    """
    # Try to extract JSON array from response
    json_match = re.search(r'\[[\s\S]*\]', result)
    if json_match:
        try:
            data = json.loads(json_match.group())
            scenes = []
            for i, item in enumerate(data):
                scene = {
                    'index': i,
                    'text': _to_str(item.get('text', '')).strip(),
                    'keywords': item.get('keywords', []) if isinstance(item.get('keywords'), list) else [],
                    'material_index': int(item.get('material_index', -1)),
                    'visual_desc': _to_str(item.get('visual_desc', '')),
                }
                if scene['text']:
                    scenes.append(scene)

            if scenes:
                # Verify scene texts cover the narration
                combined = ''.join(s['text'] for s in scenes)
                if len(combined) < len(narration_text) * 0.7:
                    print(f'[AI] Warning: scenes only cover {len(combined)}/{len(narration_text)} chars of narration')
                return scenes
        except (json.JSONDecodeError, ValueError) as e:
            print(f'[AI] Scene JSON parse error: {e}')

    # Fallback: split by sentences
    print('[AI] Scene parsing failed, falling back to sentence splitting')
    sentences = re.split(r'([。！？!?\n]+)', narration_text)
    raw_sents = []
    for i in range(0, len(sentences) - 1, 2):
        s = (sentences[i] + (sentences[i + 1] if i + 1 < len(sentences) else '')).strip()
        if s:
            raw_sents.append(s)

    # Group sentences into scenes (2 per scene)
    scenes = []
    for i in range(0, len(raw_sents), 2):
        text = ' '.join(raw_sents[i:i + 2])
        scenes.append({
            'index': len(scenes),
            'text': text,
            'keywords': [],
            'material_index': -1,
            'visual_desc': '',
        })

    return scenes


def auto_match_materials(scenes, materials_info):
    """
    Auto-match materials to scenes using keyword similarity.

    For each scene, finds the best matching material based on keyword overlap
    with material name and tags. Ensures materials are distributed evenly.

    Args:
        scenes: list of scene dicts with 'keywords'
        materials_info: list of {index, name, type, tags}

    Returns:
        Updated scenes with material_index assigned
    """
    if not materials_info:
        return scenes

    n_materials = len(materials_info)
    used_indices = set()

    for scene in scenes:
        best_idx = -1
        best_score = 0

        for mat in materials_info:
            if mat['index'] in used_indices and len(used_indices) < n_materials:
                continue  # Try to use unused materials first

            # Calculate match score based on keyword overlap
            mat_name = mat.get('name', '').lower()
            mat_tags = mat.get('tags', '').lower()
            mat_tags_list = [t.strip().lower() for t in mat_tags.split(',') if t.strip()]

            score = 0
            for kw in scene.get('keywords', []):
                kw_lower = kw.lower()
                if kw_lower in mat_name:
                    score += 3
                if kw_lower in mat_tags:
                    score += 2
                for tag in mat_tags_list:
                    if kw_lower in tag or tag in kw_lower:
                        score += 2

            if score > best_score:
                best_score = score
                best_idx = mat['index']

        # If no keyword match and we have unused materials, assign round-robin
        if best_idx == -1:
            for mat in materials_info:
                if mat['index'] not in used_indices:
                    best_idx = mat['index']
                    break

        # If all materials used, allow reuse (round-robin from start)
        if best_idx == -1 and materials_info:
            best_idx = materials_info[len(used_indices) % n_materials]['index']

        scene['material_index'] = best_idx
        if best_idx not in used_indices:
            used_indices.add(best_idx)

    return scenes
