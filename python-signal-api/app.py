from fastapi import FastAPI
from pydantic import BaseModel
import pandas as pd
from ta.trend import SMAIndicator
from ta.momentum import RSIIndicator

app = FastAPI(title="Market Signal API v2")

# --- Data Models ---
class PricePoint(BaseModel):
    close: float
    datetime: str | None = None

class MarketData(BaseModel):
    values: list[PricePoint]
    symbol: str
    timeframe: str


@app.post("/analyze")
def analyze(data: MarketData):
    # --- Convert incoming data ---
    df = pd.DataFrame([v.dict() for v in data.values])
    if "datetime" in df.columns:
        df = df.sort_values(by="datetime", ascending=True).reset_index(drop=True)
    df["close"] = df["close"].astype(float)

    # --- Data check ---
    if len(df) < 50:
        return {"error": "Not enough data to calculate indicators (need at least 50 points)"}

    # --- Indicators ---
    df["sma20"] = SMAIndicator(df["close"], window=20).sma_indicator()
    df["sma50"] = SMAIndicator(df["close"], window=50).sma_indicator()
    df["rsi"] = RSIIndicator(df["close"], window=14).rsi()

    latest = df.iloc[-1]
    previous = df.iloc[-2]

    # --- SMA crossover logic ---
    signal = "NEUTRAL"
    confidence = 0.0

    if previous["sma20"] <= previous["sma50"] and latest["sma20"] > latest["sma50"]:
        signal = "BUY"
    elif previous["sma20"] >= previous["sma50"] and latest["sma20"] < latest["sma50"]:
        signal = "SELL"

    # --- RSI confirmation ---
    rsi_value = latest["rsi"]
    if signal == "BUY":
        if rsi_value > 55:
            confidence = 0.9
        elif rsi_value > 50:
            confidence = 0.6
        else:
            signal, confidence = "NEUTRAL", 0.0
    elif signal == "SELL":
        if rsi_value < 45:
            confidence = 0.9
        elif rsi_value < 50:
            confidence = 0.6
        else:
            signal, confidence = "NEUTRAL", 0.0

    # --- Risk management levels ---
    close_price = latest["close"]
    if signal == "BUY":
        stop_loss = close_price * 0.99
        take_profit = close_price * 1.02
    elif signal == "SELL":
        stop_loss = close_price * 1.01
        take_profit = close_price * 0.98
    else:
        stop_loss = take_profit = None

    # --- Return structured response ---
    result = {
        "symbol": data.symbol,
        "timeframe": data.timeframe,
        "signal": signal,
        "confidence": confidence,
        "rsi": round(rsi_value, 2),
        "last_close": close_price,
        "stop_loss": stop_loss,
        "take_profit": take_profit,
        "timestamp": str(df["datetime"].iloc[-1]) if "datetime" in df.columns else str(df.index[-1]),
    }

    return result


@app.get("/")
def home():
    return {"message": "Market Signal API v2 is running successfully"}
