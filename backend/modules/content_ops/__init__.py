"""内容运营情报模块。"""

from modules.content_ops.platforms import list_platforms, platform_map
from modules.content_ops.age_bands import list_age_bands, keywords_for_ages
from modules.content_ops.pipeline import (
    run_full_intelligence, collect_platform_koubo, platform_status, enrich_and_rank,
)
from modules.content_ops.hotspots import fetch_all_hotspots


def __getattr__(name):
    if name == 'PLATFORM_MAP':
        return platform_map()
    raise AttributeError(f'module {__name__!r} has no attribute {name!r}')


__all__ = [
    'list_platforms', 'platform_map', 'PLATFORM_MAP', 'list_age_bands', 'keywords_for_ages',
    'run_full_intelligence', 'collect_platform_koubo', 'platform_status',
    'enrich_and_rank', 'fetch_all_hotspots',
]
