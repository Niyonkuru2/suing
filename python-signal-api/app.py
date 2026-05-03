from fastapi import FastAPI
from pydantic import BaseModel
import pandas as pd
import numpy as np
from datetime import datetime

app = FastAPI(title="SMC PRO MTF Engine v2")


# =====================================================
# REQUEST MODEL
# =====================================================
class BacktestRequest(BaseModel):
    values_30m: list
    values_1h: list


# =====================================================
# PREPROCESS
# Requires candle format:
# {
#   "time": "2026-05-03 14:30:00",
#   "open":1.10,
#   "high":1.11,
#   "low":1.09,
#   "close":1.105,
#   "volume":1200
# }
# =====================================================
def preprocess(data):
    df = pd.DataFrame(data)
    df = df.iloc[::-1].reset_index(drop=True)

    df["time"] = pd.to_datetime(df["time"])

    for col in ["open", "high", "low", "close", "volume"]:
        df[col] = df[col].astype(float)

    return df


# =====================================================
# SESSION FILTER USING CANDLE TIME
# =====================================================
def is_active_session(candle_time):
    hour = candle_time.hour

    london = 7 <= hour <= 16
    newyork = 12 <= hour <= 21

    return london or newyork


# =====================================================
# NEWS FILTER (AVOID MAJOR NEWS HOURS)
# Example only. Replace with API later.
# =====================================================
def is_news_time(candle_time):
    hour = candle_time.hour

    # Example avoid 13:00 / 14:00 UTC
    if hour in [13, 14]:
        return True

    return False


# =====================================================
# ATR
# =====================================================
def calculate_atr(df, period=14):
    high_low = df["high"] - df["low"]
    high_close = abs(df["high"] - df["close"].shift())
    low_close = abs(df["low"] - df["close"].shift())

    tr = pd.concat([high_low, high_close, low_close], axis=1).max(axis=1)
    atr = tr.rolling(period).mean()

    return atr.iloc[-1]


# =====================================================
# TREND 1H
# =====================================================
def detect_trend(df):
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
    last = df.iloc[-1]

    prev_high = df["high"].iloc[-20:-2].max()
    prev_low = df["low"].iloc[-20:-2].min()

    if last["high"] > prev_high and last["close"] < prev_high:
        return "SWEEP_HIGH"

    if last["low"] < prev_low and last["close"] > prev_low:
        return "SWEEP_LOW"

    return None


# =====================================================
# BOS / CHOCH
# =====================================================
def detect_structure(df):
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
    c2 = df.iloc[-2]
    c3 = df.iloc[-1]

    # Bullish FVG
    if c1["high"] < c3["low"]:
        return "BULLISH_FVG"

    # Bearish FVG
    if c1["low"] > c3["high"]:
        return "BEARISH_FVG"

    return None


# =====================================================
# ORDER BLOCK
# =====================================================
def detect_order_block(df):
    last = df.iloc[-1]

    # Bullish OB = last bearish candle before rally
    prev = df.iloc[-2]

    if prev["close"] < prev["open"] and last["close"] > prev["high"]:
        return "BULLISH_OB", prev["low"], prev["high"]

    # Bearish OB
    if prev["close"] > prev["open"] and last["close"] < prev["low"]:
        return "BEARISH_OB", prev["low"], prev["high"]

    return None, None, None


# =====================================================
# VOLUME CONFIRMATION
# =====================================================
def volume_confirm(df):
    avg = df["volume"].iloc[-10:-1].mean()
    last = df.iloc[-1]["volume"]

    return last > avg * 1.2


# =====================================================
# ENTRY ENGINE
# =====================================================
def detect_entry(df_30m, trend):
    last = df_30m.iloc[-1]
    candle_time = last["time"]

    # Session filter
    if not is_active_session(candle_time):
        return {"signal": "NO_TRADE", "reason": "NO_SESSION"}

    # News filter
    if is_news_time(candle_time):
        return {"signal": "NO_TRADE", "reason": "NEWS_TIME"}

    sweep = detect_liquidity_sweep(df_30m)
    structure = detect_structure(df_30m)
    fvg = detect_fvg(df_30m)
    ob, ob_low, ob_high = detect_order_block(df_30m)
    vol_ok = volume_confirm(df_30m)

    if not vol_ok:
        return {"signal": "NO_TRADE", "reason": "LOW_VOLUME"}

    atr = calculate_atr(df_30m)

    # =================================================
    # BUY
    # =================================================
    if trend == "BULLISH":
        if sweep == "SWEEP_LOW":
            if structure in ["CHOCH_UP", "BOS_UP"]:
                if fvg == "BULLISH_FVG":
                    if ob == "BULLISH_OB":

                        entry = last["close"]
                        sl = entry - atr * 1.5
                        tp = entry + atr * 3

                        return {
                            "signal": "BUY",
                            "entry": round(entry, 5),
                            "stop_loss": round(sl, 5),
                            "take_profit": round(tp, 5),
                            "atr": round(atr, 5)
                        }

    # =================================================
    # SELL
    # =================================================
    if trend == "BEARISH":
        if sweep == "SWEEP_HIGH":
            if structure in ["CHOCH_DOWN", "BOS_DOWN"]:
                if fvg == "BEARISH_FVG":
                    if ob == "BEARISH_OB":

                        entry = last["close"]
                        sl = entry + atr * 1.5
                        tp = entry - atr * 3

                        return {
                            "signal": "SELL",
                            "entry": round(entry, 5),
                            "stop_loss": round(sl, 5),
                            "take_profit": round(tp, 5),
                            "atr": round(atr, 5)
                        }

    return {"signal": "NO_TRADE"}


# =====================================================
# LIVE ANALYSIS
# =====================================================
@app.post("/analyze")
def analyze(data: BacktestRequest):
    df30 = preprocess(data.values_30m)
    df1h = preprocess(data.values_1h)

    if len(df30) < 50 or len(df1h) < 30:
        return {"error": "Not enough data"}

    trend = detect_trend(df1h)
    trade = detect_entry(df30, trend)

    return {
        "trend": trend,
        **trade
    }


# =====================================================
# ROOT
# =====================================================
@app.get("/")
def home():
    return {
        "message": "SMC PRO Engine v2 Running | OB + FVG + ATR + Volume + Session + News"
    }
