"""
Video production module - real TTS, subtitle generation, and video composition.

Pipeline:
  1. TTS: Convert script text -> audio (MP3) using edge-tts (free) or Azure/Volcano
     - Captures WordBoundary events for precise subtitle sync
  2. Subtitle: Generate SRT subtitles from TTS word boundary timestamps
     - Falls back to even distribution if no boundary data
  3. Compose: Combine background + audio + styled subtitles -> MP4 using FFmpeg
     - Animated gradient background, styled subtitles, fade transitions

All configurable via Settings page.
"""

import os
import re
import json
import math
import random
import asyncio
import subprocess
import tempfile
import shutil
from config import get_tts_config, get_video_config


# ============================================================
# Voice options for TTS
# ============================================================

# 仅保留 Microsoft Edge TTS 当前仍可用的中文音色（2026 起大量 Neural 已下线）
VOICE_OPTIONS = {
    'zh-CN-YunxiNeural': '云希（男声·温暖知性）',
    'zh-CN-XiaoxiaoNeural': '晓晓（女声·亲切自然）',
    'zh-CN-YunyangNeural': '云扬（男声·新闻播音）',
    'zh-CN-XiaoyiNeural': '晓伊（女声·温柔甜美）',
    'zh-CN-YunjianNeural': '云健（男声·激情有力）',
    'zh-CN-YunxiaNeural': '云夏（男声·少年清澈）',
    'zh-CN-liaoning-XiaobeiNeural': '晓北（女声·辽宁口音）',
    'zh-CN-shaanxi-XiaoniNeural': '晓妮（女声·陕西口音）',
}

# 已下线音色 → 近似替代，避免偏好/旧任务继续报 No audio
_DEPRECATED_VOICE_MAP = {
    'zh-CN-XiaoqiuNeural': 'zh-CN-XiaoxiaoNeural',
    'zh-CN-XiaochenNeural': 'zh-CN-XiaoxiaoNeural',
    'zh-CN-XiaohanNeural': 'zh-CN-XiaoxiaoNeural',
    'zh-CN-XiaomengNeural': 'zh-CN-XiaoyiNeural',
    'zh-CN-XiaomoNeural': 'zh-CN-XiaoyiNeural',
    'zh-CN-XiaoruiNeural': 'zh-CN-XiaoxiaoNeural',
    'zh-CN-XiaoshuangNeural': 'zh-CN-XiaoyiNeural',
    'zh-CN-XiaoxuanNeural': 'zh-CN-XiaoyiNeural',
    'zh-CN-XiaoyanNeural': 'zh-CN-XiaoxiaoNeural',
    'zh-CN-XiaozhenNeural': 'zh-CN-XiaoxiaoNeural',
    'zh-CN-YunfengNeural': 'zh-CN-YunxiNeural',
    'zh-CN-YunhaoNeural': 'zh-CN-YunyangNeural',
    'zh-CN-YunzeNeural': 'zh-CN-YunjianNeural',
}

_DEFAULT_EDGE_VOICE = 'zh-CN-YunxiNeural'
_EDGE_VOICES_CACHE = {'ts': 0, 'names': set(VOICE_OPTIONS.keys())}


# ============================================================
# Video Style Presets
# ============================================================

VIDEO_STYLES = {
    'default': {
        'name': '默认',
        'bg_color': '#1a1a2e',
        'subtitle_color': '&H00FFFFFF',
        'subtitle_outline_color': '&H00000000',
        'subtitle_size': '28',
        'subtitle_font': 'Microsoft YaHei',
        'subtitle_margin_v': '100',
        'video_filter': '',
        'title_color': 'white@0.9',
        'letterbox': False,
        'vignette': False,
    },
    'cyberpunk': {
        'name': '赛博朋克',
        'bg_color': '#0a0a1a',
        'subtitle_color': '&H00FFFF00',
        'subtitle_outline_color': '&H00000000',
        'subtitle_size': '30',
        'subtitle_font': 'Microsoft YaHei',
        'subtitle_margin_v': '100',
        'video_filter': 'eq=contrast=1.2:saturation=1.5:gamma=0.9,hue=h=10:s=1.3',
        'title_color': 'cyan@0.9',
        'letterbox': False,
        'vignette': True,
    },
    'punk': {
        'name': '朋克风格',
        'bg_color': '#1a0505',
        'subtitle_color': '&H000055FF',
        'subtitle_outline_color': '&H00000000',
        'subtitle_size': '32',
        'subtitle_font': 'SimHei',
        'subtitle_margin_v': '100',
        'video_filter': 'eq=contrast=1.4:saturation=1.3:gamma=0.85',
        'title_color': '#FF5530@0.9',
        'letterbox': False,
        'vignette': True,
    },
    'minimalist': {
        'name': '极简风格',
        'bg_color': '#f5f5f5',
        'subtitle_color': '&H00000000',
        'subtitle_outline_color': '&H00FFFFFF',
        'subtitle_size': '26',
        'subtitle_font': 'Microsoft YaHei',
        'subtitle_margin_v': '120',
        'video_filter': 'eq=contrast=0.95:saturation=0.8',
        'title_color': 'black@0.8',
        'letterbox': False,
        'vignette': False,
    },
    'vintage': {
        'name': '复古风格',
        'bg_color': '#2a1f14',
        'subtitle_color': '&H00C0D7FF',
        'subtitle_outline_color': '&H00000000',
        'subtitle_size': '28',
        'subtitle_font': 'KaiTi',
        'subtitle_margin_v': '100',
        'video_filter': 'eq=contrast=1.1:saturation=0.6:gamma=1.1,hue=h=20:s=0.7',
        'title_color': '#D7A96C@0.9',
        'letterbox': False,
        'vignette': True,
    },
    'tech': {
        'name': '科技风格',
        'bg_color': '#0a1929',
        'subtitle_color': '&H00FFCC00',
        'subtitle_outline_color': '&H00000000',
        'subtitle_size': '28',
        'subtitle_font': 'Microsoft YaHei',
        'subtitle_margin_v': '100',
        'video_filter': 'eq=contrast=1.15:saturation=1.2:gamma=0.95',
        'title_color': '#00CCFF@0.9',
        'letterbox': False,
        'vignette': False,
    },
    'warm': {
        'name': '温暖风格',
        'bg_color': '#2a1a10',
        'subtitle_color': '&H00E0E0E0',
        'subtitle_outline_color': '&H00000000',
        'subtitle_size': '28',
        'subtitle_font': 'Microsoft YaHei',
        'subtitle_margin_v': '100',
        'video_filter': 'eq=contrast=1.05:saturation=1.1:gamma=1.05,hue=h=5:s=1.1',
        'title_color': '#FFD7A0@0.9',
        'letterbox': False,
        'vignette': False,
    },
    'cinematic': {
        'name': '电影风格',
        'bg_color': '#0a0a0a',
        'subtitle_color': '&H00FFFFFF',
        'subtitle_outline_color': '&H00000000',
        'subtitle_size': '26',
        'subtitle_font': 'Microsoft YaHei',
        'subtitle_margin_v': '130',
        'video_filter': 'eq=contrast=1.2:saturation=0.9:gamma=0.95',
        'title_color': 'white@0.85',
        'letterbox': True,
        'vignette': True,
    },
    'nature': {
        'name': '自然风格',
        'bg_color': '#0a1a0a',
        'subtitle_color': '&H00C0FFC0',
        'subtitle_outline_color': '&H00000000',
        'subtitle_size': '28',
        'subtitle_font': 'Microsoft YaHei',
        'subtitle_margin_v': '100',
        'video_filter': 'eq=contrast=1.1:saturation=1.15:gamma=1.0',
        'title_color': '#A0D080@0.9',
        'letterbox': False,
        'vignette': False,
    },
    'business': {
        'name': '商务风格',
        'bg_color': '#0F1B2D',
        'subtitle_color': '&H00FFFFFF',
        'subtitle_outline_color': '&H00002040',
        'subtitle_size': '28',
        'subtitle_font': 'Microsoft YaHei',
        'subtitle_margin_v': '100',
        'video_filter': 'eq=contrast=1.1:saturation=0.95:gamma=0.98',
        'title_color': '#A0B4C8@0.9',
        'letterbox': False,
        'vignette': False,
    },
}


