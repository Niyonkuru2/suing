from fastapi import FastAPI
from pydantic import BaseModel
import pandas as pd
from ta.trend import EMAIndicator

app = FastAPI(title="EMA50 Trend Strategy API")


class MarketData(BaseModel):
    values: list  # must include open, high, low, close
    symbol: str
    timeframe: str


@app.post("/analyze")
def analyze(data: MarketData):

    df = pd.DataFrame(data.values)

    if not all(col in df.columns for col in ['open', 'high', 'low', 'close']):
        return {"error": "Missing OHLC data"}

    if len(df) < 60:
        return {"error": "Not enough data"}

    # Reverse candles (latest at bottom)
    df = df.iloc[::-1].reset_index(drop=True)

    # Convert OHLC to float
    for col in ['open', 'high', 'low', 'close']:
        df[col] = df[col].astype(float)

    # EMA 50
    df['ema50'] = EMAIndicator(close=df['close'], window=50).ema_indicator()

    latest = df.iloc[-1]

    signal = "NO_TRADE"
    structure = "RANGE"
    stop_loss = None
    take_profit = None

    # =========================
    # BUY → price above EMA50
    # =========================
    if latest['close'] > latest['ema50']:

        structure = "UPTREND"
        signal = "BUY"

        stop_loss = df['low'].iloc[-5:-1].min()
        risk = latest['close'] - stop_loss
        take_profit = latest['close'] + (risk * 2)

    # =========================
    # SELL → price below EMA50
    # =========================
    elif latest['close'] < latest['ema50']:

        structure = "DOWNTREND"
        signal = "SELL"

        stop_loss = df['high'].iloc[-5:-1].max()
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
    return {"message": "EMA50 Trend Strategy API running successfully"}
