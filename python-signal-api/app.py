from fastapi import FastAPI
from pydantic import BaseModel
import pandas as pd
from ta.trend import EMAIndicator

app = FastAPI(title="EMA50 Breakout + Pullback Strategy API")


class MarketData(BaseModel):
    values: list
    symbol: str
    timeframe: str


# ------------------------------------------------------------------
# Candle helpers
# ------------------------------------------------------------------
def is_red(row):
    """Bearish / down candle."""
    return row['close'] < row['open']


def is_green(row):
    """Bullish / up candle."""
    return row['close'] > row['open']


# ------------------------------------------------------------------
# Core logic: find the swing point that sits right before a
# correction of at least `min_correction` opposite-colored candles.
# ------------------------------------------------------------------
def find_correction_extreme(df, cross_idx, n, direction, min_correction=2):
    """
    direction = "up"   -> we are tracking a BUY setup (price broke above EMA50)
                          we track the running HIGH and look for a run of
                          at least `min_correction` RED candles (the pullback).
    direction = "down" -> we are tracking a SELL setup (price broke below EMA50)
                          we track the running LOW and look for a run of
                          at least `min_correction` GREEN candles (the pullback).

    Returns:
        extreme_price, extreme_idx, correction_end_idx
        (correction_end_idx = first index AFTER the correction run finishes)
    or (None, None, None) if no valid correction of the required length is found.
    """
    if direction == "up":
        running_extreme = df['high'].iloc[cross_idx]
        is_correction_candle = is_red
        better = lambda new, old: new > old
        price_col = 'high'
    else:
        running_extreme = df['low'].iloc[cross_idx]
        is_correction_candle = is_green
        better = lambda new, old: new < old
        price_col = 'low'

    extreme_idx = cross_idx
    i = cross_idx + 1

    while i < n:
        row = df.iloc[i]
        price = row[price_col]

        # Still making new extremes (new high for BUY / new low for SELL) ->
        # this pushes the reference point forward, no correction yet.
        if better(price, running_extreme):
            running_extreme = price
            extreme_idx = i
            i += 1
            continue

        # Not a new extreme - check if a correction (opposite color run) starts here
        if is_correction_candle(row):
            j = i
            count = 0
            while j < n and is_correction_candle(df.iloc[j]):
                count += 1
                j += 1

            if count >= min_correction:
                # Found a valid correction of the required length.
                return running_extreme, extreme_idx, j
            else:
                # Correction too short - keep scanning from where it ended,
                # the extreme reference stays the same.
                i = j if j > i else i + 1
        else:
            i += 1

    return None, None, None


def find_last_cross(df, start, n, direction):
    """
    direction = "up"   -> most recent bar where price was below EMA50
                          on the previous close and above EMA50 on this close.
    direction = "down" -> the mirror image.
    Returns the index of the cross bar, or None.
    """
    last_cross = None
    for i in range(start + 1, n):
        prev_close, prev_ema = df['close'].iloc[i - 1], df['ema50'].iloc[i - 1]
        curr_close, curr_ema = df['close'].iloc[i], df['ema50'].iloc[i]

        if direction == "up" and prev_close < prev_ema and curr_close > curr_ema:
            last_cross = i
        elif direction == "down" and prev_close > prev_ema and curr_close < curr_ema:
            last_cross = i

    return last_cross


