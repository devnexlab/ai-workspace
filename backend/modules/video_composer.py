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
        'sub_font_size': 36,
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
    """Map font name to Windows font file path."""
    font_map = {
        'msyh.ttc': 'C:/Windows/Fonts/msyh.ttc',
        'simhei.ttf': 'C:/Windows/Fonts/simhei.ttf',
        'simkai.ttf': 'C:/Windows/Fonts/simkai.ttf',
        'simsun.ttc': 'C:/Windows/Fonts/simsun.ttc',
        'msjh.ttc': 'C:/Windows/Fonts/msjh.ttc',
    }
    path = font_map.get(font_name, 'C:/Windows/Fonts/msyh.ttc')
    if os.path.exists(path):
        return path
    # Fallback
    for p in font_map.values():
        if os.path.exists(p):
            return p
    return 'C:/Windows/Fonts/msyh.ttc'


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
    """Create TextClip overlays for each subtitle segment with background box."""
    from moviepy import TextClip, ImageClip
    from moviepy.video.fx import FadeIn, FadeOut

    segments = _parse_srt(srt_path)
    if not segments:
        return []

    font_path = _get_font_path(style.get('sub_font', 'msyh.ttc'))
    font_size = style.get('sub_font_size', 36)
    sub_color = style.get('sub_color', 'white')
    stroke_color = style.get('sub_stroke_color', 'black')
    stroke_width = style.get('sub_stroke_width', 2)

    # Subtitle area dimensions
    text_max_w = target_w - 100  # Leave 50px margin each side
    sub_y = target_h - 160  # Position from top (near bottom)

    clips = []
    for seg in segments:
        dur = seg['end'] - seg['start']
        if dur <= 0:
            continue

        try:
            txt_clip = TextClip(
                text=seg['text'],
                font=font_path,
                font_size=font_size,
                color=sub_color,
                stroke_color=stroke_color,
                stroke_width=stroke_width,
                duration=dur,
                text_align='center',
                size=(text_max_w, None),
                method='caption',
            )

            # Get text dimensions
            txt_w = txt_clip.w
            txt_h = txt_clip.h

            # Create semi-transparent background box behind text
            bg_padding = 12
            bg_arr = np.zeros((txt_h + bg_padding * 2, txt_w + bg_padding * 2, 4), dtype=np.uint8)
            bg_arr[:, :, :3] = 0  # Black
            bg_arr[:, :, 3] = 130  # Semi-transparent

            bg_clip = ImageClip(bg_arr, duration=dur)
            bg_clip = bg_clip.with_position(('center', sub_y - bg_padding))
            bg_clip = bg_clip.with_start(seg['start'])

            # Position text clip
            txt_clip = txt_clip.with_position(('center', sub_y))
            txt_clip = txt_clip.with_start(seg['start'])

            # Subtle fade in/out
            fade_dur = min(0.25, dur / 4)
            txt_clip = txt_clip.with_effects([FadeIn(fade_dur), FadeOut(fade_dur)])
            bg_clip = bg_clip.with_effects([FadeIn(fade_dur), FadeOut(fade_dur)])

            clips.append(bg_clip)
            clips.append(txt_clip)
        except Exception as e:
            print(f'[VideoComposer] TextClip error for segment: {e}')
            continue

    return clips


