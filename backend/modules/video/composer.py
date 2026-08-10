"""
Video composition module using MoviePy 2.x.

Replaces raw FFmpeg command-line composition with MoviePy for:
  - Smooth Ken Burns zoom on images (function-based, not zoompan filter)
  - Crossfade transitions between image segments
  - TextClip for styled subtitles (no subtitles filter escaping issues)
  - Per-frame color grading via fl_image (brightness/contrast/saturation/hue)
  - Vignette and letterbox overlays
  - Title overlay with fade animation
  - Audio composition
"""

import os
import re
import numpy as np
from config import get_video_config


# ============================================================
# Style presets (MoviePy format - RGB colors, not ASS hex)
# ============================================================

MOVIEPY_STYLES = {
    'default': {
        'name': '默认',
        'bg_color': (26, 26, 46),        # #1a1a2e
        'sub_color': 'white',
        'sub_stroke_color': 'black',
        'sub_stroke_width': 2,
        'sub_font_size': 44,
        'sub_font': 'msyh.ttc',
        'title_color': 'white',
        'title_font_size': 42,
        'brightness': 1.0,
        'contrast': 1.0,
        'saturation': 1.0,
        'vignette': False,
        'letterbox': False,
    },
    'cyberpunk': {
        'name': '赛博朋克',
        'bg_color': (10, 10, 26),
        'sub_color': '#00FFFF',
        'sub_stroke_color': '#000033',
        'sub_stroke_width': 3,
        'sub_font_size': 38,
        'sub_font': 'msyh.ttc',
        'title_color': '#00CCFF',
        'title_font_size': 44,
        'brightness': 0.9,
        'contrast': 1.2,
        'saturation': 1.5,
        'vignette': True,
        'letterbox': False,
    },
    'punk': {
        'name': '朋克风格',
        'bg_color': (26, 5, 5),
        'sub_color': '#FF5530',
        'sub_stroke_color': 'black',
        'sub_stroke_width': 3,
        'sub_font_size': 40,
        'sub_font': 'simhei.ttf',
        'title_color': '#FF3322',
        'title_font_size': 46,
        'brightness': 0.85,
        'contrast': 1.4,
        'saturation': 1.3,
        'vignette': True,
        'letterbox': False,
    },
    'minimalist': {
        'name': '极简风格',
        'bg_color': (245, 245, 245),
        'sub_color': 'black',
        'sub_stroke_color': 'white',
        'sub_stroke_width': 1,
        'sub_font_size': 34,
        'sub_font': 'msyh.ttc',
        'title_color': '#333333',
        'title_font_size': 40,
        'brightness': 1.0,
        'contrast': 0.95,
        'saturation': 0.8,
        'vignette': False,
        'letterbox': False,
    },
    'vintage': {
        'name': '复古风格',
        'bg_color': (42, 31, 20),
        'sub_color': '#D7B88C',
        'sub_stroke_color': '#1a1000',
        'sub_stroke_width': 2,
        'sub_font_size': 36,
        'sub_font': 'simkai.ttf',
        'title_color': '#D7A96C',
        'title_font_size': 42,
        'brightness': 1.05,
        'contrast': 1.1,
        'saturation': 0.6,
        'vignette': True,
        'letterbox': False,
    },
    'tech': {
        'name': '科技风格',
        'bg_color': (10, 25, 41),
        'sub_color': '#00CCFF',
        'sub_stroke_color': '#001122',
        'sub_stroke_width': 2,
        'sub_font_size': 36,
        'sub_font': 'msyh.ttc',
        'title_color': '#00AAFF',
        'title_font_size': 42,
        'brightness': 0.95,
        'contrast': 1.15,
        'saturation': 1.2,
        'vignette': False,
        'letterbox': False,
    },
    'warm': {
        'name': '温暖风格',
        'bg_color': (42, 26, 16),
        'sub_color': '#FFE0C0',
        'sub_stroke_color': '#1a1000',
        'sub_stroke_width': 2,
        'sub_font_size': 36,
        'sub_font': 'msyh.ttc',
        'title_color': '#FFD7A0',
        'title_font_size': 42,
        'brightness': 1.05,
        'contrast': 1.05,
        'saturation': 1.1,
        'vignette': False,
        'letterbox': False,
    },
    'cinematic': {
        'name': '电影风格',
        'bg_color': (10, 10, 10),
        'sub_color': 'white',
        'sub_stroke_color': 'black',
        'sub_stroke_width': 2,
        'sub_font_size': 34,
        'sub_font': 'msyh.ttc',
        'title_color': '#E0E0E0',
        'title_font_size': 40,
        'brightness': 0.95,
        'contrast': 1.2,
        'saturation': 0.9,
        'vignette': True,
        'letterbox': True,
    },
    'nature': {
        'name': '自然风格',
        'bg_color': (10, 26, 10),
        'sub_color': '#C0FFC0',
        'sub_stroke_color': '#001100',
        'sub_stroke_width': 2,
        'sub_font_size': 36,
        'sub_font': 'msyh.ttc',
        'title_color': '#A0D080',
        'title_font_size': 42,
        'brightness': 1.0,
        'contrast': 1.1,
        'saturation': 1.15,
        'vignette': False,
        'letterbox': False,
    },
    'business': {
        'name': '商务风格',
        'bg_color': (15, 27, 45),
        'sub_color': 'white',
        'sub_stroke_color': '#001530',
        'sub_stroke_width': 2,
        'sub_font_size': 36,
        'sub_font': 'msyh.ttc',
        'title_color': '#A0B4C8',
        'title_font_size': 42,
        'brightness': 0.98,
        'contrast': 1.1,
        'saturation': 0.95,
        'vignette': False,
        'letterbox': False,
    },
}


