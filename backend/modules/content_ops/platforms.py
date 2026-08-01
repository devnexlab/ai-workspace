"""
内容运营 - 可插拔采集平台注册表。

新增平台：在 PLATFORMS 登记 + 实现 collector，即可被 UI/流水线自动发现。
"""

# 平台注册表：key 与 collector / settings 的 collector_{key} 对齐
PLATFORMS = [
    {
        'key': 'shipinhao',
        'label': '视频号',
        'color': 'green',
        'priority': 1,
        'setting_category': 'collector_shipinhao',
        'desc': '主阵地，微信生态口播与熟人转发',
        'enabled_default': True,
    },
    {
        'key': 'douyin',
        'label': '抖音',
        'color': 'black',
        'priority': 2,
        'setting_category': 'collector_douyin',
        'desc': '泛流量最大，适合全年龄口播素材',
        'enabled_default': True,
    },
    {
        'key': 'xiaohongshu',
        'label': '小红书',
        'color': 'red',
        'priority': 3,
        'setting_category': 'collector_xiaohongshu',
        'desc': '种草与女性/家庭向口播（可随时开关）',
        'enabled_default': True,
    },
    # 预留：以后加平台只在此追加，例如
    # {'key': 'bilibili', 'label': 'B站', ...},
    # {'key': 'kuaishou', 'label': '快手', ...},
]

PLATFORM_MAP = {p['key']: p for p in PLATFORMS}


def list_platforms():
    return list(PLATFORMS)


def platform_keys():
    return [p['key'] for p in PLATFORMS]