# ============================================================
# Title overlay
# ============================================================

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

    # Scene-based material switching (priority over sequential playback)
    if scenes and any(s.get('material_path') for s in scenes):
        print(f'[VideoComposer] Scene-based mode: {len(scenes)} scenes')
        pan_options = ['center', 'left', 'right', 'up', 'down']
        zoom_options = ['in', 'out']

        for i, scene in enumerate(scenes):
            s_start = scene.get('start', 0)
            s_end = scene.get('end', duration)
            s_dur = max(0.5, s_end - s_start)
            mat_path = scene.get('material_path', '')
            mat_type = scene.get('material_type', 'image')

            if mat_path and os.path.exists(mat_path):
                if mat_type == 'video':
                    # Video material: take subclip for scene duration
                    try:
                        from moviepy.video.fx import Resize, Crop
                        vclip = VideoFileClip(mat_path)
                        bg_video_refs.append(vclip)
                        v_dur = min(vclip.duration, s_dur)
                        vclip = vclip.subclipped(0, v_dur)
                        vclip = vclip.with_effects([Resize(width=width, height=height)])
                        vclip = vclip.with_effects([Crop(width=width, height=height,
                                                          x_center=width/2, y_center=height/2)])
                        vclip = vclip.with_fps(fps)
                        vclip = vclip.with_start(s_start)

                        # If video shorter than scene, freeze last frame for remaining time
                        if v_dur < s_dur:
                            remaining = s_dur - v_dur
                            try:
                                last_frame = vclip.get_frame(v_dur - 0.01)
                                from moviepy import ImageClip
                                freeze = ImageClip(last_frame, duration=remaining)
                                freeze = freeze.with_effects([Resize(width=width, height=height)])
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
        from moviepy.video.fx import Resize, Crop
        elapsed = 0.0
        bg_video_ref = VideoFileClip(video_paths[0])
        bg_video_refs.append(bg_video_ref)
        video_dur = min(bg_video_ref.duration, duration)
        video_clip = bg_video_ref.subclipped(0, video_dur)
        video_clip = video_clip.with_effects([Resize(width=width, height=height)])
        video_clip = video_clip.with_effects([Crop(width=width, height=height, x_center=width/2, y_center=height/2)])
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
                last_frame = bg_video_ref.get_frame(bg_video_ref.duration - 0.01)
                from moviepy import ImageClip
                freeze_clip = ImageClip(last_frame, duration=remaining)
                freeze_clip = freeze_clip.with_effects([Resize(width=width, height=height)])
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

    # 4. Add audio
    base_video = base_video.with_audio(audio)

    # 5. Build overlay layers (subtitles, title, vignette, letterbox)
    overlay_clips = []

    # Subtitle clips
    sub_clips = _create_subtitle_clips(subtitle_path, style, width, height, fps)
    overlay_clips.extend(sub_clips)

    # Title clip
    if show_title == 'true':
        title_clip = _create_title_clip(title_text, style, duration, width, fps)
        if title_clip:
            overlay_clips.append(title_clip)

    # Vignette overlay
    if style.get('vignette'):
        try:
            from moviepy import ImageClip
            vignette_arr = _make_vignette_overlay(width, height, strength=0.4)
            vignette_clip = ImageClip(vignette_arr, duration=duration).with_position((0, 0))
            vignette_clip = vignette_clip.with_fps(fps)
            overlay_clips.append(vignette_clip)
        except Exception as e:
            print(f'[VideoComposer] Vignette error: {e}')

    # Bottom gradient overlay for subtitle readability (always on)
    try:
        from moviepy import ImageClip
        gradient_arr = _make_bottom_gradient(width, height, max_alpha=140)
        gradient_h = gradient_arr.shape[0]
        gradient_clip = ImageClip(gradient_arr, duration=duration).with_position((0, height - gradient_h))
        gradient_clip = gradient_clip.with_fps(fps)
        overlay_clips.append(gradient_clip)
    except Exception as e:
        print(f'[VideoComposer] Gradient overlay error: {e}')

    # Letterbox bars (cinematic style)
    if style.get('letterbox'):
        bar_h = int(height * 0.06)
        from moviepy import ColorClip
        top_bar = ColorClip(size=(width, bar_h), color=(0, 0, 0), duration=duration)
        bottom_bar = ColorClip(size=(width, bar_h), color=(0, 0, 0), duration=duration)
        top_bar = top_bar.with_position((0, 0)).with_fps(fps)
        bottom_bar = bottom_bar.with_position((0, height - bar_h)).with_fps(fps)
        overlay_clips.extend([top_bar, bottom_bar])

    # 6. Composite everything together
    all_clips = [base_video] + overlay_clips
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
