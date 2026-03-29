from fastapi import FastAPI
from pydantic import BaseModel
import pandas as pd
from ta.trend import EMAIndicator

app = FastAPI(title="Market Structure + EMA50 Strategy API")


class MarketData(BaseModel):
    values: list
    symbol: str
    timeframe: str


def detect_structure(df):
    """
    Detects HH/HL (uptrend) or LH/LL (downtrend)
    """
    highs = df['high']
    lows = df['low']

    # Last 3 swings
    h1, h2, h3 = highs.iloc[-3], highs.iloc[-2], highs.iloc[-1]
    l1, l2, l3 = lows.iloc[-3], lows.iloc[-2], lows.iloc[-1]

    # Higher Highs & Higher Lows
    if h3 > h2 > h1 and l3 > l2 > l1:
        return "UPTREND"

    # Lower Highs & Lower Lows
    if h3 < h2 < h1 and l3 < l2 < l1:
        return "DOWNTREND"

    return "RANGE"


@app.post("/analyze")
def analyze(data: MarketData):

    df = pd.DataFrame(data.values)

    if not all(col in df.columns for col in ['open', 'high', 'low', 'close']):
        return {"error": "Missing OHLC data"}

    if len(df) < 60:
        return {"error": "Not enough data"}

    # Latest candle at bottom
    df = df.iloc[::-1].reset_index(drop=True)

    # Convert to float
    for col in ['open', 'high', 'low', 'close']:
        df[col] = df[col].astype(float)

    # =========================
    # EMA 50
    # =========================
    df['ema50'] = EMAIndicator(close=df['close'], window=50).ema_indicator()

    latest = df.iloc[-1]

    # =========================
    # STRUCTURE DETECTION
    # =========================
    structure = detect_structure(df)

    signal = "NO_TRADE"
    stop_loss = None
    take_profit = None

    # =========================
    # BUY CONDITIONS
    # =========================
    if (
        latest['close'] > latest['ema50']
        and structure == "UPTREND"
    ):
        signal = "BUY_TREND"

        stop_loss = df['low'].iloc[-6:-1].min()
        risk = latest['close'] - stop_loss
        take_profit = latest['close'] + (risk * 2)

    # =========================
    # SELL CONDITIONS
    # =========================
    elif (
        latest['close'] < latest['ema50']
        and structure == "DOWNTREND"
    ):
        signal = "SELL_TREND"

        stop_loss = df['high'].iloc[-6:-1].max()
        risk = stop_loss - latest['close']
        take_profit = latest['close'] - (risk * 2)

    return {
        "symbol": data.symbol,
        "timeframe": data.timeframe,
        "structure": structure,
        "signal": signal,
        "entry": round(latest['close'], 5),
        "ema50": round(latest['ema50'], 5),
        "stop_loss": round(stop_loss, 5) if stop_loss else None,
        "take_profit": round(take_profit, 5) if take_profit else None
    }


@app.get("/")
def home():
    return {"message": "Market Structure + EMA50 API running successfully"}
