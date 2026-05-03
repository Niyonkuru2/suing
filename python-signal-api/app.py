from fastapi import FastAPI
from pydantic import BaseModel
import pandas as pd
from datetime import datetime

app = FastAPI(title="SMC Day Trading MTF Engine")


# ==========================================
# MODELS
# ==========================================
class BacktestRequest(BaseModel):
    values_30m: list
    values_1h: list


# ==========================================
# PREPROCESS
# ==========================================
def preprocess(df):
    df = pd.DataFrame(df)
    df = df.iloc[::-1].reset_index(drop=True)

    for col in ["open", "high", "low", "close"]:
        df[col] = df[col].astype(float)

    return df


# ==========================================
# SESSION FILTER (LONDON / NEW YORK)
# ==========================================
def is_active_session():
    hour = datetime.utcnow().hour

    # London session (7–16 UTC)
    london = 7 <= hour <= 16

    # New York session (12–21 UTC)
    ny = 12 <= hour <= 21

    return london or ny


# ==========================================
# LIQUIDITY SWEEP DETECTION
# ==========================================
def detect_liquidity_sweep(df):
    last = df.iloc[-1]

    prev_high = df["high"].iloc[-20:-2].max()
    prev_low = df["low"].iloc[-20:-2].min()

    # Buy-side liquidity sweep
    if last["high"] > prev_high and last["close"] < prev_high:
        return "SWEEP_HIGH"

    # Sell-side liquidity sweep
    if last["low"] < prev_low and last["close"] > prev_low:
        return "SWEEP_LOW"

    return None


# ==========================================
# STRUCTURE (BOS / CHOCH)
# ==========================================
def detect_structure(df):
    last = df.iloc[-1]
    prev = df.iloc[-2]

    prev_high = df["high"].iloc[-20:-2].max()
    prev_low = df["low"].iloc[-20:-2].min()

    # BOS UP
    if last["close"] > prev_high:
        return "BOS_UP"

    # BOS DOWN
    if last["close"] < prev_low:
        return "BOS_DOWN"

    # CHOCH UP (reversal)
    if prev["close"] < prev_low and last["close"] > prev_low:
        return "CHOCH_UP"

    # CHOCH DOWN
    if prev["close"] > prev_high and last["close"] < prev_high:
        return "CHOCH_DOWN"

    return "RANGE"


# ==========================================
# TREND (1H CONFIRMATION)
# ==========================================
def detect_trend(df_1h):
    last = df_1h.iloc[-1]

    prev_high = df_1h["high"].iloc[-10:].max()
    prev_low = df_1h["low"].iloc[-10:].min()

    if last["close"] > prev_high:
        return "BULLISH"

    if last["close"] < prev_low:
        return "BEARISH"

    return "RANGE"


# ==========================================
# ENTRY LOGIC (30M)
# ==========================================
def detect_entry(df_30m, trend):

    last = df_30m.iloc[-1]

    sweep = detect_liquidity_sweep(df_30m)
    structure = detect_structure(df_30m)

    prev_high = df_30m["high"].iloc[-20:-2].max()
    prev_low = df_30m["low"].iloc[-20:-2].min()

    # ================= BUY SETUP =================
    if trend == "BULLISH" and sweep == "SWEEP_LOW":

        if structure in ["CHOCH_UP", "BOS_UP"]:

            entry = last["close"]
            sl = prev_low
            tp = entry + (entry - sl) * 2

            return {
                "signal": "BUY",
                "entry": entry,
                "stop_loss": sl,
                "take_profit": tp,
                "structure": structure
            }

    # ================= SELL SETUP =================
    if trend == "BEARISH" and sweep == "SWEEP_HIGH":

        if structure in ["CHOCH_DOWN", "BOS_DOWN"]:

            entry = last["close"]
            sl = prev_high
            tp = entry - (sl - entry) * 2

            return {
                "signal": "SELL",
                "entry": entry,
                "stop_loss": sl,
                "take_profit": tp,
                "structure": structure
            }

    return {"signal": "NO_TRADE"}


# ==========================================
# MAIN ANALYSIS (MTF DAY TRADING)
# ==========================================
@app.post("/analyze-mtf")
def analyze_mtf(data: BacktestRequest):

    if not is_active_session():
        return {
            "signal": "NO_TRADE",
            "reason": "NO_SESSION"
        }

    df_30m = preprocess(data.values_30m)
    df_1h = preprocess(data.values_1h)

    if len(df_30m) < 60 or len(df_1h) < 60:
        return {"error": "Not enough data"}

    trend = detect_trend(df_1h)
    trade = detect_entry(df_30m, trend)

    return {
        "trend": trend,
        "session": "ACTIVE",
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
        slice_1h = df_1h.iloc[:max(30, i // 2)]

        trend = detect_trend(slice_1h)

        if not is_active_session():
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
    return {
        "message": "SMC Day Trading MTF Engine Running (London/NY + BOS + CHoCH + Liquidity)"
    }
