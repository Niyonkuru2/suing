from fastapi import FastAPI
from pydantic import BaseModel
import pandas as pd
from ta.trend import EMAIndicator
from ta.volatility import AverageTrueRange

app = FastAPI(title="EMA50 Pullback Pro Strategy API")


class MarketData(BaseModel):
    values: list  # must include open, high, low, close
    symbol: str
    timeframe: str


# ---------------- STRUCTURE DETECTION ----------------
def detect_structure(df):
    highs = []
    lows = []

    for i in range(2, len(df) - 2):
        if df['high'][i] > df['high'][i-1] and df['high'][i] > df['high'][i-2] \
           and df['high'][i] > df['high'][i+1] and df['high'][i] > df['high'][i+2]:
            highs.append(df['high'][i])

        if df['low'][i] < df['low'][i-1] and df['low'][i] < df['low'][i-2] \
           and df['low'][i] < df['low'][i+1] and df['low'][i] < df['low'][i+2]:
            lows.append(df['low'][i])

    if len(highs) < 2 or len(lows) < 2:
        return "NO_STRUCTURE"

    if highs[-1] > highs[-2] and lows[-1] > lows[-2]:
        return "UPTREND"

    elif highs[-1] < highs[-2] and lows[-1] < lows[-2]:
        return "DOWNTREND"

    return "RANGE"


# ---------------- CONFIRMATION ----------------
def bullish_engulfing(prev, curr):
    return (
        curr['close'] > curr['open'] and
        prev['close'] < prev['open'] and
        curr['close'] > prev['open'] and
        curr['open'] < prev['close']
    )


def bearish_engulfing(prev, curr):
    return (
        curr['close'] < curr['open'] and
        prev['close'] > prev['open'] and
        curr['open'] > prev['close'] and
        curr['close'] < prev['open']
    )


# ---------------- SIDEWAYS FILTER ----------------
def is_trending(df):
    ema_slope = df['ema50'].iloc[-1] - df['ema50'].iloc[-6]
    return abs(ema_slope) > df['atr'].iloc[-1] * 0.2


# ---------------- MAIN ENDPOINT ----------------
@app.post("/analyze")
def analyze(data: MarketData):
    df = pd.DataFrame(data.values)

    if not all(col in df.columns for col in ['open', 'high', 'low', 'close']):
        return {"error": "Missing OHLC data"}

    if len(df) < 100:
        return {"error": "Not enough data"}

    df = df.iloc[::-1].reset_index(drop=True)

    for col in ['open', 'high', 'low', 'close']:
        df[col] = df[col].astype(float)

    # Indicators
    df['ema50'] = EMAIndicator(df['close'], window=50).ema_indicator()
    atr_indicator = AverageTrueRange(df['high'], df['low'], df['close'], window=14)
    df['atr'] = atr_indicator.average_true_range()

    structure = detect_structure(df)

    latest = df.iloc[-1]
    prev = df.iloc[-2]

    signal = "NO_TRADE"
    stop_loss = None
    take_profit = None

    # 🔥 Sideways filter
    if not is_trending(df):
        return {
            "symbol": data.symbol,
            "timeframe": data.timeframe,
            "structure": "SIDEWAYS",
            "signal": "NO_TRADE"
        }

    tolerance = df['atr'].iloc[-1] * 0.5

    # ================= BUY =================
    if structure == "UPTREND":

        # price must be above EMA
        if latest['close'] > latest['ema50']:

            # pullback must touch EMA zone
            if abs(prev['close'] - prev['ema50']) <= tolerance:

                # strong bullish confirmation
                if bullish_engulfing(prev, latest):

                    signal = "BUY"
                    stop_loss = df['low'].iloc[-10:-1].min()

                    risk = latest['close'] - stop_loss
                    take_profit = latest['close'] + (risk * 2)

    # ================= SELL =================
    if structure == "DOWNTREND":

        if latest['close'] < latest['ema50']:

            if abs(prev['close'] - prev['ema50']) <= tolerance:

                if bearish_engulfing(prev, latest):

                    signal = "SELL"
                    stop_loss = df['high'].iloc[-10:-1].max()

                    risk = stop_loss - latest['close']
                    take_profit = latest['close'] - (risk * 2)

    return {
        "symbol": data.symbol,
        "timeframe": data.timeframe,
        "structure": structure,
        "signal": signal,
        "entry": round(latest['close'], 5),
        "stop_loss": round(stop_loss, 5) if stop_loss else None,
        "take_profit": round(take_profit, 5) if take_profit else None
    }


@app.get("/")
def home():
    return {"message": "EMA50 Pullback Pro Strategy running"}