def get_style_config(video_style='default'):
    """Get video style configuration.

    If style is 'default', uses user's global video settings from database.
    Otherwise, uses the style preset values.
    """
    config = get_video_config()

    if video_style == 'default' or video_style not in VIDEO_STYLES:
        return {
            'bg_color': _hex_to_ffmpeg_color(config.get('bg_color', '#1a1a2e')),
            'subtitle_color': config.get('subtitle_color', '&H00FFFFFF'),
            'subtitle_outline_color': config.get('subtitle_outline_color', '&H00000000'),
            'subtitle_size': config.get('subtitle_size', '28'),
            'subtitle_font': config.get('subtitle_font', 'Microsoft YaHei'),
            'subtitle_margin_v': config.get('subtitle_margin_v', '100'),
            'video_filter': '',
            'title_color': 'white@0.9',
            'letterbox': False,
            'vignette': False,
        }

    style = VIDEO_STYLES[video_style]
    return {
        'bg_color': _hex_to_ffmpeg_color(style['bg_color']),
        'subtitle_color': style['subtitle_color'],
        'subtitle_outline_color': style['subtitle_outline_color'],
        'subtitle_size': style['subtitle_size'],
        'subtitle_font': style['subtitle_font'],
        'subtitle_margin_v': style['subtitle_margin_v'],
        'video_filter': style.get('video_filter', ''),
        'title_color': style.get('title_color', 'white@0.9'),
        'letterbox': style.get('letterbox', False),
        'vignette': style.get('vignette', False),
    }


def get_available_styles():
    """Return list of available video styles for API."""
    return [{'key': k, 'name': v['name']} for k, v in VIDEO_STYLES.items()]


# ============================================================
# 1. TTS (Text-to-Speech) with natural delivery
# ============================================================

def generate_tts(text, output_path, voice=None, rate=None, volume=None):
    """
    Convert text to speech audio file with natural delivery.

    Uses edge-tts by default (free, no API key needed).
    Splits text into sentences and generates TTS for each segment with
    slight rate variation and pauses between sentences for a more natural,
    human-like delivery.

    Args:
        text: the script text to narrate
        output_path: path to save the audio file (.mp3)
        voice: override voice (if None, uses system setting)
        rate: override rate (if None, uses system setting)
        volume: override volume (if None, uses system setting)

    Returns:
        dict with: duration (seconds), audio_path, word_boundaries
    """
    if not (text or '').strip():
        raise Exception('配音文案为空，无法生成语音')

    config = get_tts_config()
    provider = config.get('provider', 'edge')
    use_voice = _normalize_edge_voice(voice or config.get('voice') or 'zh-CN-YunxiNeural')
    use_rate = _normalize_edge_rate(rate if rate not in (None, '') else config.get('rate'))
    use_volume = _normalize_edge_volume(volume if volume not in (None, '') else config.get('volume'))

    if provider == 'azure':
        return _tts_azure(text, output_path, config)
    elif provider == 'volcano':
        return _tts_volcano(text, output_path, config)
    else:
        try:
            return _tts_edge_natural(text, output_path, use_voice, use_rate, use_volume)
        except Exception as e:
            err = str(e)
            # 参数异常时回退默认音色/语速再试一次（常见于偏好里存了非法 rate/voice）
            if 'No audio was received' in err or 'parameters are correct' in err:
                print(f'[TTS] edge-tts failed ({use_voice}, {use_rate}): {e}; retry defaults')
                fallback_voice = 'zh-CN-YunxiNeural'
                fallback_rate = '+0%'
                fallback_volume = '+0%'
                if use_voice != fallback_voice or use_rate != fallback_rate:
                    return _tts_edge_natural(
                        text, output_path, fallback_voice, fallback_rate, fallback_volume,
                    )
            raise Exception(
                f'配音失败: {err}。请检查网络能否访问 Edge TTS，'
                f'或到系统设置确认音色/语速格式（如 zh-CN-YunxiNeural、+0%）'
            ) from e


def _refresh_edge_voices(force=False):
    """Refresh available Edge TTS zh-CN voice names (cached ~24h)."""
    import time
    now = time.time()
    if not force and _EDGE_VOICES_CACHE['names'] and now - _EDGE_VOICES_CACHE['ts'] < 86400:
        return _EDGE_VOICES_CACHE['names']
    try:
        import edge_tts

        async def _list():
            voices = await edge_tts.list_voices()
            return {
                v['ShortName']
                for v in voices
                if str(v.get('ShortName') or '').startswith('zh-CN')
            }

        names = asyncio.run(_list())
        if names:
            _EDGE_VOICES_CACHE['names'] = names
            _EDGE_VOICES_CACHE['ts'] = now
            print(f'[TTS] Refreshed edge voices: {len(names)} zh-CN')
    except Exception as e:
        print(f'[TTS] list_voices failed: {e}')
    return _EDGE_VOICES_CACHE['names'] or set(VOICE_OPTIONS.keys())


def _normalize_edge_voice(voice):
    """Map label / unknown / deprecated voice to a currently available Edge voice."""
    v = (voice or '').strip()
    if not v:
        return _DEFAULT_EDGE_VOICE

    # 已下线音色先映射
    if v in _DEPRECATED_VOICE_MAP:
        mapped = _DEPRECATED_VOICE_MAP[v]
        print(f'[TTS] Deprecated voice "{v}" -> "{mapped}"')
        v = mapped

    available = _refresh_edge_voices()
    if v in available:
        return v
    if v in VOICE_OPTIONS and v in available:
        return v

    # 允许用中文标签反查
    for key, label in VOICE_OPTIONS.items():
        if v == label or v in label or label in v:
            if key in available or not available:
                return key

    aliases = {
        'yunxi': 'zh-CN-YunxiNeural',
        'xiaoxiao': 'zh-CN-XiaoxiaoNeural',
        'yunyang': 'zh-CN-YunyangNeural',
        'xiaoyi': 'zh-CN-XiaoyiNeural',
        'yunjian': 'zh-CN-YunjianNeural',
        'yunxia': 'zh-CN-YunxiaNeural',
        'xiaoqiu': 'zh-CN-XiaoxiaoNeural',
    }
    low = v.lower()
    for k, mapped in aliases.items():
        if k in low:
            return mapped if mapped in available or not available else _DEFAULT_EDGE_VOICE

    print(f'[TTS] Unknown/unavailable voice "{voice}", fallback to {_DEFAULT_EDGE_VOICE}')
    return _DEFAULT_EDGE_VOICE


def get_voice_options_for_api():
    """Return voice dropdown options, preferring live Edge TTS list."""
    available = _refresh_edge_voices()
    items = []
    for key, label in VOICE_OPTIONS.items():
        if not available or key in available:
            items.append({'value': key, 'label': label})
    # 把线上有、本地表没有的补上
    for name in sorted(available or []):
        if name not in VOICE_OPTIONS:
            items.append({'value': name, 'label': name})
    if not items:
        items = [{'value': k, 'label': v} for k, v in VOICE_OPTIONS.items()]
    return items


def _normalize_edge_rate(rate):
    """edge-tts 需要类似 +0% / -5% / +10% 的相对语速。"""
    if rate is None or rate == '':
        return '+0%'
    s = str(rate).strip().replace(' ', '')
    m = re.match(r'^([+-]?)(\d+(?:\.\d+)?)(%?)$', s)
    if m:
        sign, num, pct = m.group(1), m.group(2), m.group(3)
        val = float(num)
        # 1.0 / 0.9 这类倍率误填 → 当作默认
        if not pct and 0 < val <= 2 and '.' in num:
            return '+0%'
        ival = int(round(val))
        ival = max(-50, min(100, ival))
        if not sign:
            sign = '+' if ival >= 0 else ''
        # 0 必须带 +
        if ival == 0:
            return '+0%'
        return f'{sign}{abs(ival)}%' if sign == '-' else f'+{ival}%'
    print(f'[TTS] Invalid rate "{rate}", fallback to +0%')
    return '+0%'


def _normalize_edge_volume(volume):
    if volume is None or volume == '':
        return '+0%'
    s = str(volume).strip().replace(' ', '')
    m = re.match(r'^([+-]?)(\d+(?:\.\d+)?)(%?)$', s)
    if m:
        sign, num, _pct = m.group(1), m.group(2), m.group(3)
        ival = int(round(float(num)))
        ival = max(-50, min(100, ival))
        if ival == 0:
            return '+0%'
        if not sign:
            sign = '+'
        return f'{sign}{abs(ival)}%' if sign == '-' else f'+{ival}%'
    return '+0%'


def _split_sentences(text):
    """Split text into natural sentences for TTS segmentation.

    Splits on Chinese/English sentence endings, then further splits
    long sentences at commas to keep TTS segments manageable.
    """
    # First split on sentence endings (keeping delimiters)
    parts = re.split(r'([。！？!?\n]+)', text)
    raw_sentences = []
    for i in range(0, len(parts) - 1, 2):
        sent = (parts[i] + (parts[i + 1] if i + 1 < len(parts) else '')).strip()
        if sent:
            raw_sentences.append(sent)
    if len(parts) % 2 == 1 and parts[-1].strip():
        raw_sentences.append(parts[-1].strip())

    # Further split very long sentences at commas
    sentences = []
    for sent in raw_sentences:
        if len(sent) > 80:
            sub_parts = re.split(r'([，,；;、]+)', sent)
            current = ''
            for part in sub_parts:
                current += part
                if part and part[0] in '，,；;、' and len(current) > 40:
                    sentences.append(current.strip())
                    current = ''
            if current.strip():
                sentences.append(current.strip())
        else:
            sentences.append(sent)

    return [s for s in sentences if s]


