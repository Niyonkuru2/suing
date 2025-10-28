from fastapi import FastAPI
from pydantic import BaseModel
import pandas as pd
from ta.trend import SMAIndicator

app = FastAPI(title="Market Signal API")

class MarketData(BaseModel):
    values: list
    symbol: str
    timeframe: str

@app.post("/analyze")
def analyze(data: MarketData):
    raw_data = data.values
    df = pd.DataFrame(raw_data)
    df['close'] = df['close'].astype(float)
    df = df.iloc[::-1].reset_index(drop=True)  # chronological order

    df['sma20'] = SMAIndicator(df['close'], window=20).sma_indicator()
    df['sma50'] = SMAIndicator(df['close'], window=50).sma_indicator()

    latest = df.iloc[-1]
    previous = df.iloc[-2]

    if previous['sma20'] <= previous['sma50'] and latest['sma20'] > latest['sma50']:
        signal = "SELL"
    elif previous['sma20'] >= previous['sma50'] and latest['sma20'] < latest['sma50']:
        signal = "BUY"
    else:
        signal = "NEUTRAL"

    result = {
        "symbol": data.symbol,
        "timeframe": data.timeframe,
        "signal": signal,
        "last_close": latest['close'],
        "timestamp": str(df.index[-1])
    }

    return result
