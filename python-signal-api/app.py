from fastapi import FastAPI
from pydantic import BaseModel
import pandas as pd
from ta.trend import EMAIndicator

app = FastAPI(title="EMA50 Touch & Trend Detection Strategy")


class MarketData(BaseModel):
    values: list
    symbol: str
    timeframe: str


# =========================
# HELPER FUNCTIONS
# =========================

def is_bullish(candle):
    return candle['close'] > candle['open']


def is_bearish(candle):
    return candle['close'] < candle['open']


def detect_trend(df):
    """
    Confirm trend using:
    1. Price touching or closing near EMA50
    2. New high/low compared to previous 5 swings
    """

    latest = df.iloc[-1]
    prev_high = df['high'].iloc[-6:-1].max()  # last 5 swings
    prev_low = df['low'].iloc[-6:-1].min()

    # Price tolerance for EMA50 touch (e.g., within 0.2% of EMA50)
    tolerance = latest['ema50'] * 0.002

    # ---- UPTREND CONDITION ----
    if latest['close'] > latest['ema50'] - tolerance and latest['high'] > prev_high:
        return "UPTREND"

    # ---- DOWNTREND CONDITION ----
    if latest['close'] < latest['ema50'] + tolerance and latest['low'] < prev_low:
        return "DOWNTREND"

    return "NO_TREND"


# Optional: detect pullbacks but do not generate automatic entry
def detect_pullback(df, trend):
    """
    Detect corrective movement but only signals trend presence.
    Entry decision left to user.
    """
    c1 = df.iloc[-2]
    c2 = df.iloc[-1]

    if trend == "UPTREND":
        if is_bearish(c1) and is_bearish(c2):
            return "TREND_PULLBACK"

    if trend == "DOWNTREND":
        if is_bullish(c1) and is_bullish(c2):
            return "TREND_PULLBACK"

    return None


# =========================
# MAIN ENDPOINT
# =========================

@app.post("/analyze")
def analyze(data: MarketData):

    df = pd.DataFrame(data.values)

    # Validation
    required_cols = ['open', 'high', 'low', 'close']
    if not all(col in df.columns for col in required_cols):
        return {"error": "Missing OHLC data"}

    if len(df) < 60:
        return {"error": "Not enough data"}

    # Reverse order: latest candle last
    df = df.iloc[::-1].reset_index(drop=True)
    for col in required_cols:
        df[col] = df[col].astype(float)

    # EMA50
    df['ema50'] = EMAIndicator(df['close'], window=50).ema_indicator()

    # ---- STEP 1: Detect Confirmed Trend ----
    trend = detect_trend(df)

    if trend == "NO_TREND":
        return {
            "symbol": data.symbol,
            "timeframe": data.timeframe,
            "trend": trend,
            "signal": "NO_TREND"
        }

    # ---- STEP 2: Detect Pullback ----
    pullback_signal = detect_pullback(df, trend)

    return {
        "symbol": data.symbol,
        "timeframe": data.timeframe,
        "trend": trend,
        "signal": pullback_signal if pullback_signal else "TREND_CONFIRMED",
        "latest_close": round(df.iloc[-1]['close'], 5),
        "ema50": round(df.iloc[-1]['ema50'], 5)
    }


@app.get("/")
def home():
    return {"message": "EMA50 Touch & Trend Detection Strategy Running"}
