from fastapi import FastAPI
from pydantic import BaseModel
import pandas as pd
from ta.trend import SMAIndicator

app = FastAPI(title="Market Signal API")

class PricePoint(BaseModel):
    close: float

class MarketData(BaseModel):
    values: list[PricePoint]
    symbol: str
    timeframe: str

@app.post("/analyze")
def analyze(data: MarketData):
    df = pd.DataFrame([v.dict() for v in data.values])
    if len(df) < 50:
        return {"error": "Not enough data to calculate SMA50"}

    df = df.iloc[::-1].reset_index(drop=True)
    df['sma20'] = SMAIndicator(df['close'], window=20).sma_indicator()
    df['sma50'] = SMAIndicator(df['close'], window=50).sma_indicator()

    latest = df.iloc[-1]
    previous = df.iloc[-2]

    if previous['sma20'] <= previous['sma50'] and latest['sma20'] > latest['sma50']:
        signal = "BUY"
    elif previous['sma20'] >= previous['sma50'] and latest['sma20'] < latest['sma50']:
        signal = "SELL"
    else:
        signal = "NEUTRAL"

    return {
        "symbol": data.symbol,
        "timeframe": data.timeframe,
        "signal": signal,
        "last_close": latest['close'],
        "timestamp": df.index[-1]
    }

@app.get("/")
def home():
    return {"message": "Market Signal API"}