def _get_style(video_style='default'):
    """Get MoviePy-compatible style config."""
    if video_style in MOVIEPY_STYLES:
        return MOVIEPY_STYLES[video_style]
    return MOVIEPY_STYLES['default']


def _get_font_path(font_name):
    """Map font name to Windows font file path. Prefer TTF over TTC for Pillow."""
    font_map = {
        'msyh.ttc': 'C:/Windows/Fonts/msyh.ttc',
        'msyh.ttf': 'C:/Windows/Fonts/msyh.ttf',
        'msyhbd.ttc': 'C:/Windows/Fonts/msyhbd.ttc',
        'simhei.ttf': 'C:/Windows/Fonts/simhei.ttf',
        'simkai.ttf': 'C:/Windows/Fonts/simkai.ttf',
        'simsun.ttc': 'C:/Windows/Fonts/simsun.ttc',
        'msjh.ttc': 'C:/Windows/Fonts/msjh.ttc',
    }
    # Pillow 对部分 .ttc 支持差，优先黑体/雅黑 ttf
    preferred = [
        'C:/Windows/Fonts/msyh.ttc',
        'C:/Windows/Fonts/msyhbd.ttc',
        'C:/Windows/Fonts/simhei.ttf',
        'C:/Windows/Fonts/msyh.ttf',
        'C:/Windows/Fonts/simsun.ttc',
        'C:/Windows/Fonts/arial.ttf',
    ]
    path = font_map.get(font_name)
    if path and os.path.exists(path):
        return path
    for p in preferred:
        if os.path.exists(p):
            return p
    for p in font_map.values():
        if os.path.exists(p):
            return p
    return 'C:/Windows/Fonts/msyh.ttc'


def _hex_or_name_to_rgb(color, default=(255, 255, 255)):
    if not color:
        return default
    if isinstance(color, (tuple, list)) and len(color) >= 3:
        return tuple(int(c) for c in color[:3])
    s = str(color).strip().lower()
    named = {
        'white': (255, 255, 255),
        'black': (0, 0, 0),
        'yellow': (255, 230, 0),
        'red': (255, 60, 60),
        'cyan': (0, 220, 255),
    }
    if s in named:
        return named[s]
    if s.startswith('#') and len(s) >= 7:
        try:
            return (int(s[1:3], 16), int(s[3:5], 16), int(s[5:7], 16))
        except ValueError:
            return default
    return default


def _wrap_text_lines(text, font, max_width, draw):
    """Wrap Chinese/English text to fit max_width."""
    text = (text or '').replace('\n', ' ').strip()
    if not text:
        return []
    lines = []
    current = ''
    for ch in text:
        trial = current + ch
        bbox = draw.textbbox((0, 0), trial, font=font)
        if bbox[2] - bbox[0] <= max_width or not current:
            current = trial
        else:
            lines.append(current)
            current = ch
    if current:
        lines.append(current)
    return lines


