from fastapi import FastAPI
from pydantic import BaseModel
import pandas as pd
from ta.trend import EMAIndicator

app = FastAPI(title="EMA50 Break & Pullback Strategy")


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
    1. Break of EMA50
    2. New High or New Low compared to previous swing
    """

    latest = df.iloc[-1]
    prev_high = df['high'].iloc[-5:-1].max()
    prev_low = df['low'].iloc[-5:-1].min()

    # ---- UPTREND CONDITION ----
    if latest['close'] > latest['ema50'] and latest['high'] > prev_high:
        return "UPTREND"

    # ---- DOWNTREND CONDITION ----
    if latest['close'] < latest['ema50'] and latest['low'] < prev_low:
        return "DOWNTREND"

    return "NO_TREND"


def detect_pullback(df, trend):
    """
    Wait for 2 corrective candles after trend confirmation
    """

    c1 = df.iloc[-2]
    c2 = df.iloc[-1]

    if trend == "UPTREND":
        # Two bearish candles = correction
        if is_bearish(c1) and is_bearish(c2):
            return "BUY"

    if trend == "DOWNTREND":
        # Two bullish candles = correction
        if is_bullish(c1) and is_bullish(c2):
            return "SELL"

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
            "signal": "NO_TRADE"
        }

    # ---- STEP 2: Wait for Pullback ----
    signal = detect_pullback(df, trend)

    if not signal:
        return {
            "symbol": data.symbol,
            "timeframe": data.timeframe,
            "trend": trend,
            "signal": "WAIT_PULLBACK"
        }

    # ---- Risk Management ----
    latest = df.iloc[-1]

    if signal == "BUY":
        stop_loss = df['low'].iloc[-5:-1].min()
        risk = latest['close'] - stop_loss
        take_profit = latest['close'] + (risk * 2)

    elif signal == "SELL":
        stop_loss = df['high'].iloc[-5:-1].max()
        risk = stop_loss - latest['close']
        take_profit = latest['close'] - (risk * 2)

    return {
        "symbol": data.symbol,
        "timeframe": data.timeframe,
        "trend": trend,
        "signal": signal,
        "entry": round(latest['close'], 5),
        "stop_loss": round(stop_loss, 5),
        "take_profit": round(take_profit, 5)
    }


@app.get("/")
def home():
    return {"message": "EMA50 Break & Pullback Strategy Running"}
