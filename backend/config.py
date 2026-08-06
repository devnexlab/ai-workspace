"""
统一配置中心。

- 基础设施配置从环境变量 / .env 读取
- 业务配置（AI、TTS、采集 Cookie 等）仍存数据库，由设置页维护
"""

import os
import time
from pathlib import Path

import psycopg2
from psycopg2.extras import RealDictCursor

# ---- 路径 ----
BASE_DIR = Path(__file__).resolve().parent
ENV_FILE = BASE_DIR / '.env'


def _load_dotenv(path: Path = ENV_FILE):
    """轻量加载 .env，不依赖 python-dotenv。"""
    if not path.is_file():
        return
    with open(path, encoding='utf-8') as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith('#') or '=' not in line:
                continue
            key, _, value = line.partition('=')
            key = key.strip()
            value = value.strip().strip('"').strip("'")
            # 已有环境变量优先，不覆盖
            if key and key not in os.environ:
                os.environ[key] = value


_load_dotenv()


def _env(key: str, default: str = '') -> str:
    return os.environ.get(key, default)


def _env_bool(key: str, default: bool = False) -> bool:
    val = os.environ.get(key)
    if val is None:
        return default
    return val.strip().lower() in ('1', 'true', 'yes', 'on')


def _env_int(key: str, default: int) -> int:
    try:
        return int(os.environ.get(key, default))
    except (TypeError, ValueError):
        return default


# ---- PostgreSQL ----
PG_HOST = _env('PG_HOST', '192.168.251.8')
PG_PORT = _env_int('PG_PORT', 5432)
PG_DBNAME = _env('PG_DBNAME', 'ai_ops')
PG_USER = _env('PG_USER', 'postgres')
PG_PASSWORD = _env('PG_PASSWORD', 'postgres')
# 连接池：关闭后归还，而不是每次 TCP 新建
PG_POOL_MIN = _env_int('PG_POOL_MIN', 2)
PG_POOL_MAX = _env_int('PG_POOL_MAX', 20)

# ---- Flask 服务 ----
FLASK_HOST = _env('FLASK_HOST', '0.0.0.0')
FLASK_PORT = _env_int('FLASK_PORT', 3456)
FLASK_DEBUG = _env_bool('FLASK_DEBUG', True)
FLASK_THREADED = _env_bool('FLASK_THREADED', True)

# ---- 本地目录 ----
OUTPUT_DIR = Path(_env('OUTPUT_DIR', str(BASE_DIR / 'outputs')))
UPLOAD_DIR = Path(_env('UPLOAD_DIR', str(BASE_DIR / 'uploads')))
MATERIALS_DIR = UPLOAD_DIR / 'materials'
KNOWLEDGE_DIR = UPLOAD_DIR / 'knowledge'

# 确保目录存在
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
MATERIALS_DIR.mkdir(parents=True, exist_ok=True)
KNOWLEDGE_DIR.mkdir(parents=True, exist_ok=True)


# ---- PostgreSQL 连接包装（兼容原 sqlite3 风格接口）----

from psycopg2 import pool as _pg_pool_mod

_pg_pool = None


def _get_pg_pool():
    """懒加载线程安全连接池（psycopg2.pool.ThreadedConnectionPool）。"""
    global _pg_pool
    if _pg_pool is None:
        _pg_pool = _pg_pool_mod.ThreadedConnectionPool(
            minconn=max(1, PG_POOL_MIN),
            maxconn=max(PG_POOL_MIN, PG_POOL_MAX),
            host=PG_HOST,
            port=PG_PORT,
            dbname=PG_DBNAME,
            user=PG_USER,
            password=PG_PASSWORD,
            connect_timeout=10,
        )
        print(
            f'[DB] PostgreSQL pool ready '
            f'{PG_HOST}:{PG_PORT}/{PG_DBNAME} '
            f'(min={PG_POOL_MIN}, max={PG_POOL_MAX})'
        )
    return _pg_pool


class PgCursor:
    """Wraps psycopg2 cursor to mimic sqlite3 cursor (auto ? -> %s, lastrowid)."""

    def __init__(self, cur):
        self._cur = cur
        self._lastrowid = None

    def execute(self, sql, params=None):
        if params:
            sql = sql.replace('?', '%s')

        stripped = sql.strip()
        if stripped.upper().startswith('INSERT') and 'RETURNING' not in sql.upper():
            sql = sql.rstrip().rstrip(';') + ' RETURNING id'
            self._cur.execute(sql, params or ())
            try:
                row = self._cur.fetchone()
                self._lastrowid = row['id'] if row else None
            except Exception:
                self._lastrowid = None
        else:
            self._cur.execute(sql, params or ())

        return self

    @property
    def lastrowid(self):
        return self._lastrowid

    @property
    def rowcount(self):
        return self._cur.rowcount

    def fetchone(self):
        return self._cur.fetchone()

    def fetchall(self):
        return self._cur.fetchall()

    def close(self):
        self._cur.close()

    def __iter__(self):
        return iter(self._cur)