def detect_breakout_setup(df, lookback=30, min_correction=2):
    """
    BUY setup:
      1. Price is below EMA50, then closes above EMA50 (the breakout).
      2. Price keeps making new highs, then pulls back with AT LEAST
         `min_correction` consecutive RED candles.
      3. The level to beat is the high made right before that red run.
      4. Signal fires the moment a candle CLOSES back above that high.

    SELL setup is the exact mirror (EMA50 breakdown, then a run of GREEN
    candles pulling back up, level = the low made before that run, signal
    fires when a candle closes back below that low).

    Only returns a signal if the *latest* candle is the one satisfying the
    entry condition (i.e. the signal is live right now).
    """
    n = len(df)
    start = max(0, n - lookback)
    if n - start < min_correction + 3:
        return None, None, None

    latest_idx = n - 1

    # ---------------- BUY ----------------
    cross_up_idx = find_last_cross(df, start, n, "up")
    if cross_up_idx is not None:
        key_high, key_idx, correction_end_idx = find_correction_extreme(
            df, cross_up_idx, n, "up", min_correction
        )
        if key_high is not None and latest_idx >= correction_end_idx:
            if df['close'].iloc[latest_idx] > key_high:
                return "BUY_TREND", key_high, key_idx

    # ---------------- SELL ----------------
    cross_down_idx = find_last_cross(df, start, n, "down")
    if cross_down_idx is not None:
        key_low, key_idx, correction_end_idx = find_correction_extreme(
            df, cross_down_idx, n, "down", min_correction
        )
        if key_low is not None and latest_idx >= correction_end_idx:
            if df['close'].iloc[latest_idx] < key_low:
                return "SELL_TREND", key_low, key_idx

    return None, None, None


@app.post("/analyze")
def analyze(data: MarketData):
    df = pd.DataFrame(data.values)

    if not all(col in df.columns for col in ['open', 'high', 'low', 'close']):
        return {"error": "Missing OHLC data"}

    if len(df) < 60:
        return {"error": "Not enough data"}

    # Incoming data is assumed newest-first -> flip so latest candle is last
    df = df.iloc[::-1].reset_index(drop=True)

    for col in ['open', 'high', 'low', 'close']:
        df[col] = df[col].astype(float)

    # ---------------- EMA 50 ----------------
    df['ema50'] = EMAIndicator(close=df['close'], window=50).ema_indicator()
    df = df.dropna(subset=['ema50']).reset_index(drop=True)

    if len(df) < 30:
        return {"error": "Not enough data after EMA warm-up"}

    latest = df.iloc[-1]

    # ---------------- DETECT SETUP ----------------
    signal, key_level, key_idx = detect_breakout_setup(df)

    if signal == "BUY_TREND":
        # Stop loss: lowest low made during the pullback (between the
        # marked high and the entry candle).
        pullback_slice = df.iloc[key_idx + 1:]
        stop_loss = pullback_slice['low'].min() if len(pullback_slice) > 0 else latest['close'] * 0.99

        risk = latest['close'] - stop_loss
        take_profit = latest['close'] + (risk * 2)

        return {
            "symbol": data.symbol,
            "timeframe": data.timeframe,
            "setup_type": "BREAKOUT_PULLBACK_BUY",
            "signal": signal,
            "entry": round(latest['close'], 5),
            "key_level": round(key_level, 5),
            "ema50": round(latest['ema50'], 5),
            "stop_loss": round(stop_loss, 5),
            "take_profit": round(take_profit, 5),
            "risk_reward": "1:2"
        }

    elif signal == "SELL_TREND":
        pullback_slice = df.iloc[key_idx + 1:]
        stop_loss = pullback_slice['high'].max() if len(pullback_slice) > 0 else latest['close'] * 1.01

        risk = stop_loss - latest['close']
        take_profit = latest['close'] - (risk * 2)

        return {
            "symbol": data.symbol,
            "timeframe": data.timeframe,
            "setup_type": "BREAKOUT_PULLBACK_SELL",
            "signal": signal,
            "entry": round(latest['close'], 5),
            "key_level": round(key_level, 5),
            "ema50": round(latest['ema50'], 5),
            "stop_loss": round(stop_loss, 5),
            "take_profit": round(take_profit, 5),
            "risk_reward": "1:2"
        }

    else:
        return {
            "symbol": data.symbol,
            "timeframe": data.timeframe,
            "setup_type": "NO_SETUP",
            "signal": "NO_TRADE",
            "info": "No valid EMA50 breakout + 2-candle-pullback setup detected yet.",
            "entry": round(latest['close'], 5),
            "ema50": round(latest['ema50'], 5),
            "stop_loss": None,
            "take_profit": None
        }


@app.get("/")
def home():
    return {"message": "EMA50 Breakout + Pullback Strategy API running successfully"}
