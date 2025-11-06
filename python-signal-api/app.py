from fastapi import FastAPI
from pydantic import BaseModel
import pandas as pd
from ta.trend import SMAIndicator

app = FastAPI(title="Market Signal API")

# --- Data Models ---
class PricePoint(BaseModel):
    close: float
    datetime: str | None = None  # optional for sorting if provided

class MarketData(BaseModel):
    values: list[PricePoint]
    symbol: str
    timeframe: str


# --- Analysis Route ---
@app.post("/analyze")
def analyze(data: MarketData):
    # Convert incoming list of PricePoint objects into DataFrame
    df = pd.DataFrame([v.dict() for v in data.values])

    # Sort data by datetime if timestamps exist (Twelve Data returns newest first)
    if "datetime" in df.columns:
        df = df.sort_values(by="datetime", ascending=True).reset_index(drop=True)

    # Ensure close prices are floats
    df["close"] = df["close"].astype(float)

    # Require at least 30 data points for SMA windows
    if len(df) < 30:
        return {"error": "Not enough data to calculate moving averages"}

    # Calculate short-term and long-term SMAs
    df["sma20"] = SMAIndicator(df["close"], window=10).sma_indicator()
    df["sma50"] = SMAIndicator(df["close"], window=30).sma_indicator()

    latest = df.iloc[-1]
    previous = df.iloc[-2]

    # --- Crossover logic ---
    if previous["sma20"] <= previous["sma50"] and latest["sma20"] > latest["sma50"]:
        signal = "BUY"   # bullish crossover
        confidence = 0.9
    elif previous["sma20"] >= previous["sma50"] and latest["sma20"] < latest["sma50"]:
        signal = "SELL"  # bearish crossover
        confidence = 0.9
    else:
        signal = "NEUTRAL"
        confidence = 0.0

    # --- Risk management levels ---
    close_price = latest["close"]
    stop_loss = close_price * (0.99 if signal == "BUY" else 1.01) if signal != "NEUTRAL" else None
    take_profit = close_price * (1.02 if signal == "BUY" else 0.98) if signal != "NEUTRAL" else None

    # --- Final structured result ---
    result = {
        "symbol": data.symbol,
        "timeframe": data.timeframe,
        "signal": signal,
        "confidence": confidence,
        "last_close": close_price,
        "stop_loss": stop_loss,
        "take_profit": take_profit,
        "timestamp": str(df["datetime"].iloc[-1]) if "datetime" in df.columns else str(df.index[-1]),
    }

    return result


# --- Root route ---
@app.get("/")
def home():
    return {"message": "Market Signal API is running successfully"}
