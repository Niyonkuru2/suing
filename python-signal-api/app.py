from fastapi import FastAPI
from pydantic import BaseModel
import pandas as pd
from ta.trend import EMAIndicator

app = FastAPI(title="EMA50 MTF Strategy API")


# ==========================================
# REQUEST MODELS
# ==========================================
class MarketData(BaseModel):
    values: list
    symbol: str
    timeframe: str


class BacktestRequest(BaseModel):
    values_30m: list
    values_1h: list


# ==========================================
# HELPERS
# ==========================================
def preprocess(df):
    df = pd.DataFrame(df)
    df = df.iloc[::-1].reset_index(drop=True)

    for col in ["open", "high", "low", "close"]:
        df[col] = df[col].astype(float)

    df["ema50"] = EMAIndicator(close=df["close"], window=50).ema_indicator()
    return df


def is_bullish(c): return c["close"] > c["open"]
def is_bearish(c): return c["close"] < c["open"]


# ==========================================
# VOLATILITY
# ==========================================
def detect_volatility(df):
    df["range"] = df["high"] - df["low"]

    recent = df["range"].iloc[-10:].mean()
    overall = df["range"].mean()

    if recent > overall * 1.5:
        return "HIGH"
    elif recent < overall * 0.7:
        return "LOW"
    return "NORMAL"


# ==========================================
# 1H TREND (HIGH TIMEFRAME)
# ==========================================
def detect_trend(df_1h):
    last = df_1h.iloc[-1]
    prev = df_1h.iloc[-2]

    if prev["close"] < prev["ema50"] and last["close"] > last["ema50"]:
        return "BULLISH"

    if prev["close"] > prev["ema50"] and last["close"] < last["ema50"]:
        return "BEARISH"

    if last["close"] > last["ema50"]:
        return "BULLISH"

    return "BEARISH"


# ==========================================
# ENTRY LOGIC (30M)
# ==========================================
def detect_entry(df_30m, trend):

    last = df_30m.iloc[-1]

    # Pullback candles
    pullback = df_30m.iloc[-4:-2]

    bearish_pullback = all(is_bearish(c) for _, c in pullback.iterrows())
    bullish_pullback = all(is_bullish(c) for _, c in pullback.iterrows())

    # Structure
    swing_high = df_30m["high"].iloc[-6:-2].max()
    swing_low = df_30m["low"].iloc[-6:-2].min()

    # ENTRY CONDITIONS
    if trend == "BULLISH" and bearish_pullback:
        if last["close"] > swing_high:
            entry = last["close"]
            sl = swing_low
            tp = entry + (entry - sl) * 2

            return {
                "signal": "BUY",
                "entry": entry,
                "stop_loss": sl,
                "take_profit": tp,
                "structure": "MTF_PULLBACK_BUY"
            }

    if trend == "BEARISH" and bullish_pullback:
        if last["close"] < swing_low:
            entry = last["close"]
            sl = swing_high
            tp = entry - (sl - entry) * 2

            return {
                "signal": "SELL",
                "entry": entry,
                "stop_loss": sl,
                "take_profit": tp,
                "structure": "MTF_PULLBACK_SELL"
            }

    return {"signal": "NO_TRADE"}


# ==========================================
# MAIN ANALYSIS (MTF)
# ==========================================
@app.post("/analyze-mtf")
def analyze_mtf(data: BacktestRequest):

    df_30m = preprocess(data.values_30m)
    df_1h = preprocess(data.values_1h)

    if len(df_30m) < 60 or len(df_1h) < 60:
        return {"error": "Not enough data"}

    volatility = detect_volatility(df_30m)
    trend = detect_trend(df_1h)

    if volatility == "LOW":
        return {
            "signal": "NO_TRADE",
            "reason": "LOW_VOLATILITY"
        }

    trade = detect_entry(df_30m, trend)

    return {
        "trend": trend,
        "volatility": volatility,
        **trade
    }


# ==========================================
# BACKTEST ENGINE
# ==========================================
@app.post("/backtest")
def backtest(data: BacktestRequest):

    df_30m = preprocess(data.values_30m)
    df_1h = preprocess(data.values_1h)

    wins = 0
    losses = 0
    trades = 0

    for i in range(60, len(df_30m) - 10):

        slice_30m = df_30m.iloc[:i]
        slice_1h = df_1h.iloc[:i // 2]  # approximate alignment

        volatility = detect_volatility(slice_30m)
        trend = detect_trend(slice_1h)

        if volatility == "LOW":
            continue

        trade = detect_entry(slice_30m, trend)

        if trade["signal"] == "NO_TRADE":
            continue

        trades += 1

        entry = trade["entry"]
        sl = trade["stop_loss"]
        tp = trade["take_profit"]

        future = df_30m.iloc[i:i+10]

        hit_tp = False
        hit_sl = False

        for _, candle in future.iterrows():
            if trade["signal"] == "BUY":
                if candle["low"] <= sl:
                    hit_sl = True
                    break
                if candle["high"] >= tp:
                    hit_tp = True
                    break

            if trade["signal"] == "SELL":
                if candle["high"] >= sl:
                    hit_sl = True
                    break
                if candle["low"] <= tp:
                    hit_tp = True
                    break

        if hit_tp:
            wins += 1
        elif hit_sl:
            losses += 1

    winrate = (wins / trades * 100) if trades > 0 else 0

    return {
        "trades": trades,
        "wins": wins,
        "losses": losses,
        "winrate": round(winrate, 2)
    }


# ==========================================
# ROOT
# ==========================================
@app.get("/")
def home():
    return {"message": "MTF EMA Strategy API Running"}