def _adjust_rate(base_rate, adjustment):
    """Adjust a rate string like '+0%' by an adjustment like '+5%'.

    Clamps result to [-50%, +50%] range.
    """
    try:
        base_val = int(base_rate.replace('%', '').replace('+', ''))
        adj_val = int(adjustment.replace('%', '').replace('+', ''))
        new_val = max(-50, min(50, base_val + adj_val))
        return f'{new_val:+d}%'
    except Exception:
        return base_rate


def _tts_edge_natural(text, output_path, voice, rate, volume):
    """Generate natural-sounding TTS with sentence-level pauses and rate variation.

    Splits text into sentences, generates TTS for each with slight rate
    variation (hook faster, ending slower, middle with micro-random variation),
    then concatenates with 400ms pauses between segments.

    Word boundary timestamps are adjusted to account for segment offsets
    and pause durations, ensuring subtitle sync remains accurate.
    """
    sentences = _split_sentences(text)

    # If only one sentence or splitting failed, use simple TTS
    if len(sentences) <= 1:
        return _tts_edge(text, output_path, voice, rate, volume)

    print(f'[TTS] Natural mode: {len(sentences)} sentences, voice={voice}, rate={rate}')

    pause_duration = 0.4  # 400ms pause between sentences
    segment_dir = os.path.dirname(output_path)
    segment_paths = []
    all_boundaries = []
    sentence_timings = []  # [{index, text, start, end}] for scene mapping
    cumulative_offset_100ns = 0  # in 100-nanosecond units
    cumulative_time_sec = 0.0  # in seconds

    for i, sentence in enumerate(sentences):
        if not sentence.strip():
            continue

        # Rate variation for natural delivery:
        # - First 1-2 sentences (hook): slightly faster (+5%) for energy
        # - Last 1-2 sentences (ending): slightly slower (-5%) for emphasis
        # - Middle sentences: micro-random variation (±2%) for naturalness
        if i < 2:
            seg_rate = _adjust_rate(rate, '+5%')
        elif i >= len(sentences) - 2:
            seg_rate = _adjust_rate(rate, '-5%')
        else:
            variation = random.choice(['+0%', '+2%', '-2%', '+0%', '+1%', '-1%'])
            seg_rate = _adjust_rate(rate, variation)

        seg_path = os.path.join(segment_dir, f'_tts_seg_{i:03d}.mp3')
        try:
            seg_result = _tts_edge(sentence, seg_path, voice, seg_rate, volume)
        except Exception as e1:
            # 部分音色对非 0 语速极敏感；已下线音色也会在此暴露
            print(f'[TTS] segment {i} failed ({seg_rate}): {e1}; retry +0%')
            try:
                seg_result = _tts_edge(sentence, seg_path, voice, '+0%', volume)
            except Exception as e2:
                print(f'[TTS] segment {i} retry failed: {e2}; fallback Yunxi')
                seg_result = _tts_edge(
                    sentence, seg_path, _DEFAULT_EDGE_VOICE, '+0%', volume,
                )

        if seg_result['duration'] <= 0:
            print(f'[TTS] Warning: segment {i} has 0 duration, skipping')
            continue

        # Track sentence timing for scene mapping
        sent_start = cumulative_time_sec
        sent_end = sent_start + seg_result['duration']
        sentence_timings.append({
            'index': i,
            'text': sentence,
            'start': sent_start,
            'end': sent_end,
        })

        # Adjust word boundary timestamps for this segment
        for wb in seg_result.get('word_boundaries', []):
            all_boundaries.append({
                'offset': wb['offset'] + cumulative_offset_100ns,
                'duration': wb['duration'],
                'text': wb['text'],
            })

        segment_paths.append(seg_path)

        # Update cumulative offset: segment duration + pause
        seg_duration_100ns = int(seg_result['duration'] * 10_000_000)
        cumulative_offset_100ns += seg_duration_100ns
        cumulative_time_sec += seg_result['duration']
        if i < len(sentences) - 1:
            cumulative_offset_100ns += int(pause_duration * 10_000_000)
            cumulative_time_sec += pause_duration

    if not segment_paths:
        # Fallback: single TTS call
        return _tts_edge(text, output_path, voice, rate, volume)

    # Concatenate audio segments with pauses
    _concat_audio_segments(segment_paths, pause_duration, output_path)

    # Cleanup segment files
    for seg_path in segment_paths:
        try:
            os.remove(seg_path)
        except OSError:
            pass

    duration = _get_audio_duration(output_path)
    if duration <= 0:
        # Fallback: estimate from segment durations + pauses
        duration = cumulative_offset_100ns / 10_000_000

    print(f'[TTS] Natural TTS done: {len(sentences)} segments, {duration:.1f}s total, {len(all_boundaries)} boundaries')

    return {
        'audio_path': output_path,
        'duration': duration,
        'provider': 'edge',
        'word_boundaries': all_boundaries,
        'sentence_timings': sentence_timings,
    }


def _concat_audio_segments(segment_paths, pause_duration, output_path):
    """Concatenate audio segments with silence pauses using FFmpeg.

    Uses FFmpeg's concat filter to join segments with generated silence
    between them. All segments are re-encoded to ensure compatibility.
    """
    ffmpeg = _get_ffmpeg_path()

    # Build FFmpeg command with concat filter
    inputs = []
    filter_parts = []
    input_idx = 0

    for i, seg in enumerate(segment_paths):
        inputs.extend(['-i', seg])
        filter_parts.append(f'[{input_idx}:a]')
        input_idx += 1
        if i < len(segment_paths) - 1:
            # Insert silence between segments
            inputs.extend(['-f', 'lavfi', '-i', f'anullsrc=r=24000:cl=mono:d={pause_duration}'])
            filter_parts.append(f'[{input_idx}:a]')
            input_idx += 1

    n = len(filter_parts)
    filter_complex = ''.join(filter_parts) + f'concat=n={n}:v=0:a=1[out]'

    cmd = [ffmpeg] + inputs + [
        '-filter_complex', filter_complex,
        '-map', '[out]',
        '-c:a', 'libmp3lame', '-b:a', '128k',
        '-ar', '24000',
        output_path, '-y',
    ]

    result = subprocess.run(cmd, capture_output=True, text=True, timeout=120)

    if result.returncode != 0:
        # Fallback: concatenate without pauses (direct copy)
        print(f'[TTS] Concat with pauses failed, trying simple concat: {result.stderr[-300:]}')
        list_path = output_path.replace('.mp3', '_concat.txt')
        with open(list_path, 'w') as f:
            for seg in segment_paths:
                seg_escaped = seg.replace('\\', '/').replace("'", "\\'")
                f.write(f"file '{seg_escaped}'\n")

        cmd_simple = [ffmpeg, '-f', 'concat', '-safe', '0', '-i', list_path,
                      '-c', 'copy', output_path, '-y']
        result = subprocess.run(cmd_simple, capture_output=True, text=True, timeout=60)
        try:
            os.remove(list_path)
        except OSError:
            pass

        if result.returncode != 0:
            raise Exception(f'Audio concatenation failed: {result.stderr[-500:]}')


def _tts_edge(text, output_path, voice, rate, volume):
    """Use edge-tts (free Microsoft Edge TTS) with boundary capture for subtitle sync."""
    import edge_tts

    voice = _normalize_edge_voice(voice)
    rate = _normalize_edge_rate(rate)
    volume = _normalize_edge_volume(volume)
    boundaries = []
    got_audio = False

    async def _run():
        nonlocal got_audio
        communicate = edge_tts.Communicate(text, voice, rate=rate, volume=volume)
        with open(output_path, 'wb') as f:
            async for chunk in communicate.stream():
                if chunk['type'] == 'audio':
                    f.write(chunk['data'])
                    got_audio = True
                elif chunk['type'] in ('WordBoundary', 'SentenceBoundary'):
                    # edge-tts v7+ uses SentenceBoundary, older versions use WordBoundary
                    boundaries.append({
                        'offset': chunk['offset'],      # 100-nanosecond units
                        'duration': chunk['duration'],  # 100-nanosecond units
                        'text': chunk['text'],
                    })

    try:
        asyncio.run(_run())
    except Exception as e:
        raise Exception(f'{e} (voice={voice}, rate={rate}, volume={volume})') from e

    if not got_audio or not os.path.exists(output_path) or os.path.getsize(output_path) < 64:
        raise Exception(
            f'No audio was received. Please verify that your parameters are correct. '
            f'(voice={voice}, rate={rate}, volume={volume})'
        )

    duration = _get_audio_duration(output_path)
    if duration <= 0:
        # Fallback: estimate from text length (avg 4 chars/sec for Chinese)
        duration = max(1.0, len(text) / 4.0)
        print(f'[TTS] ffprobe failed, estimated duration: {duration:.1f}s')

    return {
        'audio_path': output_path,
        'duration': duration,
        'provider': 'edge',
        'word_boundaries': boundaries,
    }