def _render_subtitle_pil(text, font_path, font_size, color, stroke_color, stroke_width, max_w):
    """Render subtitle to RGBA numpy array via Pillow (reliable Chinese fallback)."""
    from PIL import Image, ImageDraw, ImageFont

    try:
        font = ImageFont.truetype(font_path, font_size)
    except Exception:
        try:
            font = ImageFont.truetype('C:/Windows/Fonts/simhei.ttf', font_size)
        except Exception:
            font = ImageFont.load_default()

    # Measure with a temp image
    tmp = Image.new('RGBA', (max_w, font_size * 8), (0, 0, 0, 0))
    draw = ImageDraw.Draw(tmp)
    lines = _wrap_text_lines(text, font, max_w - 24, draw)
    if not lines:
        return None

    line_heights = []
    line_widths = []
    for line in lines:
        bbox = draw.textbbox((0, 0), line, font=font)
        line_widths.append(bbox[2] - bbox[0])
        line_heights.append(bbox[3] - bbox[1])
    pad_x, pad_y = 18, 12
    gap = max(4, font_size // 8)
    text_h = sum(line_heights) + gap * (len(lines) - 1)
    text_w = max(line_widths) if line_widths else max_w
    img_w = min(max_w, text_w + pad_x * 2)
    img_h = text_h + pad_y * 2

    img = Image.new('RGBA', (img_w, img_h), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    # Soft dark box
    draw.rounded_rectangle(
        [(0, 0), (img_w - 1, img_h - 1)],
        radius=10,
        fill=(0, 0, 0, 150),
    )

    fill = _hex_or_name_to_rgb(color)
    stroke = _hex_or_name_to_rgb(stroke_color, (0, 0, 0))
    y = pad_y
    for i, line in enumerate(lines):
        bbox = draw.textbbox((0, 0), line, font=font)
        lw = bbox[2] - bbox[0]
        x = (img_w - lw) // 2
        draw.text(
            (x, y),
            line,
            font=font,
            fill=fill + (255,),
            stroke_width=max(0, int(stroke_width or 0)),
            stroke_fill=stroke + (255,),
        )
        y += line_heights[i] + gap

    return np.array(img)



# ============================================================
# SRT parsing
# ============================================================

def _parse_srt(srt_path):
    """Parse SRT file into list of {start, end, text} segments."""
    if not srt_path or not os.path.exists(srt_path):
        return []

    with open(srt_path, 'r', encoding='utf-8') as f:
        content = f.read()

    segments = []
    pattern = re.compile(
        r'(\d+)\s*\n'
        r'(\d{2}:\d{2}:\d{2},\d{3})\s*-->\s*(\d{2}:\d{2}:\d{2},\d{3})\s*\n'
        r'((?:.*\n)*?)',
        re.MULTILINE
    )

    for match in pattern.finditer(content):
        start = _srt_time_to_seconds(match.group(2))
        end = _srt_time_to_seconds(match.group(3))
        text = match.group(4).strip()
        if text:
            segments.append({'start': start, 'end': end, 'text': text})

    return segments


def _srt_time_to_seconds(time_str):
    """Convert SRT timestamp to seconds."""
    h, m, rest = time_str.split(':')
    s, ms = rest.split(',')
    return int(h) * 3600 + int(m) * 60 + int(s) + int(ms) / 1000.0


# ============================================================
# Color grading
# ============================================================

def _make_color_grade_fn(style):
    """Create a per-frame color grading function for MoviePy transform()."""
    brightness = style.get('brightness', 1.0)
    contrast = style.get('contrast', 1.0)
    saturation = style.get('saturation', 1.0)

    if brightness == 1.0 and contrast == 1.0 and saturation == 1.0:
        return None  # No adjustment needed

    def grade_fn(get_frame, t):
        frame = get_frame(t).astype(np.float32)
        # Brightness
        frame = frame * brightness
        # Contrast
        frame = (frame - 128.0) * contrast + 128.0
        # Saturation
        gray = np.mean(frame, axis=2, keepdims=True)
        frame = gray + (frame - gray) * saturation
        return np.clip(frame, 0, 255).astype(np.uint8)

    return grade_fn


def _make_vignette_overlay(width, height, strength=0.5):
    """Create a vignette overlay as a numpy array."""
    y, x = np.ogrid[:height, :width]
    center_x, center_y = width / 2, height / 2
    dist = np.sqrt((x - center_x) ** 2 + (y - center_y) ** 2)
    max_dist = np.sqrt(center_x ** 2 + center_y ** 2)
    vignette = (dist / max_dist) ** 2 * strength * 255
    vignette = np.clip(vignette, 0, 255).astype(np.uint8)

    # Create RGBA overlay
    overlay = np.zeros((height, width, 4), dtype=np.uint8)
    overlay[:, :, 3] = vignette  # Alpha channel
    return overlay


def _make_bottom_gradient(width, height, gradient_h=None, max_alpha=160):
    """Create a bottom gradient overlay for subtitle readability.

    Generates a smooth gradient from transparent (top) to semi-transparent
    black (bottom), covering the lower portion of the video.
    """
    if gradient_h is None:
        gradient_h = int(height * 0.22)  # Bottom 22% of video

    # Create gradient: 0 alpha at top, max_alpha at bottom
    alpha = np.linspace(0, max_alpha, gradient_h, dtype=np.float32)
    # Apply ease-in for smoother transition
    alpha = alpha ** 0.7
    alpha = np.clip(alpha, 0, max_alpha).astype(np.uint8)

    # Build RGBA array (full width, gradient height)
    overlay = np.zeros((gradient_h, width, 4), dtype=np.uint8)
    overlay[:, :, 3] = alpha[:, np.newaxis]  # Broadcast across width

    return overlay


def _make_subtitle_bg(text_w, text_h, padding=16, alpha=140):
    """Create a semi-transparent dark background box for subtitle text."""
    bg_w = text_w + padding * 2
    bg_h = text_h + padding
    overlay = np.zeros((bg_h, bg_w, 4), dtype=np.uint8)
    overlay[:, :, :3] = 0  # Black background
    overlay[:, :, 3] = alpha  # Semi-transparent
    return overlay


# ============================================================
# Ken Burns effect for images
# ============================================================

def _create_ken_burns_clip(image_path, duration, target_w, target_h, fps, zoom_dir='in', pan_dir='center'):
    """Create an ImageClip with smooth Ken Burns zoom + pan effect.

    Uses Resize(zoom_fn) for smooth zooming and transform() for panning/cropping,
    since MoviePy 2.x Crop effect doesn't support dynamic x_center/y_center.

    Args:
        image_path: path to image file
        duration: clip duration in seconds
        target_w, target_h: target video dimensions
        fps: frames per second
        zoom_dir: 'in' (zoom in) or 'out' (zoom out)
        pan_dir: 'center', 'left', 'right', 'up', 'down' — panning direction
    """
    from moviepy import ImageClip
    from moviepy.video.fx import Resize

    # Overscale by 20% to allow panning without showing edges
    overscale = 1.2
    overscale_w = int(target_w * overscale)
    overscale_h = int(target_h * overscale)

    clip = ImageClip(image_path).with_duration(duration).with_fps(fps)

    # First resize to cover overscaled dimensions
    clip = clip.with_effects([Resize(width=overscale_w, height=overscale_h)])

    # Apply smooth zoom using a time function with ease-in-out
    zoom_amount = 0.15  # 15% zoom over the clip duration

    if zoom_dir == 'in':
        def zoom_fn(t):
            progress = min(t / max(duration, 0.1), 1.0)
            eased = 0.5 * (1 - np.cos(np.pi * progress))
            return 1.0 + zoom_amount * eased
    else:
        def zoom_fn(t):
            progress = min(t / max(duration, 0.1), 1.0)
            eased = 0.5 * (1 - np.cos(np.pi * progress))
            return (1.0 + zoom_amount) * (1.0 - zoom_amount / (1.0 + zoom_amount) * eased)

    clip = clip.with_effects([Resize(zoom_fn)])

    # Pan and crop using transform() — MoviePy 2.x Crop doesn't support dynamic centers
    pan_range = 0.08  # 8% of available margin

    def _make_crop_pan_fn(pdir):
        """Create a transform function that crops to target size with panning."""
        def crop_pan_fn(get_frame, t):
            frame = get_frame(t)
            h, w = frame.shape[:2]
            progress = min(t / max(duration, 0.1), 1.0)
            eased = 0.5 * (1 - np.cos(np.pi * progress))

            # Calculate available margin
            margin_x = max(0, w - target_w)
            margin_y = max(0, h - target_h)

            if pdir == 'left':
                x_offset = int(margin_x * (0.5 + pan_range * (0.5 - eased)))
            elif pdir == 'right':
                x_offset = int(margin_x * (0.5 - pan_range * (0.5 - eased)))
            else:
                x_offset = margin_x // 2

            if pdir == 'up':
                y_offset = int(margin_y * (0.5 + pan_range * (0.5 - eased)))
            elif pdir == 'down':
                y_offset = int(margin_y * (0.5 - pan_range * (0.5 - eased)))
            else:
                y_offset = margin_y // 2

            # Clamp to valid range
            x_offset = max(0, min(x_offset, margin_x))
            y_offset = max(0, min(y_offset, margin_y))

            return frame[y_offset:y_offset + target_h, x_offset:x_offset + target_w]

        return crop_pan_fn

    clip = clip.transform(_make_crop_pan_fn(pan_dir))

    return clip


def _create_image_clips(image_paths, total_duration, target_w, target_h, fps):
    """Create image clips with Ken Burns + pan and crossfade transitions."""
    from moviepy.video.fx import CrossFadeIn, CrossFadeOut

    if not image_paths:
        return []

    n = len(image_paths)
    # Each image gets equal time, with 0.5s crossfade overlap
    transition_dur = 0.5 if n > 1 else 0
    # Account for overlap: total = n * per_image - (n-1) * transition_dur
    # So per_image = (total + (n-1) * transition_dur) / n
    per_image = (total_duration + (n - 1) * transition_dur) / n if n > 1 else total_duration

    # Alternate zoom direction and pan direction for variety
    pan_options = ['center', 'left', 'right', 'up', 'down']
    zoom_options = ['in', 'out']

    clips = []
    for i, img_path in enumerate(image_paths):
        zoom_dir = zoom_options[i % 2]
        pan_dir = pan_options[i % len(pan_options)]
        clip = _create_ken_burns_clip(img_path, per_image, target_w, target_h, fps, zoom_dir, pan_dir)

        # Add crossfade in for clips after the first
        if i > 0:
            clip = clip.with_effects([CrossFadeIn(transition_dur)])
            # Shift start time to overlap with previous clip
            clip = clip.with_start(i * per_image - i * transition_dur)
        else:
            clip = clip.with_start(0)

        clips.append(clip)

    return clips


# ============================================================
# Subtitle overlay
# ============================================================

def _create_subtitle_clips(srt_path, style, target_w, target_h, fps):
    """Create subtitle overlays. Prefer Pillow render so Chinese always shows."""
    from moviepy import ImageClip
    from moviepy.video.fx import FadeIn, FadeOut

    segments = _parse_srt(srt_path)
    if not segments:
        print(f'[VideoComposer] No subtitle segments from: {srt_path}')
        return []

    font_path = _get_font_path(style.get('sub_font', 'msyh.ttc'))
    font_size = int(style.get('sub_font_size', 42) or 42)
    # 竖屏口播字幕略放大
    if target_h >= target_w:
        font_size = max(font_size, 44)
    sub_color = style.get('sub_color', 'white')
    stroke_color = style.get('sub_stroke_color', 'black')
    stroke_width = style.get('sub_stroke_width', 3)

    text_max_w = target_w - 80
    # 贴屏幕下方：按字幕块高度 + 底部安全边距定位（避免误放顶部）
    bottom_margin = max(48, int(target_h * 0.06))

    clips = []
    ok = 0
    for seg in segments:
        dur = seg['end'] - seg['start']
        if dur <= 0:
            continue
        try:
            arr = _render_subtitle_pil(
                seg['text'], font_path, font_size,
                sub_color, stroke_color, stroke_width, text_max_w,
            )
            if arr is None:
                continue
            sub_h = int(arr.shape[0])
            sub_y = max(0, target_h - sub_h - bottom_margin)
            clip = ImageClip(arr, duration=dur).with_position(('center', sub_y))
            clip = clip.with_start(seg['start']).with_fps(fps)
            fade_dur = min(0.2, dur / 4)
            clip = clip.with_effects([FadeIn(fade_dur), FadeOut(fade_dur)])
            clips.append(clip)
            ok += 1
        except Exception as e:
            print(f'[VideoComposer] subtitle render error: {e}')
            continue

    print(f'[VideoComposer] Subtitles ready: {ok}/{len(segments)} (font={font_path})')
    return clips


# ============================================================
# 口播模板：背景 + 居中人像（完整显示，不狠裁）
# ============================================================

def _cover_resize_image(img_path, target_w, target_h):
    """Load image and cover-fit to target size (center crop). Returns RGB uint8 array."""
    from PIL import Image
    img = Image.open(img_path).convert('RGB')
    iw, ih = img.size
    scale = max(target_w / iw, target_h / ih)
    nw, nh = int(iw * scale + 0.5), int(ih * scale + 0.5)
    img = img.resize((nw, nh), Image.Resampling.LANCZOS)
    left = max(0, (nw - target_w) // 2)
    top = max(0, (nh - target_h) // 2)
    img = img.crop((left, top, left + target_w, top + target_h))
    return np.array(img)


def _cover_fit_clip(clip, target_w, target_h):
    """
    视频/画面 cover 铺满目标尺寸并居中裁切。

    注意：MoviePy 的 Resize(width=…, height=…) 实际只认 height（忽略 width），
    若再配合 Crop(x_center=target_w/2) 会裁到画面左侧，横屏人像会变成只有模糊背景。
    """
    from moviepy.video.fx import Resize, Crop
    vw, vh = clip.size
    if not vw or not vh:
        return clip
    scale = max(target_w / vw, target_h / vh)
    fitted = clip.with_effects([Resize(scale)])
    return fitted.with_effects([Crop(
        width=target_w,
        height=target_h,
        x_center=fitted.w / 2,
        y_center=fitted.h / 2,
    )])


def _contain_resize_rgba(img_path, max_w, max_h):
    """Load person image contain-fit inside box, keep alpha if present."""
    from PIL import Image
    img = Image.open(img_path).convert('RGBA')
    iw, ih = img.size
    scale = min(max_w / iw, max_h / ih, 1.0)  # 不放大超过原图太多时可改为不限制 1.0
    scale = min(max_w / iw, max_h / ih)
    nw, nh = max(1, int(iw * scale + 0.5)), max(1, int(ih * scale + 0.5))
    img = img.resize((nw, nh), Image.Resampling.LANCZOS)
    return np.array(img), nw, nh


def _create_talking_head_base(bg_path, person_path, duration, width, height, fps, style):
    """
    口播底板：背景铺满 + 人物居中完整显示（留出底部字幕区）。
    """
    from moviepy import ImageClip, ColorClip, CompositeVideoClip, VideoFileClip
    from moviepy.video.fx import Resize, Crop

    bg_color = style.get('bg_color', (26, 26, 46))
    layers = []
    video_refs = []

    # 1) Background
    if bg_path and os.path.exists(bg_path):
        ext = os.path.splitext(bg_path)[1].lower()
        if ext in ('.mp4', '.mov', '.webm', '.avi', '.mkv'):
            try:
                vclip = VideoFileClip(bg_path)
                video_refs.append(vclip)
                v_dur = min(vclip.duration, duration)
                vclip = vclip.subclipped(0, v_dur)
                # cover fit
                vw, vh = vclip.w, vclip.h
                scale = max(width / vw, height / vh)
                vclip = vclip.with_effects([Resize(scale)])
                vclip = vclip.with_effects([Crop(
                    width=width, height=height,
                    x_center=vclip.w / 2, y_center=vclip.h / 2,
                )])
                vclip = vclip.with_fps(fps).with_duration(duration)
                if v_dur < duration:
                    # freeze last frame for remainder via looping last frame as image
                    from moviepy import concatenate_videoclips
                    last = vclip.get_frame(max(0, v_dur - 0.04))
                    freeze = ImageClip(last, duration=duration - v_dur)
                    vclip = concatenate_videoclips([vclip.subclipped(0, v_dur), freeze])
                layers.append(vclip.with_position((0, 0)))
            except Exception as e:
                print(f'[VideoComposer] talking bg video failed: {e}')
                layers.append(ColorClip(size=(width, height), color=bg_color, duration=duration))
        else:
            try:
                bg_arr = _cover_resize_image(bg_path, width, height)
                # 轻微压暗，突出人像
                bg_arr = (bg_arr.astype(np.float32) * 0.72).clip(0, 255).astype(np.uint8)
                layers.append(ImageClip(bg_arr, duration=duration).with_position((0, 0)))
            except Exception as e:
                print(f'[VideoComposer] talking bg image failed: {e}')
                layers.append(ColorClip(size=(width, height), color=bg_color, duration=duration))
    else:
        layers.append(ColorClip(size=(width, height), color=bg_color, duration=duration))

    # 2) Person — 完整显示，放在画面中上部，底部留给字幕
    if person_path and os.path.exists(person_path):
        try:
            max_w = int(width * 0.88)
            max_h = int(height * 0.58)
            person_arr, pw, ph = _contain_resize_rgba(person_path, max_w, max_h)
            person = ImageClip(person_arr, duration=duration).with_fps(fps)
            # 垂直：约从 10% 高度开始，保证脚/半身不被字幕挡住
            y = int(height * 0.10)
            x = (width - pw) // 2
            person = person.with_position((x, y))
            layers.append(person)
            print(f'[VideoComposer] Talking person {pw}x{ph} at ({x},{y})')
        except Exception as e:
            print(f'[VideoComposer] talking person failed: {e}')
    else:
        print('[VideoComposer] Talking layout: no person image')

    base = CompositeVideoClip(layers, size=(width, height)).with_duration(duration).with_fps(fps)
    return base, video_refs

def _create_title_clip(title_text, style, duration, target_w, fps):
    """Create an animated title overlay at the top."""
    from moviepy import TextClip
    from moviepy.video.fx import FadeIn, FadeOut

    if not title_text:
        return None

    font_path = _get_font_path(style.get('sub_font', 'msyh.ttc'))
    title_color = style.get('title_color', 'white')
    title_size = style.get('title_font_size', 42)

    try:
        title_clip = TextClip(
            text=title_text,
            font=font_path,
            font_size=title_size,
            color=title_color,
            stroke_color='black',
            stroke_width=2,
            duration=min(duration, 5),  # Title shows for max 5 seconds
            text_align='center',
            size=(target_w - 100, None),
            method='caption',
        )
        title_clip = title_clip.with_position(('center', 60))
        title_clip = title_clip.with_effects([FadeIn(0.5), FadeOut(0.5)])
        return title_clip
    except Exception as e:
        print(f'[VideoComposer] Title clip error: {e}')
        return None


# ============================================================
# Main composition function
# ============================================================

def compose_video_moviepy(audio_path, subtitle_path, image_paths, output_path,
                           title_text='', video_style='default', video_paths=None,
                           task_params=None, scenes=None):
    """
    Compose a video using MoviePy 2.x.

    Features:
      - Scene-based material switching (if scenes provided):
        each scene shows its matched material for its duration
      - Smooth Ken Burns zoom on images (function-based animation)
      - Crossfade transitions between scenes/segments
      - TextClip subtitles with per-style font/color/stroke
      - Color grading (brightness/contrast/saturation) per style
      - Vignette overlay for cinematic styles
      - Letterbox bars for cinematic style
      - Title overlay with fade animation
      - Fade in/out at video start/end

    Args:
        audio_path: path to audio file (.mp3)
        subtitle_path: path to SRT subtitle file (.srt)
        image_paths: list of image file paths
        output_path: path to save output video (.mp4)
        title_text: optional title overlay text
        video_style: style key from MOVIEPY_STYLES
        video_paths: list of video file paths for background
        task_params: dict with per-task overrides
        scenes: optional list of {start, end, material_path, material_type, text, keywords}
                for scene-based material switching

    Returns:
        dict with: video_path, duration, file_size
    """
    from moviepy import (
        VideoFileClip, AudioFileClip, ColorClip,
        CompositeVideoClip, concatenate_videoclips
    )
    from moviepy.video.fx import FadeIn, FadeOut, CrossFadeIn

    # Merge config defaults with per-task overrides
    config = get_video_config()
    tp = task_params or {}
    resolution = tp.get('resolution') or config.get('default_resolution', '1080x1920') or '1080x1920'
    fps = int(tp.get('fps') or config.get('default_fps', '30') or '30')
    render_quality = tp.get('render_quality') or config.get('default_render_quality', 'high') or 'high'
    fade_enabled = tp.get('fade_transition') or config.get('default_fade_transition', 'true') or 'true'
    show_title = tp.get('title_overlay') or config.get('default_title_overlay', 'true') or 'true'
    if render_quality == 'preview':
        # Fast preview: 480p @ 24fps
        base_w, base_h = map(int, resolution.split('x'))
        if base_w > base_h:  # landscape
            width, height = 640, 360
        else:  # portrait
            width, height = 360, 640
        fps = min(fps, 24)
    elif render_quality == 'medium':
        # Medium quality: 720p @ 24fps
        base_w, base_h = map(int, resolution.split('x'))
        if base_w > base_h:  # landscape
            width, height = 1280, 720
        else:  # portrait
            width, height = 720, 1280
        fps = min(fps, 24)
    else:
        # High quality: full resolution
        width, height = map(int, resolution.split('x'))
    style = _get_style(video_style)

    # Get audio duration
    audio = AudioFileClip(audio_path)
    duration = audio.duration

    print(f'[VideoComposer] Composing video: {width}x{height} @ {fps}fps, duration={duration:.1f}s, style={video_style}')

    # 1. Create background clip(s)
    bg_clips = []
    bg_video_refs = []  # keep references for cleanup
    talking_base = None

    compose_layout = (tp.get('compose_layout') or 'default').strip().lower()
    if compose_layout in ('talking', 'koubo', 'portrait'):
        print('[VideoComposer] Talking-head layout (背景+居中人像)')
        talking_base, refs = _create_talking_head_base(
            tp.get('bg_path') or '',
            tp.get('person_path') or '',
            duration, width, height, fps, style,
        )
        bg_video_refs.extend(refs)
    # Scene-based material switching (priority over sequential playback)
    elif scenes and any(s.get('material_path') for s in scenes) and any(
        s.get('start') is not None and s.get('end') is not None for s in scenes
    ):
        print(f'[VideoComposer] Scene-based mode: {len(scenes)} scenes')
        pan_options = ['center', 'left', 'right', 'up', 'down']
        zoom_options = ['in', 'out']

        for i, scene in enumerate(scenes):
            s_start = scene.get('start')
            s_end = scene.get('end')
            if s_start is None:
                s_start = 0.0
            if s_end is None:
                s_end = duration
            s_dur = max(0.5, float(s_end) - float(s_start))
            mat_path = scene.get('material_path', '')
            mat_type = scene.get('material_type', 'image')

            if mat_path and os.path.exists(mat_path):
                if mat_type == 'video':
                    # Video material: take subclip for scene duration
                    try:
                        vclip = VideoFileClip(mat_path)
                        bg_video_refs.append(vclip)
                        v_dur = min(vclip.duration, s_dur)
                        vclip = vclip.subclipped(0, v_dur)
                        vclip = _cover_fit_clip(vclip, width, height)
                        vclip = vclip.with_fps(fps)
                        vclip = vclip.with_start(s_start)

                        # If video shorter than scene, freeze last frame for remaining time
                        if v_dur < s_dur:
                            remaining = s_dur - v_dur
                            try:
                                last_frame = vclip.get_frame(max(0, v_dur - 0.04))
                                from moviepy import ImageClip
                                freeze = ImageClip(last_frame, duration=remaining)
                                freeze = freeze.with_fps(fps)
                                freeze = freeze.with_start(s_start + v_dur)
                                bg_clips.append(vclip)
                                bg_clips.append(freeze)
                            except Exception:
                                bg_clips.append(vclip.with_duration(s_dur))
                        else:
                            bg_clips.append(vclip)
                        print(f'  Scene {i}: video {os.path.basename(mat_path)} ({s_dur:.1f}s)')
                    except Exception as e:
                        print(f'  Scene {i}: video load failed: {e}, using color bg')
                        bg_clip = ColorClip(size=(width, height), color=style['bg_color'], duration=s_dur)
                        bg_clip = bg_clip.with_fps(fps).with_start(s_start)
                        bg_clips.append(bg_clip)
                else:
                    # Image material: Ken Burns for scene duration
                    zoom_dir = zoom_options[i % 2]
                    pan_dir = pan_options[i % len(pan_options)]
                    try:
                        img_clip = _create_ken_burns_clip(mat_path, s_dur, width, height, fps, zoom_dir, pan_dir)
                        img_clip = img_clip.with_start(s_start)
                        # Crossfade from previous scene
                        if i > 0:
                            img_clip = img_clip.with_effects([CrossFadeIn(0.5)])
                        bg_clips.append(img_clip)
                        print(f'  Scene {i}: image {os.path.basename(mat_path)} ({s_dur:.1f}s)')
                    except Exception as e:
                        print(f'  Scene {i}: image load failed: {e}, using color bg')
                        bg_clip = ColorClip(size=(width, height), color=style['bg_color'], duration=s_dur)
                        bg_clip = bg_clip.with_fps(fps).with_start(s_start)
                        bg_clips.append(bg_clip)
            else:
                # No material for this scene: color background
                bg_clip = ColorClip(size=(width, height), color=style['bg_color'], duration=s_dur)
                bg_clip = bg_clip.with_fps(fps).with_start(s_start)
                bg_clips.append(bg_clip)
                print(f'  Scene {i}: color bg ({s_dur:.1f}s)')

    elif video_paths:
        # Sequential mode: video + images (no scenes)
        elapsed = 0.0
        bg_video_ref = VideoFileClip(video_paths[0])
        bg_video_refs.append(bg_video_ref)
        video_dur = min(bg_video_ref.duration, duration)
        video_clip = bg_video_ref.subclipped(0, video_dur)
        video_clip = _cover_fit_clip(video_clip, width, height)
        video_clip = video_clip.with_fps(fps)
        video_clip = video_clip.with_start(0)
        bg_clips.append(video_clip)
        elapsed = video_dur
        print(f'[VideoComposer] Video material: {video_dur:.1f}s, remaining: {duration - elapsed:.1f}s')

        if image_paths and elapsed < duration:
            remaining = duration - elapsed
            img_clips = _create_image_clips(image_paths, remaining, width, height, fps)
            if img_clips:
                transition = 0.5
                for i, clip in enumerate(img_clips):
                    new_start = clip.start + elapsed
                    if elapsed > 0 and i == 0:
                        clip = clip.with_effects([CrossFadeIn(transition)])
                        new_start = elapsed - transition
                    clip = clip.with_start(new_start)
                    bg_clips.append(clip)
                elapsed = duration
                print(f'[VideoComposer] Image materials: {remaining:.1f}s filled with {len(image_paths)} images')

        # If video was shorter than audio and no images to fill, freeze last frame
        if elapsed < duration and not image_paths:
            remaining = duration - elapsed
            try:
                last_frame = video_clip.get_frame(max(0, video_dur - 0.04))
                from moviepy import ImageClip
                freeze_clip = ImageClip(last_frame, duration=remaining)
                freeze_clip = freeze_clip.with_fps(fps)
                freeze_clip = freeze_clip.with_start(elapsed)
                bg_clips.append(freeze_clip)
                print(f'[VideoComposer] Freeze last frame for {remaining:.1f}s')
            except Exception as e:
                print(f'[VideoComposer] Freeze frame failed: {e}, using color background')
                bg_clip = ColorClip(size=(width, height), color=style['bg_color'], duration=duration - elapsed)
                bg_clip = bg_clip.with_fps(fps).with_start(elapsed)
                bg_clips.append(bg_clip)

    elif image_paths:
        # Images only (no video, no scenes)
        img_clips = _create_image_clips(image_paths, duration, width, height, fps)
        bg_clips = img_clips

    if talking_base is not None:
        base_video = talking_base
    else:
        if not bg_clips:
            # No materials at all: use colored background
            bg_clip = ColorClip(size=(width, height), color=style['bg_color'], duration=duration)
            bg_clip = bg_clip.with_fps(fps)
            bg_clips = [bg_clip]

        # 2. Build the base video from background clips
        if len(bg_clips) == 1:
            base_video = bg_clips[0].with_duration(duration)
        else:
            # For multiple image clips with crossfade overlap, use CompositeVideoClip
            base_video = CompositeVideoClip(bg_clips, size=(width, height))
            # Ensure exact duration matches audio
            base_video = base_video.with_duration(duration)

        base_video = base_video.with_fps(fps)

    # 3. Apply color grading
    grade_fn = _make_color_grade_fn(style)
    if grade_fn:
        base_video = base_video.transform(grade_fn)

    # 4. Add audio (+ optional BGM)
    bgm_path = (tp.get('bgm_path') or '').strip()
    if bgm_path and os.path.exists(bgm_path):
        try:
            from moviepy import CompositeAudioClip
            try:
                bgm_vol = float(tp.get('bgm_volume') or 0.12)
            except (TypeError, ValueError):
                bgm_vol = 0.12
            bgm = AudioFileClip(bgm_path)
            if hasattr(bgm, 'with_volume_scaled'):
                bgm = bgm.with_volume_scaled(bgm_vol)
            elif hasattr(bgm, 'volumex'):
                bgm = bgm.volumex(bgm_vol)
            if bgm.duration < duration:
                loops = int(duration / max(bgm.duration, 0.1)) + 1
                from moviepy import concatenate_audioclips
                bgm = concatenate_audioclips([bgm] * loops)
            bgm = bgm.subclipped(0, duration) if hasattr(bgm, 'subclipped') else bgm.subclip(0, duration)
            audio = CompositeAudioClip([audio, bgm])
            print(f'[VideoComposer] Mixed BGM at volume {bgm_vol}')
        except Exception as e:
            print(f'[VideoComposer] BGM mix skipped: {e}')
    base_video = base_video.with_audio(audio)

    # 5. Build overlay layers — 字幕必须在最上层，否则会被渐变盖住
    underlays = []
    overlays = []

    # Vignette / gradient under text
    if style.get('vignette'):
        try:
            from moviepy import ImageClip
            vignette_arr = _make_vignette_overlay(width, height, strength=0.4)
            vignette_clip = ImageClip(vignette_arr, duration=duration).with_position((0, 0))
            vignette_clip = vignette_clip.with_fps(fps)
            underlays.append(vignette_clip)
        except Exception as e:
            print(f'[VideoComposer] Vignette error: {e}')

    try:
        from moviepy import ImageClip
        gradient_arr = _make_bottom_gradient(width, height, max_alpha=140)
        gradient_h = gradient_arr.shape[0]
        gradient_clip = ImageClip(gradient_arr, duration=duration).with_position((0, height - gradient_h))
        gradient_clip = gradient_clip.with_fps(fps)
        underlays.append(gradient_clip)
    except Exception as e:
        print(f'[VideoComposer] Gradient overlay error: {e}')

    if style.get('letterbox'):
        bar_h = int(height * 0.06)
        from moviepy import ColorClip as _CC
        top_bar = _CC(size=(width, bar_h), color=(0, 0, 0), duration=duration)
        bottom_bar = _CC(size=(width, bar_h), color=(0, 0, 0), duration=duration)
        top_bar = top_bar.with_position((0, 0)).with_fps(fps)
        bottom_bar = bottom_bar.with_position((0, height - bar_h)).with_fps(fps)
        underlays.extend([top_bar, bottom_bar])

    if show_title == 'true':
        title_clip = _create_title_clip(title_text, style, duration, width, fps)
        if title_clip:
            overlays.append(title_clip)

    sub_clips = _create_subtitle_clips(subtitle_path, style, width, height, fps)
    overlays.extend(sub_clips)

    # 6. Composite everything together（字幕最后叠，保证可见）
    all_clips = [base_video] + underlays + overlays
    final = CompositeVideoClip(all_clips, size=(width, height))
    final = final.with_duration(duration)

    # 7. Add fade in/out at start/end
    if fade_enabled == 'true':
        fade_dur = 0.5
        final = final.with_effects([FadeIn(fade_dur), FadeOut(fade_dur)])

    # 8. Write to file
    print(f'[VideoComposer] Rendering video to: {output_path}')

    # Use a temp audio file in the system temp directory to avoid
    # sandbox issues with file deletion in the working directory
    import tempfile
    temp_audio = os.path.join(tempfile.gettempdir(), f'moviepy_audio_{os.getpid()}.mp4')

    # Use optimized encoding settings:
    # - preset='ultrafast' for fastest encoding (least CPU on encoding)
    # - threads=8 for parallel frame processing
    # - CRF 23 = visually lossless, good balance of quality/size
    # - logger=None to skip progress bar I/O (speeds up rendering ~10%)
    # - remove_temp=False to prevent sandbox deletion errors
    final.write_videofile(
        output_path,
        fps=fps,
        codec='libx264',
        audio_codec='aac',
        preset='ultrafast',
        threads=8,
        ffmpeg_params=['-crf', '23', '-pix_fmt', 'yuv420p', '-movflags', '+faststart'],
        temp_audiofile=temp_audio,
        remove_temp=False,
        logger=None,
    )

    # Clean up temp audio file manually (ignore errors)
    try:
        if os.path.exists(temp_audio):
            os.remove(temp_audio)
    except Exception:
        pass

    file_size = os.path.getsize(output_path) if os.path.exists(output_path) else 0
    print(f'[VideoComposer] Done: {file_size} bytes')

    # Cleanup
    try:
        audio.close()
        for ref in bg_video_refs:
            if hasattr(ref, 'close'):
                ref.close()
    except Exception:
        pass

    return {
        'video_path': output_path,
        'duration': duration,
        'file_size': file_size,
    }
