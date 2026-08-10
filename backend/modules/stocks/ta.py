"""技术指标计算（纯 pandas，不依赖 talib）。"""

from __future__ import annotations

import pandas as pd


def _ema(series: pd.Series, span: int) -> pd.Series:
    return series.ewm(span=span, adjust=False).mean()


def add_indicators(df: pd.DataFrame) -> pd.DataFrame:
    """在日 K DataFrame 上追加 MA/MACD/RSI/KDJ/BOLL/量能均线。"""
    if df is None or df.empty or 'close' not in df.columns:
        return df
    out = df.copy()
    c = out['close']
    h = out['high'] if 'high' in out.columns else c
    l = out['low'] if 'low' in out.columns else c
    v = out['volume'] if 'volume' in out.columns else pd.Series(0, index=out.index)

    for n in (5, 10, 20, 30, 60, 250):
        out[f'MA{n}'] = c.rolling(n).mean()

    # MACD 12/26/9
    dif = _ema(c, 12) - _ema(c, 26)
    dea = _ema(dif, 9)
    out['DIF'] = dif
    out['DEA'] = dea
    out['MACD'] = (dif - dea) * 2

    # RSI
    delta = c.diff()
    gain = delta.clip(lower=0)
    loss = (-delta).clip(lower=0)
    for n in (6, 12, 24):
        avg_gain = gain.rolling(n).mean()
        avg_loss = loss.rolling(n).mean()
        rs = avg_gain / avg_loss.replace(0, pd.NA)
        out[f'RSI{n}'] = 100 - (100 / (1 + rs))

    # KDJ 9
    low_n = l.rolling(9).min()
    high_n = h.rolling(9).max()
    rsv = (c - low_n) / (high_n - low_n).replace(0, pd.NA) * 100
    out['K'] = rsv.ewm(com=2, adjust=False).mean()
    out['D'] = out['K'].ewm(com=2, adjust=False).mean()
    out['J'] = 3 * out['K'] - 2 * out['D']

    # BOLL 20
    mid = c.rolling(20).mean()
    std = c.rolling(20).std()
    out['BOLL_MID'] = mid
    out['BOLL_UP'] = mid + 2 * std
    out['BOLL_LOW'] = mid - 2 * std

    out['VOL_MA5'] = v.rolling(5).mean()
    out['VOL_MA10'] = v.rolling(10).mean()
    return out


def latest_snapshot(df: pd.DataFrame) -> dict:
    """取最新一行关键指标，供 API 展示。"""
    if df is None or df.empty:
        return {}
    row = df.iloc[-1]
    prev = df.iloc[-2] if len(df) > 1 else row

    def f(key, default=0):
        val = row.get(key, default)
        try:
            if pd.isna(val):
                return default
            return round(float(val), 4)
        except Exception:
            return default

    macd_signal = '金叉' if f('DIF') > f('DEA') and float(prev.get('DIF') or 0) <= float(prev.get('DEA') or 0) else (
        '死叉' if f('DIF') < f('DEA') and float(prev.get('DIF') or 0) >= float(prev.get('DEA') or 0) else (
            '多头' if f('DIF') > f('DEA') else '空头'
        )
    )
    ma_signal = '多头' if f('MA5') > f('MA10') > f('MA20') else (
        '空头' if f('MA5') < f('MA10') < f('MA20') else '纠结'
    )
    vol_signal = '放量' if f('volume') > f('VOL_MA5') * 1.5 else '正常'

    return {
        'MACD': {'DIF': f('DIF'), 'DEA': f('DEA'), 'MACD': f('MACD'), 'signal': macd_signal},
        'KDJ': {'K': f('K'), 'D': f('D'), 'J': f('J'),
                'signal': '金叉' if f('K') > f('D') else '死叉'},
        'RSI': {'RSI6': f('RSI6'), 'RSI12': f('RSI12'), 'RSI24': f('RSI24'),
                'signal': '超卖' if f('RSI6') < 30 else ('超买' if f('RSI6') > 70 else '中性')},
        'MA': {
            'MA5': f('MA5'), 'MA10': f('MA10'), 'MA20': f('MA20'),
            'MA30': f('MA30'), 'MA60': f('MA60'), 'MA250': f('MA250'),
            'signal': ma_signal,
        },
        'BOLL': {'UP': f('BOLL_UP'), 'MID': f('BOLL_MID'), 'LOW': f('BOLL_LOW'),
                 'signal': '下轨' if f('close') <= f('BOLL_LOW') else ('上轨' if f('close') >= f('BOLL_UP') else '中轨')},
        'VOLUME': {'volume': f('volume'), 'vol_ma5': f('VOL_MA5'), 'signal': vol_signal},
        'TREND': {'close': f('close'), 'signal': ma_signal},
        'close': f('close'),
        'pct_hint': round((f('close') - float(prev.get('close') or f('close'))) / max(float(prev.get('close') or 1), 1e-6) * 100, 2),
    }