def _tts_azure(text, output_path, config):
    """Use Azure Cognitive Services TTS (requires API key)."""
    import requests as req
    api_key = config.get('api_key', '')
    if not api_key:
        raise Exception('Azure TTS API Key 未配置')

    voice = config.get('voice', 'zh-CN-YunxiNeural')
    rate = config.get('rate', '+0%')
    volume = config.get('volume', '+0%')

    url = 'https://eastus.tts.speech.microsoft.com/cognitiveservices/v1'
    headers = {
        'Ocp-Apim-Subscription-Key': api_key,
        'Content-Type': 'application/ssml+xml',
        'X-Microsoft-OutputFormat': 'audio-16khz-128kbitrate-mono-mp3',
    }
    ssml = f'''<speak version="1.0" xml:lang="zh-CN">
        <voice name="{voice}">
            <prosody rate="{rate}" volume="{volume}">{text}</prosody>
        </voice>
    </speak>'''

    resp = req.post(url, headers=headers, data=ssml.encode('utf-8'), timeout=30)
    resp.raise_for_status()
    with open(output_path, 'wb') as f:
        f.write(resp.content)

    duration = _get_audio_duration(output_path)
    return {'audio_path': output_path, 'duration': duration, 'provider': 'azure', 'word_boundaries': []}


def _tts_volcano(text, output_path, config):
    """Use Volcano Engine TTS."""
    raise Exception('火山引擎 TTS 暂未实现，请使用 Edge TTS')


# ============================================================
# 2. Subtitle Generation (synced with TTS word boundaries)
# ============================================================

def generate_subtitle(text, audio_duration, output_path, word_boundaries=None):
    """
    Generate SRT subtitle file from script text.

    If word_boundaries (from TTS) are available, uses real timestamps
    for perfect audio/subtitle sync. Otherwise falls back to even distribution.

    If audio_duration is 0 or negative (e.g. ffprobe unavailable), estimates
    duration from text length to ensure subtitles are always generated.

    Args:
        text: the full script text
        audio_duration: audio length in seconds
        output_path: path to save .srt file
        word_boundaries: list of {offset, duration, text} from TTS (optional)

    Returns:
        dict with: subtitle_path, segment_count
    """
    # Ensure we always have a valid duration for subtitle generation
    if audio_duration is None or audio_duration <= 0:
        # Estimate: average 4 chars/sec for Chinese, 2.5 words/sec for English
        char_count = len(text.strip())
        audio_duration = max(5.0, char_count / 4.0)
        print(f'[Subtitle] audio_duration was 0, estimated {audio_duration:.1f}s from text length')

    if word_boundaries:
        result = _generate_subtitle_from_boundaries(word_boundaries, output_path)
        if result['segment_count'] > 0:
            return result
        # Fall through to even distribution if boundary parsing failed
        print('[Subtitle] Word boundary parsing failed, using even distribution')

    # Fallback: even distribution
    return _generate_subtitle_even(text, audio_duration, output_path)


def _generate_subtitle_from_boundaries(word_boundaries, output_path):
    """Generate SRT from TTS boundary timestamps (perfectly synced).

    Handles both WordBoundary (word-level) and SentenceBoundary (sentence-level) data.
    For sentence-level: splits long sentences into shorter subtitle segments.
    For word-level: groups words into segments by punctuation.
    """
    if not word_boundaries:
        return {'subtitle_path': '', 'segment_count': 0}

    # Check if these are sentence-level boundaries (longer text) or word-level
    avg_len = sum(len(wb['text']) for wb in word_boundaries) / len(word_boundaries)
    is_sentence_level = avg_len > 10  # Heuristic: > 10 chars avg = sentence-level

    if is_sentence_level:
        # SentenceBoundary: each item is a full sentence
        # Split long sentences into shorter subtitle segments
        segments = []
        for wb in word_boundaries:
            text = wb['text'].strip()
            if not text:
                continue

            # If sentence is short enough, use as-is
            if len(text) <= 35:
                segments.append({
                    'start': wb['offset'],
                    'end': wb['offset'] + wb['duration'],
                    'text': text,
                })
            else:
                # Split long sentence by punctuation and distribute time proportionally
                parts = re.split(r'([，,；;、])', text)
                # Rejoin with delimiters
                chunks = []
                current = ''
                for part in parts:
                    current += part
                    if part in '，,；;、' and len(current) > 10:
                        chunks.append(current)
                        current = ''
                if current:
                    chunks.append(current)

                # Distribute time across chunks proportionally
                total_len = sum(len(c) for c in chunks)
                if total_len == 0:
                    segments.append({
                        'start': wb['offset'],
                        'end': wb['offset'] + wb['duration'],
                        'text': text,
                    })
                    continue

                chunk_start = wb['offset']
                chunk_total_dur = wb['duration']
                for chunk in chunks:
                    chunk_dur = int(chunk_total_dur * len(chunk) / total_len)
                    segments.append({
                        'start': chunk_start,
                        'end': chunk_start + chunk_dur,
                        'text': chunk.strip(),
                    })
                    chunk_start += chunk_dur
    else:
        # WordBoundary: group words into segments
        segments = []
        current_words = []
        current_text = ''

        for wb in word_boundaries:
            word = wb['text']
            current_words.append(wb)
            current_text += word

            if (word and word[-1] in '。！？!?，,；;、\n') or len(current_text) >= 35:
                if current_words:
                    segments.append({
                        'start': current_words[0]['offset'],
                        'end': current_words[-1]['offset'] + current_words[-1]['duration'],
                        'text': current_text.strip(),
                    })
                current_words = []
                current_text = ''

        if current_words:
            segments.append({
                'start': current_words[0]['offset'],
                'end': current_words[-1]['offset'] + current_words[-1]['duration'],
                'text': current_text.strip(),
            })

    # Build SRT
    srt_lines = []
    for i, seg in enumerate(segments):
        start_sec = seg['start'] / 10_000_000
        end_sec = seg['end'] / 10_000_000

        # Ensure minimum display time
        if end_sec - start_sec < 0.5:
            end_sec = start_sec + 0.5

        if not seg['text']:
            continue

        srt_lines.append(str(i + 1))
        srt_lines.append(f'{_format_srt_time(start_sec)} --> {_format_srt_time(end_sec)}')
        srt_lines.append(seg['text'])
        srt_lines.append('')

    with open(output_path, 'w', encoding='utf-8') as f:
        f.write('\n'.join(srt_lines))

    return {
        'subtitle_path': output_path,
        'segment_count': len([s for s in srt_lines if s and not s.isdigit() and '-->' not in s]),
    }


def _generate_subtitle_even(text, audio_duration, output_path):
    """Fallback: split text evenly across audio duration (less accurate sync)."""
    segments = _split_text_for_subtitle(text)

    if not segments or audio_duration <= 0:
        return {'subtitle_path': '', 'segment_count': 0}

    time_per_segment = audio_duration / len(segments)

    srt_lines = []
    for i, seg in enumerate(segments):
        start_time = i * time_per_segment
        end_time = (i + 1) * time_per_segment
        srt_lines.append(f'{i + 1}')
        srt_lines.append(f'{_format_srt_time(start_time)} --> {_format_srt_time(end_time)}')
        srt_lines.append(seg.strip())
        srt_lines.append('')

    with open(output_path, 'w', encoding='utf-8') as f:
        f.write('\n'.join(srt_lines))

    return {
        'subtitle_path': output_path,
        'segment_count': len(segments),
    }


def _split_text_for_subtitle(text):
    """Split text into subtitle segments by Chinese/English punctuation."""
    raw = re.split(r'[。！？!?\n]+', text)
    segments = []
    for s in raw:
        s = s.strip()
        if not s:
            continue
        if len(s) > 40:
            sub = re.split(r'[，,；;]+', s)
            segments.extend([x.strip() for x in sub if x.strip()])
        else:
            segments.append(s)
    return segments


