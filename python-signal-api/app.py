```python
from fastapi import FastAPI
from pydantic import BaseModel
import pandas as pd
import numpy as np

app = FastAPI(title="SMC PRO MTF Engine v3 | TwelveData Ready")


# =====================================================
# REQUEST MODEL
# =====================================================
class BacktestRequest(BaseModel):
    values_30m: list
    values_1h: list


# =====================================================
# PREPROCESS (TWELVEDATA READY)
# Works with:
# datetime, open, high, low, close, volume(optional)
# =====================================================
def preprocess(data):
    df = pd.DataFrame(data)

    if df.empty:
        return df

    # TwelveData returns newest first -> reverse
    df = df.iloc[::-1].reset_index(drop=True)

    # Support datetime/time
    if "datetime" in df.columns:
        df["time"] = pd.to_datetime(df["datetime"], errors="coerce")

    elif "time" in df.columns:
        df["time"] = pd.to_datetime(df["time"], errors="coerce")

    else:
        raise ValueError("No datetime/time column found")

    # Numeric OHLC
    for col in ["open", "high", "low", "close"]:
        df[col] = pd.to_numeric(df[col], errors="coerce")

    # TwelveData forex may not have volume
    if "volume" not in df.columns:
        df["volume"] = 1000

    df["volume"] = pd.to_numeric(df["volume"], errors="coerce").fillna(1000)

    # Remove bad rows
    df.dropna(inplace=True)
    df.reset_index(drop=True, inplace=True)

    return df


# =====================================================
# SESSION FILTER
# =====================================================
def is_active_session(candle_time):
    hour = candle_time.hour

    london = 7 <= hour <= 16
    newyork = 12 <= hour <= 21

    return london or newyork


# =====================================================
# NEWS FILTER
# =====================================================
def is_news_time(candle_time):
    hour = candle_time.hour

    # avoid high volatility hours
    return hour in [13, 14]


# =====================================================
# ATR
# =====================================================
def calculate_atr(df, period=14):
    high_low = df["high"] - df["low"]
    high_close = abs(df["high"] - df["close"].shift())
    low_close = abs(df["low"] - df["close"].shift())

    tr = pd.concat([high_low, high_close, low_close], axis=1).max(axis=1)
    atr = tr.rolling(period).mean()

    value = atr.iloc[-1]

    if pd.isna(value):
        return (df["high"] - df["low"]).tail(14).mean()

    return value


# =====================================================
# TREND 1H
# =====================================================
def detect_trend(df):
    if len(df) < 12:
        return "RANGE"

    last = df.iloc[-1]

    prev_high = df["high"].iloc[-10:-1].max()
    prev_low = df["low"].iloc[-10:-1].min()

    if last["close"] > prev_high:
        return "BULLISH"

    if last["close"] < prev_low:
        return "BEARISH"

    return "RANGE"


# =====================================================
# LIQUIDITY SWEEP
# =====================================================
def detect_liquidity_sweep(df):
    if len(df) < 25:
        return None

    last = df.iloc[-1]

    prev_high = df["high"].iloc[-20:-2].max()
    prev_low = df["low"].iloc[-20:-2].min()

    if last["high"] > prev_high and last["close"] < prev_high:
        return "SWEEP_HIGH"

    if last["low"] < prev_low and last["close"] > prev_low:
        return "SWEEP_LOW"

    return None


# =====================================================
# STRUCTURE
# =====================================================
def detect_structure(df):
    if len(df) < 25:
        return "RANGE"

    last = df.iloc[-1]
    prev = df.iloc[-2]

    prev_high = df["high"].iloc[-20:-2].max()
    prev_low = df["low"].iloc[-20:-2].min()

    if last["close"] > prev_high:
        return "BOS_UP"

    if last["close"] < prev_low:
        return "BOS_DOWN"

    if prev["close"] < prev_low and last["close"] > prev_low:
        return "CHOCH_UP"

    if prev["close"] > prev_high and last["close"] < prev_high:
        return "CHOCH_DOWN"

    return "RANGE"


# =====================================================
# FAIR VALUE GAP
# =====================================================
def detect_fvg(df):
    if len(df) < 3:
        return None

    c1 = df.iloc[-3]
    c3 = df.iloc[-1]

    if c1["high"] < c3["low"]:
        return "BULLISH_FVG"

    if c1["low"] > c3["high"]:
        return "BEARISH_FVG"

    return None


# =====================================================
# ORDER BLOCK
# =====================================================
def detect_order_block(df):
    if len(df) < 3:
        return None

    prev = df.iloc[-2]
    last = df.iloc[-1]

    if prev["close"] < prev["open"] and last["close"] > prev["high"]:
        return "BULLISH_OB"

    if prev["close"] > prev["open"] and last["close"] < prev["low"]:
        return "BEARISH_OB"

    return None


# =====================================================
# VOLUME CONFIRM
# =====================================================
def volume_confirm(df):
    if len(df) < 12:
        return True

    avg = df["volume"].iloc[-10:-1].mean()
    last = df.iloc[-1]["volume"]

    return last >= avg * 0.8


# =====================================================
# ENTRY ENGINE
# =====================================================
def detect_entry(df_30m, trend):
    last = df_30m.iloc[-1]
    candle_time = last["time"]

    if not is_active_session(candle_time):
        return {"signal": "NO_TRADE", "reason": "NO_SESSION"}

    if is_news_time(candle_time):
        return {"signal": "NO_TRADE", "reason": "NEWS_TIME"}

    sweep = detect_liquidity_sweep(df_30m)
    structure = detect_structure(df_30m)
    fvg = detect_fvg(df_30m)
    ob = detect_order_block(df_30m)
    vol_ok = volume_confirm(df_30m)

    if not vol_ok:
        return {"signal": "NO_TRADE", "reason": "LOW_VOLUME"}

    atr = calculate_atr(df_30m)

    # ========================= BUY =========================
    if (
        trend == "BULLISH"
        and sweep == "SWEEP_LOW"
        and structure in ["CHOCH_UP", "BOS_UP"]
        and fvg == "BULLISH_FVG"
        and ob == "BULLISH_OB"
    ):
        entry = last["close"]
        sl = entry - atr * 1.5
        tp = entry + atr * 3

        return {
            "signal": "BUY",
            "entry": round(entry, 5),
            "stop_loss": round(sl, 5),
            "take_profit": round(tp, 5),
            "trend": trend,
            "structure": structure,
            "atr": round(atr, 5)
        }

    # ========================= SELL =========================
    if (
        trend == "BEARISH"
        and sweep == "SWEEP_HIGH"
        and structure in ["CHOCH_DOWN", "BOS_DOWN"]
        and fvg == "BEARISH_FVG"
        and ob == "BEARISH_OB"
    ):
        entry = last["close"]
        sl = entry + atr * 1.5
        tp = entry - atr * 3

        return {
            "signal": "SELL",
            "entry": round(entry, 5),
            "stop_loss": round(sl, 5),
            "take_profit": round(tp, 5),
            "trend": trend,
            "structure": structure,
            "atr": round(atr, 5)
        }

    return {
        "signal": "NO_TRADE",
        "trend": trend,
        "structure": structure
    }


# =====================================================
# MAIN ANALYZE
# =====================================================
@app.post("/analyze")
def analyze(data: BacktestRequest):
    try:
        df30 = preprocess(data.values_30m)
        df1h = preprocess(data.values_1h)

        if len(df30) < 50 or len(df1h) < 20:
            return {
                "signal": "NO_TRADE",
                "reason": "NOT_ENOUGH_DATA"
            }

        trend = detect_trend(df1h)
        result = detect_entry(df30, trend)

        return result

    except Exception as e:
        return {
            "signal": "NO_TRADE",
            "reason": str(e)
        }


# =====================================================
# ROOT
# =====================================================
@app.get("/")
def home():
    return {
        "message": "SMC PRO MTF Engine v3 Running | TwelveData Compatible"
    }
```