class PgConnection:
    """从连接池取连接；close() 归还池，不真正断开 TCP。"""

    def __init__(self):
        self._conn = _get_pg_pool().getconn()
        # 归还前可能残留事务，取用时复位
        try:
            self._conn.rollback()
        except Exception:
            pass
        self._conn.autocommit = False
        self._last_cur = None
        self._closed = False

    def execute(self, sql, params=None):
        cur = PgCursor(self._conn.cursor(cursor_factory=RealDictCursor))
        cur.execute(sql, params)
        self._last_cur = cur
        return cur

    def executescript(self, sql):
        cur = self._conn.cursor()
        cur.execute(sql)
        self._last_cur = cur
        return cur

    def commit(self):
        self._conn.commit()

    def rollback(self):
        self._conn.rollback()

    def close(self):
        """归还连接到池（不是关闭 TCP）。"""
        if self._closed:
            return
        self._closed = True
        conn = self._conn
        self._conn = None
        try:
            if conn is None:
                return
            # 未 commit 的事务先回滚，避免脏连接回到池里
            if getattr(conn, 'closed', 1) == 0:
                try:
                    conn.rollback()
                except Exception:
                    pass
                _get_pg_pool().putconn(conn)
            else:
                _get_pg_pool().putconn(conn, close=True)
        except Exception:
            try:
                if conn is not None:
                    _get_pg_pool().putconn(conn, close=True)
            except Exception:
                pass

    @property
    def total_changes(self):
        return self._last_cur.rowcount if self._last_cur else 0


def get_db():
    """从连接池获取 PostgreSQL 连接（接口同 sqlite3）。"""
    return PgConnection()


_get_db = get_db


# ---- 业务设置（数据库）----

_settings_cache = None
_settings_cache_ts = 0.0
_SETTINGS_CACHE_TTL = 2.0  # 秒；短 TTL，避免写入后长期脏读


def _invalidate_settings_cache():
    global _settings_cache, _settings_cache_ts
    _settings_cache = None
    _settings_cache_ts = 0.0


def prime_settings_cache(settings_map: dict):
    """用已加载的 settings 填入缓存，避免同一次请求里重复查库。"""
    global _settings_cache, _settings_cache_ts
    _settings_cache = settings_map
    _settings_cache_ts = time.time()


def get_all_settings():
    """Return all settings as a dict grouped by category（带短时缓存，避免每次 get_setting 新建 PG 连接）。"""
    global _settings_cache, _settings_cache_ts
    now = time.time()
    if _settings_cache is not None and (now - _settings_cache_ts) < _SETTINGS_CACHE_TTL:
        return _settings_cache

    conn = get_db()
    rows = conn.execute('SELECT category, key, value FROM system_setting').fetchall()
    conn.close()
    result = {}
    for row in rows:
        cat = row['category']
        if cat not in result:
            result[cat] = {}
        result[cat][row['key']] = row['value']
    _settings_cache = result
    _settings_cache_ts = now
    return result


def get_settings_by_category(category):
    """Return all settings in a category as a flat dict."""
    return dict(get_all_settings().get(category) or {})


def get_setting(category, key, default=''):
    """Return a single setting value."""
    return get_all_settings().get(category, {}).get(key, default)


def update_setting(category, key, value):
    """Upsert a single setting."""
    conn = get_db()
    conn.execute(
        '''INSERT INTO system_setting (category, key, value, description, field_type, options)
           VALUES (%s, %s, %s, '', 'text', NULL)
           ON CONFLICT (category, key) DO UPDATE SET value = EXCLUDED.value''',
        (category, key, value)
    )
    conn.commit()
    conn.close()
    _invalidate_settings_cache()


def update_settings_batch(settings_dict):
    """Update multiple settings. Input: { category: { key: value } }."""
    conn = get_db()
    for category, items in settings_dict.items():
        for key, value in items.items():
            conn.execute(
                '''INSERT INTO system_setting (category, key, value, description, field_type, options)
                   VALUES (%s, %s, %s, '', 'text', NULL)
                   ON CONFLICT (category, key) DO UPDATE SET value = EXCLUDED.value''',
                (category, key, str(value))
            )
    conn.commit()
    conn.close()
    _invalidate_settings_cache()


def get_ai_config():
    from modules.ai_providers import resolve_ai_config
    return resolve_ai_config()


def get_collector_config(platform):
    return get_settings_by_category(f'collector_{platform}')


def get_tts_config():
    return get_settings_by_category('tts')


def get_video_config():
    return get_settings_by_category('video')


def get_publish_config(platform):
    return get_settings_by_category(f'publish_{platform}')


def is_configured(category):
    settings = get_settings_by_category(category)
    return any(v for v in settings.values() if v)
