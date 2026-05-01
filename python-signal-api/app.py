from fastapi import FastAPI
from pydantic import BaseModel
import pandas as pd
from ta.trend import EMAIndicator

app = FastAPI(title="EMA50 Breakout + Volatility Detection API")


# ==========================================
# REQUEST MODEL
# ==========================================
class MarketData(BaseModel):
    values: list
    symbol: str
    timeframe: str


# ==========================================
# VOLATILITY DETECTION
# ==========================================
def detect_volatility(df):
    """
    Detect if market volatility is HIGH / NORMAL / LOW
    Based on average candle range of last 10 candles
    """

    # Candle range = High - Low
    df["range"] = df["high"] - df["low"]

    recent_avg = df["range"].iloc[-10:].mean()
    total_avg = df["range"].mean()

    if recent_avg > total_avg * 1.5:
        return "HIGH"

    elif recent_avg < total_avg * 0.7:
        return "LOW"

    return "NORMAL"


# ==========================================
# EMA CROSS DETECTION
# ==========================================
def detect_ema_cross(df):
    """
    Detect if price crossed above or below EMA50
    """

    prev = df.iloc[-2]
    current = df.iloc[-1]

    # Price moved from below EMA to above EMA
    if prev["close"] < prev["ema50"] and current["close"] > current["ema50"]:
        return "PRICE_CROSSED_ABOVE_EMA50"

    # Price moved from above EMA to below EMA
    elif prev["close"] > prev["ema50"] and current["close"] < current["ema50"]:
        return "PRICE_CROSSED_BELOW_EMA50"

    # Still above
    elif current["close"] > current["ema50"]:
        return "PRICE_ABOVE_EMA50"

    # Still below
    elif current["close"] < current["ema50"]:
        return "PRICE_BELOW_EMA50"

    return "ON_EMA50"


# ==========================================
# MAIN ANALYSIS ENDPOINT
# ==========================================
@app.post("/analyze")
def analyze(data: MarketData):

    df = pd.DataFrame(data.values)

    required_cols = ["open", "high", "low", "close"]

    if not all(col in df.columns for col in required_cols):
        return {"error": "Missing OHLC data"}

    if len(df) < 60:
        return {"error": "At least 60 candles required"}

    # Reverse latest candle at bottom
    df = df.iloc[::-1].reset_index(drop=True)

    # Convert to float
    for col in required_cols:
        df[col] = df[col].astype(float)

    # ==========================================
    # EMA 50
    # ==========================================
    df["ema50"] = EMAIndicator(close=df["close"], window=50).ema_indicator()

    latest = df.iloc[-1]

    # ==========================================
    # DETECT SIGNAL
    # ==========================================
    ema_signal = detect_ema_cross(df)

    # ==========================================
    # DETECT VOLATILITY
    # ==========================================
    volatility = detect_volatility(df)

    # ==========================================
    # RESPONSE
    # ==========================================
    return {
        "symbol": data.symbol,
        "timeframe": data.timeframe,
        "price": round(latest["close"], 5),
        "ema50": round(latest["ema50"], 5),
        "ema_signal": ema_signal,
        "volatility": volatility,
        "message": (
            "Check market structure before trading"
            if volatility != "LOW"
            else "Low volatility - avoid trading"
        )
    }


# ==========================================
# ROOT
# ==========================================
@app.get("/")
def home():
    return {
        "message": "EMA50 Breakout + Volatility API running successfully"
    }