def _format_srt_time(seconds):
    """Format seconds as SRT timestamp: HH:MM:SS,mmm"""
    hrs = int(seconds // 3600)
    mins = int((seconds % 3600) // 60)
    secs = int(seconds % 60)
    ms = int((seconds % 1) * 1000)
    return f'{hrs:02d}:{mins:02d}:{secs:02d},{ms:03d}'


# ============================================================
# 3. Video Composition (with styled subtitles & visual effects)
# ============================================================

def _map_scenes_to_timings(scenes, sentence_timings):
    """Map scene texts to TTS sentence timings to get start/end times.

    Uses sequential greedy matching: for each scene, consume consecutive
    sentences until the scene text is covered.

    Args:
        scenes: list of {index, text, keywords, material_index, visual_desc}
        sentence_timings: list of {index, text, start, end}

    Returns:
        Updated scenes with 'start' and 'end' fields added
    """
    if not scenes or not sentence_timings:
        # Fallback: distribute evenly
        return scenes

    sent_idx = 0
    for scene in scenes:
        scene_text = scene.get('text', '').strip()
        if not scene_text:
            continue

        # Find matching sentences: consume consecutive sentences whose text
        # is contained in the scene text
        matched_start = None
        matched_end = None
        accumulated = ''

        while sent_idx < len(sentence_timings):
            sent = sentence_timings[sent_idx]
            sent_text = sent['text'].strip()

            # Check if this sentence belongs to the current scene
            # by checking if accumulated + sentence is a prefix of scene_text
            # or sentence text is contained in scene text
            if sent_text in scene_text or scene_text.startswith(accumulated + sent_text):
                if matched_start is None:
                    matched_start = sent['start']
                matched_end = sent['end']
                accumulated += sent_text
                sent_idx += 1

                # Check if we've covered the scene text
                if len(accumulated) >= len(scene_text) * 0.8:
                    break
            else:
                # This sentence doesn't belong to current scene
                if matched_start is not None:
                    break  # We've matched something, stop
                # Skip this sentence (might be from a previous unmatched scene)
                sent_idx += 1

        if matched_start is not None:
            scene['start'] = matched_start
            scene['end'] = matched_end
        else:
            # No match found, assign remaining time or use even distribution
            if sent_idx < len(sentence_timings):
                scene['start'] = sentence_timings[sent_idx]['start']
                scene['end'] = sentence_timings[sent_idx]['end']
            elif sentence_timings:
                scene['start'] = sentence_timings[-1]['end']
                scene['end'] = sentence_timings[-1]['end'] + 1.0

    # Ensure last scene ends at audio duration
    if scenes and sentence_timings:
        scenes[-1]['end'] = sentence_timings[-1]['end']

    return scenes


def _hex_to_ffmpeg_color(hex_color):
    """Convert #RRGGBB to FFmpeg 0xRRGGBB format."""
    c = hex_color.lstrip('#')
    if len(c) == 6:
        return f'0x{c}'
    return '0x1a1a2e'


def _escape_subtitle_path(path):
    """Escape a file path for FFmpeg subtitles filter.

    Copies SRT to temp dir with ASCII-only path to avoid encoding issues.
    Returns (escaped_path_string, temp_file_path_for_cleanup).
    """
    temp_dir = tempfile.gettempdir()
    temp_srt = os.path.join(temp_dir, '_ffmpeg_subtitle.srt')
    shutil.copy2(path, temp_srt)

    escaped = temp_srt.replace('\\', '/').replace(':', '\\:')
    return f"'{escaped}'", temp_srt


def _build_subtitle_filter(sub_filter_str, style=None):
    """Build the subtitles filter string with force_style.

    Uses style config if provided, otherwise falls back to global video settings.
    """
    if style:
        font_name = style['subtitle_font']
        font_size = style['subtitle_size']
        sub_color = style['subtitle_color']
        outline_color = style['subtitle_outline_color']
        outline_width = '2'
        margin_v = style['subtitle_margin_v']
    else:
        config = get_video_config()
        font_name = config.get('subtitle_font', 'Microsoft YaHei') or 'Microsoft YaHei'
        font_size = config.get('subtitle_size', '28') or '28'
        sub_color = config.get('subtitle_color', '&H00FFFFFF') or '&H00FFFFFF'
        outline_color = config.get('subtitle_outline_color', '&H00000000') or '&H00000000'
        outline_width = config.get('subtitle_outline', '2') or '2'
        margin_v = config.get('subtitle_margin_v', '100') or '100'

    # ASS style: Alignment=2 means bottom-center
    force_style = (
        f"force_style='"
        f"FontName={font_name},"
        f"FontSize={font_size},"
        f"PrimaryColour={sub_color},"
        f"OutlineColour={outline_color},"
        f"BorderStyle=1,"
        f"Outline={outline_width},"
        f"Shadow=0,"
        f"Alignment=2,"
        f"MarginV={margin_v}"
        f"'"
    )

    return f'subtitles={sub_filter_str}:{force_style}'


def _build_fade_filter(duration, style=None):
    """Build fade in/out filter string."""
    if style and style.get('_fade_transition'):
        fade_enabled = style['_fade_transition']
    else:
        config = get_video_config()
        fade_enabled = config.get('default_fade_transition', 'true') or 'true'

    if fade_enabled != 'true':
        return ''

    fade_in_duration = 0.5
    fade_out_duration = 0.5
    fade_out_start = max(0, duration - fade_out_duration)

    return f',fade=t=in:st=0:d={fade_in_duration},fade=t=out:st={fade_out_start}:d={fade_out_duration}'


def compose_video(audio_path, subtitle_path, image_paths, output_path,
                  title_text='', video_style='default', video_paths=None, task_params=None,
                  scenes=None):
    """
    Compose a video from audio, subtitles, images/videos.

    Uses MoviePy 2.x for high-quality composition with:
      - Smooth Ken Burns zoom on images
      - Crossfade transitions between segments
      - TextClip subtitles with per-style styling
      - Color grading, vignette, letterbox per style preset
      - Scene-based material switching (if scenes provided)

    Falls back to raw FFmpeg if MoviePy fails.

    Args:
        audio_path: path to audio file (.mp3)
        subtitle_path: path to SRT subtitle file (.srt)
        image_paths: list of image file paths for background
        output_path: path to save output video (.mp4)
        title_text: optional title text to overlay at top
        video_style: style key (default, cyberpunk, punk, minimalist, etc.)
        video_paths: list of video file paths for background
        task_params: dict with per-task overrides
        scenes: optional list of scene dicts with {start, end, material_path, material_type}
                for scene-based material switching

    Returns:
        dict with: video_path, duration, file_size
    """
    # Merge config defaults with per-task overrides
    config = get_video_config()
    tp = task_params or {}
    engine = tp.get('video_engine') or config.get('default_video_engine', 'moviepy') or 'moviepy'

    # Try MoviePy first (better quality) if configured
    if engine != 'ffmpeg':
        try:
            from modules.video.composer import compose_video_moviepy
            print('[VideoMaker] Using MoviePy composer')
            return compose_video_moviepy(
                audio_path, subtitle_path, image_paths, output_path,
                title_text=title_text,
                video_style=video_style,
                video_paths=video_paths,
                task_params=tp,
                scenes=scenes,
            )
        except Exception as e:
            print(f'[VideoMaker] MoviePy failed: {e}')
            print('[VideoMaker] Falling back to FFmpeg composer')

    # Fallback: raw FFmpeg
    ffmpeg = config.get('ffmpeg_path', 'ffmpeg') or 'ffmpeg'
    resolution = tp.get('resolution') or config.get('default_resolution', '1080x1920') or '1080x1920'
    fps = tp.get('fps') or config.get('default_fps', '30') or '30'
    width, height = resolution.split('x')
    style = get_style_config(video_style)

    # Pass per-task params to FFmpeg filter builders via style dict
    style['_fade_transition'] = tp.get('fade_transition') or config.get('default_fade_transition', 'true') or 'true'
    style['_title_overlay'] = 'false'

    sub_filter_str, temp_srt = _escape_subtitle_path(subtitle_path)

    try:
        if video_paths and not image_paths:
            # Only video material: play once, freeze last frame if shorter than audio
            return _compose_with_video_bg(
                audio_path, sub_filter_str, output_path,
                ffmpeg, width, height, fps, style, title_text, video_paths
            )
        elif image_paths:
            # Images (with or without video): use image slideshow
            # If there's also a video, MoviePy handles mixing; FFmpeg fallback uses images only
            return _compose_with_images(
                audio_path, sub_filter_str, output_path,
                ffmpeg, width, height, fps, style, title_text, image_paths
            )
        else:
            return _compose_animated_bg(
                audio_path, sub_filter_str, output_path,
                ffmpeg, width, height, fps, style, title_text
            )
    finally:
        try:
            os.remove(temp_srt)
        except OSError:
            pass


def _build_vf_chain(sub_filter, style, fade_str, title_filter, audio_duration):
    """Build the full video filter chain from components."""
    vf_parts = [sub_filter]

    # Style color grading filter
    if style.get('video_filter'):
        vf_parts.append(style['video_filter'])

    # Vignette effect
    if style.get('vignette'):
        vf_parts.append('vignette=PI/5')

    # Title overlay
    if title_filter:
        vf_parts.append(title_filter)

    # Fade transitions
    if fade_str:
        vf_parts.append(fade_str.lstrip(','))

    return ','.join(vf_parts)


def _build_title_filter(style, title_text):
    """Build drawtext filter for title overlay."""
    if not title_text:
        return ''

    if style and style.get('_title_overlay'):
        show_title = style['_title_overlay']
    else:
        config = get_video_config()
        show_title = config.get('default_title_overlay', 'true') or 'true'
    if show_title != 'true':
        return ''

    safe_title = title_text.replace(':', r'\:').replace("'", r"\'")
    fontfile = _find_font_file(style['subtitle_font'])
    font_part = f"fontfile='{fontfile}':" if fontfile else ''
    title_color = style.get('title_color', 'white@0.9')

    return (
        f"drawtext={font_part}"
        f"text='{safe_title}':"
        f"fontcolor={title_color}:fontsize=36:"
        f"x=(w-text_w)/2:y=60:"
        f"shadowcolor=black@0.5:shadowx=2:shadowy=2"
    )


def _compose_with_images(audio_path, sub_filter_str, output_path,
                          ffmpeg, width, height, fps, style, title_text, image_paths):
    """Compose video with image backgrounds and Ken Burns zoom effect."""
    audio_duration = _get_audio_duration(audio_path)
    if audio_duration <= 0:
        audio_duration = 30

    fade_str = _build_fade_filter(audio_duration, style)
    sub_filter = _build_subtitle_filter(sub_filter_str, style)
    title_filter = _build_title_filter(style, title_text)
    total_frames = int(audio_duration * int(fps))

    if len(image_paths) == 1:
        # Single image with Ken Burns zoom effect
        cmd = [
            ffmpeg,
            '-loop', '1', '-i', image_paths[0],
            '-i', audio_path,
            '-vf',
            f'scale={width}:{height}:force_original_aspect_ratio=increase,'
            f'crop={width}:{height},'
            f'zoompan=z=\'min(zoom+0.0008,1.3)\':d={total_frames}:'
            f'x=\'iw/2-(iw/zoom/2)\':y=\'ih/2-(ih/zoom/2)\':'
            f's={width}x{height}:fps={fps},'
            f'{_build_vf_chain(sub_filter, style, fade_str, title_filter, audio_duration)}',
            '-t', str(audio_duration),
            '-c:v', 'libx264', '-pix_fmt', 'yuv420p', '-r', str(fps),
            '-c:a', 'aac', '-b:a', '192k',
            '-shortest', '-y', output_path,
        ]
    else:
        # Multiple images: slideshow with crossfade
        img_duration = audio_duration / len(image_paths)
        concat_file = os.path.join(os.path.dirname(output_path), 'concat_images.txt')
        with open(concat_file, 'w') as f:
            for img in image_paths:
                safe_img = img.replace('\\', '/').replace("'", "\\'")
                f.write(f"file '{safe_img}'\nduration {img_duration}\n")
            f.write(f"file '{image_paths[-1].replace(chr(92), '/')}'\n")

        cmd = [
            ffmpeg,
            '-f', 'concat', '-safe', '0', '-i', concat_file,
            '-i', audio_path,
            '-vf',
            f'scale={width}:{height}:force_original_aspect_ratio=increase,'
            f'crop={width}:{height},'
            f'{_build_vf_chain(sub_filter, style, fade_str, title_filter, audio_duration)}',
            '-c:v', 'libx264', '-pix_fmt', 'yuv420p', '-r', str(fps),
            '-c:a', 'aac', '-b:a', '192k',
            '-shortest', '-y', output_path,
        ]

    result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
    if result.returncode != 0:
        # Retry without title overlay if it failed
        if title_filter:
            vf_simple = _build_vf_chain(sub_filter, style, fade_str, '', audio_duration)
            if len(image_paths) == 1:
                cmd_simple = [
                    ffmpeg,
                    '-loop', '1', '-i', image_paths[0],
                    '-i', audio_path,
                    '-vf',
                    f'scale={width}:{height}:force_original_aspect_ratio=increase,'
                    f'crop={width}:{height},'
                    f'zoompan=z=\'min(zoom+0.0008,1.3)\':d={total_frames}:'
                    f'x=\'iw/2-(iw/zoom/2)\':y=\'ih/2-(ih/zoom/2)\':'
                    f's={width}x{height}:fps={fps},'
                    f'{vf_simple}',
                    '-t', str(audio_duration),
                    '-c:v', 'libx264', '-pix_fmt', 'yuv420p', '-r', str(fps),
                    '-c:a', 'aac', '-b:a', '192k',
                    '-shortest', '-y', output_path,
                ]
            else:
                cmd_simple = [
                    ffmpeg,
                    '-f', 'concat', '-safe', '0', '-i', concat_file,
                    '-i', audio_path,
                    '-vf',
                    f'scale={width}:{height}:force_original_aspect_ratio=increase,'
                    f'crop={width}:{height},'
                    f'{vf_simple}',
                    '-c:v', 'libx264', '-pix_fmt', 'yuv420p', '-r', str(fps),
                    '-c:a', 'aac', '-b:a', '192k',
                    '-shortest', '-y', output_path,
                ]
            result = subprocess.run(cmd_simple, capture_output=True, text=True, timeout=300)
            if result.returncode != 0:
                raise Exception(f'FFmpeg error: {result.stderr[-800:]}')
        else:
            raise Exception(f'FFmpeg error: {result.stderr[-800:]}')

    # Cleanup concat file
    if len(image_paths) > 1:
        try:
            os.remove(concat_file)
        except OSError:
            pass

    file_size = os.path.getsize(output_path) if os.path.exists(output_path) else 0
    return {
        'video_path': output_path,
        'duration': audio_duration,
        'file_size': file_size,
    }


def _compose_with_video_bg(audio_path, sub_filter_str, output_path,
                            ffmpeg, width, height, fps, style, title_text, video_paths):
    """Compose video with a video file as background.

    Plays the video once (no looping). If the video is shorter than the audio,
    freezes the last frame to fill the remaining duration using tpad filter.
    If the video is longer, trims it to match the audio duration.
    """
    audio_duration = _get_audio_duration(audio_path)
    if audio_duration <= 0:
        audio_duration = 30

    fade_str = _build_fade_filter(audio_duration, style)
    sub_filter = _build_subtitle_filter(sub_filter_str, style)
    title_filter = _build_title_filter(style, title_text)
    vf_chain = _build_vf_chain(sub_filter, style, fade_str, title_filter, audio_duration)

    bg_video = video_paths[0]
    video_duration = _get_video_duration(bg_video)

    # Build scale+crop filter
    scale_crop = f'scale={width}:{height}:force_original_aspect_ratio=increase,crop={width}:{height}'

    if video_duration > 0 and video_duration < audio_duration:
        # Video shorter than audio: play once, then freeze last frame
        pad_duration = audio_duration - video_duration
        print(f'[VideoMaker] Video {video_duration:.1f}s < audio {audio_duration:.1f}s, freezing last frame for {pad_duration:.1f}s')
        cmd = [
            ffmpeg,
            '-i', bg_video,
            '-i', audio_path,
            '-vf',
            f'{scale_crop},'
            f'tpad=stop_mode=clone:stop_duration={pad_duration:.3f},'
            f'{vf_chain}',
            '-t', str(audio_duration),
            '-c:v', 'libx264', '-pix_fmt', 'yuv420p', '-r', str(fps),
            '-c:a', 'aac', '-b:a', '192k',
            '-shortest', '-y', output_path,
        ]
    else:
        # Video long enough or duration unknown: trim to audio duration
        cmd = [
            ffmpeg,
            '-i', bg_video,
            '-i', audio_path,
            '-vf',
            f'{scale_crop},'
            f'{vf_chain}',
            '-t', str(audio_duration),
            '-c:v', 'libx264', '-pix_fmt', 'yuv420p', '-r', str(fps),
            '-c:a', 'aac', '-b:a', '192k',
            '-shortest', '-y', output_path,
        ]

    result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
    if result.returncode != 0:
        if title_filter:
            vf_simple = _build_vf_chain(sub_filter, style, fade_str, '', audio_duration)
            if video_duration > 0 and video_duration < audio_duration:
                pad_duration = audio_duration - video_duration
                cmd_simple = [
                    ffmpeg,
                    '-i', bg_video,
                    '-i', audio_path,
                    '-vf',
                    f'{scale_crop},'
                    f'tpad=stop_mode=clone:stop_duration={pad_duration:.3f},'
                    f'{vf_simple}',
                    '-t', str(audio_duration),
                    '-c:v', 'libx264', '-pix_fmt', 'yuv420p', '-r', str(fps),
                    '-c:a', 'aac', '-b:a', '192k',
                    '-shortest', '-y', output_path,
                ]
            else:
                cmd_simple = [
                    ffmpeg,
                    '-i', bg_video,
                    '-i', audio_path,
                    '-vf',
                    f'{scale_crop},'
                    f'{vf_simple}',
                    '-t', str(audio_duration),
                    '-c:v', 'libx264', '-pix_fmt', 'yuv420p', '-r', str(fps),
                    '-c:a', 'aac', '-b:a', '192k',
                    '-shortest', '-y', output_path,
                ]
            result = subprocess.run(cmd_simple, capture_output=True, text=True, timeout=300)
            if result.returncode != 0:
                raise Exception(f'FFmpeg error: {result.stderr[-800:]}')
        else:
            raise Exception(f'FFmpeg error: {result.stderr[-800:]}')

    file_size = os.path.getsize(output_path) if os.path.exists(output_path) else 0
    return {
        'video_path': output_path,
        'duration': audio_duration,
        'file_size': file_size,
    }


def _compose_animated_bg(audio_path, sub_filter_str, output_path,
                          ffmpeg, width, height, fps, style, title_text=''):
    """Compose video with styled animated background (when no materials available).

    Creates a visually appealing background using FFmpeg lavfi color source
    with style-specific color grading, gradient overlay, vignette, and subtitles.
    """
    audio_duration = _get_audio_duration(audio_path)
    if audio_duration <= 0:
        audio_duration = 30

    sub_filter = _build_subtitle_filter(sub_filter_str, style)
    fade_str = _build_fade_filter(audio_duration, style)
    title_filter = _build_title_filter(style, title_text)
    bg_color = style['bg_color']

    # Build filter chain
    vf_parts = [sub_filter]

    # Add gradient overlay using drawbox (semi-transparent lighter band at top)
    vf_parts.append(
        f"drawbox=x=0:y=0:w={width}:h={int(int(height)*0.3)}:"
        f"color=white@0.05:t=fill"
    )

    # Style color grading
    if style.get('video_filter'):
        vf_parts.append(style['video_filter'])

    # Vignette
    if style.get('vignette'):
        vf_parts.append('vignette=PI/5')

    # Title overlay
    if title_filter:
        vf_parts.append(title_filter)

    # Letterbox bars (cinematic style)
    if style.get('letterbox'):
        bar_h = int(int(height) * 0.05)
        vf_parts.append(
            f"drawbox=x=0:y=0:w={width}:h={bar_h}:color=black:t=fill,"
            f"drawbox=x=0:y={int(height)-bar_h}:w={width}:h={bar_h}:color=black:t=fill"
        )

    # Fade transitions
    if fade_str:
        vf_parts.append(fade_str.lstrip(','))

    vf = ','.join(vf_parts)

    cmd = [
        ffmpeg,
        '-f', 'lavfi', '-i',
        f'color=c={bg_color}:s={width}x{height}:d={audio_duration}:r={fps}',
        '-i', audio_path,
        '-vf', vf,
        '-c:v', 'libx264', '-pix_fmt', 'yuv420p', '-r', str(fps),
        '-c:a', 'aac', '-b:a', '192k',
        '-shortest', '-y', output_path,
    ]

    result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
    if result.returncode != 0:
        # Retry with minimal filters (subtitles + fade only)
        vf_parts_simple = [sub_filter]
        if fade_str:
            vf_parts_simple.append(fade_str.lstrip(','))
        vf_simple = ','.join(vf_parts_simple)
        cmd_simple = [
            ffmpeg,
            '-f', 'lavfi', '-i',
            f'color=c={bg_color}:s={width}x{height}:d={audio_duration}:r={fps}',
            '-i', audio_path,
            '-vf', vf_simple,
            '-c:v', 'libx264', '-pix_fmt', 'yuv420p', '-r', str(fps),
            '-c:a', 'aac', '-b:a', '192k',
            '-shortest', '-y', output_path,
        ]
        result = subprocess.run(cmd_simple, capture_output=True, text=True, timeout=300)
        if result.returncode != 0:
            raise Exception(f'FFmpeg error: {result.stderr[-800:]}')

    file_size = os.path.getsize(output_path) if os.path.exists(output_path) else 0
    return {
        'video_path': output_path,
        'duration': audio_duration,
        'file_size': file_size,
    }


def _find_font_file(font_name):
    """Try to find a font file path on Windows for drawtext filter."""
    font_map = {
        'Microsoft YaHei': 'C:/Windows/Fonts/msyh.ttc',
        'SimHei': 'C:/Windows/Fonts/simhei.ttf',
        'KaiTi': 'C:/Windows/Fonts/simkai.ttf',
        'SimSun': 'C:/Windows/Fonts/simsun.ttc',
        'Microsoft JhengHei': 'C:/Windows/Fonts/msjh.ttc',
    }
    path = font_map.get(font_name)
    if path and os.path.exists(path):
        escaped = path.replace('\\', '/').replace(':', r'\:')
        return f"'{escaped}'"
    default = 'C:/Windows/Fonts/msyh.ttc'
    if os.path.exists(default):
        escaped = default.replace('\\', '/').replace(':', r'\:')
        return f"'{escaped}'"
    return ''


# ============================================================
# 4. Asset Management (Images)
# ============================================================

def get_images(keywords, count=5):
    """Get background images for video composition."""
    config = get_video_config()
    source = config.get('image_source', 'local')

    if source == 'pexels':
        return _get_pexels_images(keywords, count, config)
    else:
        return _get_local_images(config)


def _get_local_images(config):
    """Get images from local directory."""
    img_dir = config.get('image_dir', '')
    if not img_dir or not os.path.isdir(img_dir):
        return []

    extensions = ('.jpg', '.jpeg', '.png', '.webp')
    images = []
    for f in sorted(os.listdir(img_dir)):
        if f.lower().endswith(extensions):
            images.append(os.path.join(img_dir, f))
    return images[:10]


def _get_pexels_images(keywords, count, config):
    """Search Pexels for free stock photos."""
    import requests
    api_key = config.get('pexels_api_key', '')
    if not api_key:
        return []

    url = 'https://api.pexels.com/v1/search'
    headers = {'Authorization': api_key}
    params = {'query': keywords, 'per_page': count, 'orientation': 'portrait'}

    resp = requests.get(url, headers=headers, params=params, timeout=15)
    resp.raise_for_status()
    data = resp.json()

    image_paths = []
    output_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'outputs', 'images')
    os.makedirs(output_dir, exist_ok=True)

    for i, photo in enumerate(data.get('photos', [])[:count]):
        img_url = photo['src']['large']
        img_path = os.path.join(output_dir, f'pexels_{i}.jpg')
        try:
            resp = requests.get(img_url, timeout=15)
            with open(img_path, 'wb') as f:
                f.write(resp.content)
            image_paths.append(img_path)
        except Exception:
            pass

    return image_paths


# ============================================================
# 5. Utilities
# ============================================================

def _get_ffmpeg_path():
    """Get configured FFmpeg executable path."""
    config = get_video_config()
    return config.get('ffmpeg_path', 'ffmpeg') or 'ffmpeg'


def _get_ffprobe_path():
    """Get ffprobe path derived from the configured ffmpeg path."""
    ffmpeg = _get_ffmpeg_path()
    if ffmpeg and ffmpeg != 'ffmpeg':
        d = os.path.dirname(ffmpeg)
        return os.path.join(d, 'ffprobe.exe') if d else 'ffprobe'
    return 'ffprobe'


def _get_audio_duration(audio_path):
    """Get audio duration in seconds using ffprobe."""
    try:
        ffprobe = _get_ffprobe_path()
        result = subprocess.run(
            [ffprobe, '-v', 'quiet', '-show_entries', 'format=duration',
             '-of', 'default=noprint_wrappers=1:nokey=1', audio_path],
            capture_output=True, text=True, timeout=10
        )
        if result.returncode == 0:
            return float(result.stdout.strip())
    except Exception:
        pass
    return 0


def _get_video_duration(video_path):
    """Get video duration in seconds using ffprobe."""
    try:
        ffprobe = _get_ffprobe_path()
        result = subprocess.run(
            [ffprobe, '-v', 'quiet', '-show_entries', 'format=duration',
             '-of', 'default=noprint_wrappers=1:nokey=1', video_path],
            capture_output=True, text=True, timeout=10
        )
        if result.returncode == 0:
            return float(result.stdout.strip())
    except Exception:
        pass
    return 0


def check_ffmpeg():
    """Check if FFmpeg is available (uses configured path)."""
    try:
        ffmpeg = _get_ffmpeg_path()
        result = subprocess.run(
            [ffmpeg, '-version'], capture_output=True, text=True, timeout=5
        )
        return result.returncode == 0
    except Exception:
        return False


# ============================================================
# 6. Full Pipeline
# ============================================================

def produce_video(script_data, video_task_id, output_dir, video_style='default', material_paths=None, task_params=None, materials_info=None, pre_scenes=None):
    """
    Run the full video production pipeline.

    Steps:
      0. (Optional) AI narration rewrite if narration_prompt is provided
      1. (Optional) AI scene segmentation + material matching
      2. Generate TTS audio (captures word boundaries + sentence timings)
      3. Generate subtitles from real TTS timestamps
      4. Map scenes to TTS sentence timings
      5. Compose final video with scene-based material switching

    Args:
        script_data: dict with hook, content, ending, title, etc.
        video_task_id: task ID for naming files
        output_dir: directory for output files
        video_style: style key
        material_paths: dict with 'images' and 'videos' lists of file paths
        task_params: dict with per-task overrides
        materials_info: list of {index, name, type, tags, file_path} for scene matching
        pre_scenes: pre-generated scenes (from manual editor), skips AI generation

    Returns:
        dict with all file paths and metadata
    """
    os.makedirs(output_dir, exist_ok=True)
    tp = task_params or {}

    # Combine script parts into narration text
    narration = ''
    if script_data.get('hook'):
        narration += script_data['hook'] + '\n'
    if script_data.get('content'):
        narration += script_data['content']
    if script_data.get('ending'):
        narration += '\n' + script_data['ending']

    if not narration.strip():
        raise Exception('文案内容为空，无法生成视频')

    # Step 0: AI narration rewrite (if narration_prompt is provided)
    narration_prompt = tp.get('narration_prompt', '').strip()
    if narration_prompt:
        print(f'[VideoMaker] Narration prompt provided, rewriting script with AI...')
        try:
            from modules.ai.writer import generate_narration
            narration = generate_narration(script_data, narration_prompt)
            if not narration.strip():
                narration = script_data.get('hook', '') + '\n' + script_data.get('content', '') + '\n' + script_data.get('ending', '')
                print('[VideoMaker] AI narration rewrite returned empty, using original text')
            else:
                print(f'[VideoMaker] Narration rewritten: {len(narration)} chars')
                narration_path = os.path.join(output_dir, f'task_{video_task_id}_narration.txt')
                with open(narration_path, 'w', encoding='utf-8') as f:
                    f.write(narration)
        except Exception as e:
            print(f'[VideoMaker] AI narration rewrite failed: {e}, using original text')

    # Save narration text for subtitle step
    narration_path = os.path.join(output_dir, f'task_{video_task_id}_narration.txt')
    with open(narration_path, 'w', encoding='utf-8') as f:
        f.write(narration)

    results = {}
    material_paths = material_paths or {}
    image_paths = material_paths.get('images', [])
    video_paths = material_paths.get('videos', [])
    if not tp.get('bgm_path') and material_paths.get('bgm'):
        tp['bgm_path'] = material_paths['bgm'][0]

    # If no user materials, try configured image source
    if not image_paths and not video_paths:
        keywords = script_data.get('tags', script_data.get('title', ''))
        image_paths = get_images(keywords, count=5)

    results['image_count'] = len(image_paths)
    results['video_material_count'] = len(video_paths)
    results['video_style'] = video_style

    def _checkpoint(**fields):
        """一键全流程中途落库，避免重启后字幕永远卡在 processing。"""
        if not video_task_id or not fields:
            return
        try:
            from config import get_db
            cols = ', '.join(f'{k}=?' for k in fields)
            vals = list(fields.values()) + [video_task_id]
            conn = get_db()
            conn.execute(f'UPDATE video_task SET {cols} WHERE id=?', vals)
            conn.commit()
            conn.close()
        except Exception as e:
            print(f'[VideoMaker] checkpoint failed: {e}')

    # Step 1: AI scene segmentation (if materials available)
    scenes = None
    if pre_scenes:
        # Use pre-generated scenes from manual editor
        scenes = pre_scenes
        print(f'[VideoMaker] Using {len(scenes)} pre-generated scenes')
    elif materials_info and len(materials_info) > 0:
        try:
            from modules.ai.writer import generate_scenes, auto_match_materials
            print(f'[VideoMaker] Generating scenes with {len(materials_info)} materials...')
            scenes = generate_scenes(narration, materials_info)
            # Auto-match if not already matched by AI
            if scenes and scenes[0].get('material_index', -1) == -1:
                scenes = auto_match_materials(scenes, materials_info)
            print(f'[VideoMaker] Generated {len(scenes)} scenes')
            # Save scenes for reference
            scenes_path = os.path.join(output_dir, f'task_{video_task_id}_scenes.json')
            with open(scenes_path, 'w', encoding='utf-8') as f:
                json.dump(scenes, f, ensure_ascii=False, indent=2)
        except Exception as e:
            print(f'[VideoMaker] Scene generation failed: {e}, using sequential playback')
            scenes = None

    # Step 2: TTS (with word boundary + sentence timing capture)
    audio_path = os.path.join(output_dir, f'task_{video_task_id}_audio.mp3')
    voice = tp.get('voice', '') or None
    voice_rate = tp.get('voice_rate', '') or None
    tts_result = generate_tts(narration, audio_path, voice=voice, rate=voice_rate)
    results['voice'] = tts_result
    results['voice_status'] = 'done'
    _checkpoint(
        voice_status='done',
        voice_url=tts_result.get('audio_path', ''),
        duration=tts_result.get('duration') or 0,
        subtitle_status='processing',
        error_msg='',
    )

    # Save word boundaries for potential separate subtitle regeneration
    boundaries_path = os.path.join(output_dir, f'task_{video_task_id}_boundaries.json')
    with open(boundaries_path, 'w', encoding='utf-8') as f:
        json.dump(tts_result.get('word_boundaries', []), f, ensure_ascii=False)

    # Save sentence timings for scene mapping
    sentence_timings = tts_result.get('sentence_timings', [])
    if sentence_timings:
        timings_path = os.path.join(output_dir, f'task_{video_task_id}_timings.json')
        with open(timings_path, 'w', encoding='utf-8') as f:
            json.dump(sentence_timings, f, ensure_ascii=False)

    # Step 3: Subtitle (synced with TTS word boundaries)
    subtitle_path = os.path.join(output_dir, f'task_{video_task_id}_subtitle.srt')
    sub_result = generate_subtitle(
        narration, tts_result['duration'], subtitle_path,
        word_boundaries=tts_result.get('word_boundaries')
    )
    results['subtitle'] = sub_result
    results['subtitle_status'] = 'done'
    _checkpoint(
        subtitle_status='done',
        subtitle_url=sub_result.get('subtitle_path', ''),
        video_status='processing',
        error_msg='',
    )

    # Step 4: Map scenes to TTS sentence timings + resolve material paths
    if scenes and sentence_timings:
        scenes = _map_scenes_to_timings(scenes, sentence_timings)

        # Resolve material_index to file paths
        if materials_info:
            mat_by_index = {m['index']: m for m in materials_info}
            for scene in scenes:
                mat_idx = scene.get('material_index', -1)
                if mat_idx >= 0 and mat_idx in mat_by_index:
                    mat = mat_by_index[mat_idx]
                    scene['material_path'] = mat.get('file_path', '')
                    scene['material_type'] = mat.get('type', 'image')
                else:
                    scene['material_path'] = ''
                    scene['material_type'] = ''

        # Log scene mapping
        for s in scenes:
            print(f'  Scene {s["index"]}: {s.get("start", 0):.1f}s-{s.get("end", 0):.1f}s '
                  f'→ {s.get("material_type", "?")} {os.path.basename(s.get("material_path", "none"))}')

    # Step 5: Compose video with style and materials
    if sub_result['subtitle_path']:
        video_path = os.path.join(output_dir, f'task_{video_task_id}_video.mp4')
        title_text = script_data.get('title', '')
        compose_result = compose_video(
            audio_path, sub_result['subtitle_path'], image_paths, video_path,
            title_text=title_text,
            video_style=video_style,
            video_paths=video_paths if video_paths else None,
            task_params=tp,
            scenes=scenes,
        )
        results['video'] = compose_result
        results['video_status'] = 'done'
        results['export_status'] = 'done'
        results['output_path'] = compose_result['video_path']
        results['scenes'] = scenes
    else:
        results['video_status'] = 'failed'
        results['export_status'] = 'failed'
        results['error_msg'] = '字幕生成失败'

    return results
