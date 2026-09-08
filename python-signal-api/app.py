from fastapi import FastAPI
from pydantic import BaseModel
import pandas as pd
from ta.trend import EMAIndicator

app = FastAPI(title="EMA50 Breakout + Pullback Strategy API")


class MarketData(BaseModel):
    values: list          # list of dicts with open/high/low/close (newest first)
    symbol: str
    timeframe: str


# ------------------------------------------------------------------
# Candle helpers
# ------------------------------------------------------------------
def is_red(row):
    return row['close'] < row['open']


def is_green(row):
    return row['close'] > row['open']


# ------------------------------------------------------------------
# Core state machine
# ------------------------------------------------------------------
def run_strategy(df: pd.DataFrame):
    """
    Walks the dataframe bar by bar and tracks a bullish and a bearish
    setup independently. Returns:
        signal        -> "BUY_TREND" / "SELL_TREND" / None
        key_level     -> the swing high/low used as the entry trigger
        pullback_low_high -> extreme reached during pullback (for stop loss)
        status        -> dict describing current phase of BOTH setups
                          (useful for debugging / alerting on "no trade yet")
    Only a signal on the LATEST bar is reported as an actionable alert;
    everything else is exposed via `status` so you can see progress.
    """
    n = len(df)

    # bullish setup state
    bull_state = "IDLE"          # IDLE -> TRACKING_HIGH -> ARMED
    bull_swing_high = None
    bull_pullback_count = 0
    bull_pullback_low = None     # lowest low seen during the pullback (for SL)

    # bearish setup state
    bear_state = "IDLE"
    bear_swing_low = None
    bear_pullback_count = 0
    bear_pullback_high = None    # highest high seen during the pullback (for SL)

    last_signal = None
    last_key_level = None
    last_pullback_extreme = None

    for i in range(1, n):
        prev_close, prev_ema = df['close'].iloc[i - 1], df['ema50'].iloc[i - 1]
        close, ema = df['close'].iloc[i], df['ema50'].iloc[i]
        high, low = df['high'].iloc[i], df['low'].iloc[i]
        row = df.iloc[i]

        crossed_up = prev_close < prev_ema and close > ema
        crossed_down = prev_close > prev_ema and close < ema

        # ---------------- BULLISH SETUP ----------------
        if crossed_up:
            # Step 1 complete -> start tracking swing high, cancel any bearish setup
            bull_state = "TRACKING_HIGH"
            bull_swing_high = high
            bull_pullback_count = 0
            bull_pullback_low = None
            bear_state = "IDLE"

        elif bull_state == "TRACKING_HIGH":
            if high > bull_swing_high:
                # still making new highs, pullback hasn't started
                bull_swing_high = high
                bull_pullback_count = 0
                bull_pullback_low = None
            elif is_red(row):
                bull_pullback_count += 1
                bull_pullback_low = low if bull_pullback_low is None else min(bull_pullback_low, low)
                if bull_pullback_count >= 2:
                    bull_state = "ARMED"   # Step 2 complete
            else:
                # green candle before pullback confirmed -> not consecutive, reset count
                bull_pullback_count = 0
                bull_pullback_low = None
            if close < ema:
                bull_state = "IDLE"        # trend broke back down, setup invalidated

        elif bull_state == "ARMED":
            if is_red(row):
                # extend pullback low tracking in case breakout hasn't happened yet
                bull_pullback_low = low if bull_pullback_low is None else min(bull_pullback_low, low)
            if close > bull_swing_high:
                # Step 3 complete -> BUY signal on this bar
                last_signal = "BUY_TREND"
                last_key_level = bull_swing_high
                last_pullback_extreme = bull_pullback_low
                bull_state = "IDLE"        # reset, ready to look for next setup
            elif close < ema:
                bull_state = "IDLE"        # invalidated before breakout

        # ---------------- BEARISH SETUP ----------------
        if crossed_down:
            bear_state = "TRACKING_LOW"
            bear_swing_low = low
            bear_pullback_count = 0
            bear_pullback_high = None
            bull_state = "IDLE"

        elif bear_state == "TRACKING_LOW":
            if low < bear_swing_low:
                bear_swing_low = low
                bear_pullback_count = 0
                bear_pullback_high = None
            elif is_green(row):
                bear_pullback_count += 1
                bear_pullback_high = high if bear_pullback_high is None else max(bear_pullback_high, high)
                if bear_pullback_count >= 2:
                    bear_state = "ARMED"
            else:
                bear_pullback_count = 0
                bear_pullback_high = None
            if close > ema:
                bear_state = "IDLE"

        elif bear_state == "ARMED":
            if is_green(row):
                bear_pullback_high = high if bear_pullback_high is None else max(bear_pullback_high, high)
            if close < bear_swing_low:
                last_signal = "SELL_TREND"
                last_key_level = bear_swing_low
                last_pullback_extreme = bear_pullback_high
                bear_state = "IDLE"
            elif close > ema:
                bear_state = "IDLE"

        # Only the FINAL bar's signal is the live/actionable one
        if i < n - 1:
            last_signal = None
            last_key_level = None
            last_pullback_extreme = None

    status = {
        "bull_phase": bull_state,
        "bull_pullback_candles": bull_pullback_count,
        "bull_swing_high": round(bull_swing_high, 5) if bull_swing_high else None,
        "bear_phase": bear_state,
        "bear_pullback_candles": bear_pullback_count,
        "bear_swing_low": round(bear_swing_low, 5) if bear_swing_low else None,
    }

    return last_signal, last_key_level, last_pullback_extreme, status


@app.post("/analyze")
def analyze(data: MarketData):
    df = pd.DataFrame(data.values)

    if not all(col in df.columns for col in ['open', 'high', 'low', 'close']):
        return {"error": "Missing OHLC data"}

    if len(df) < 60:
        return {"error": "Not enough data (need at least 60 candles for EMA50 warm-up + history)"}

    # Incoming data assumed newest-first -> flip so latest candle is last
    df = df.iloc[::-1].reset_index(drop=True)

    for col in ['open', 'high', 'low', 'close']:
        df[col] = df[col].astype(float)

    df['ema50'] = EMAIndicator(close=df['close'], window=50).ema_indicator()
    df = df.dropna(subset=['ema50']).reset_index(drop=True)

    if len(df) < 5:
        return {"error": "Not enough data after EMA50 warm-up"}

    latest = df.iloc[-1]
    signal, key_level, pullback_extreme, status = run_strategy(df)

    base_response = {
        "symbol": data.symbol,
        "timeframe": data.timeframe,
        "entry_price": round(latest['close'], 5),
        "ema50": round(latest['ema50'], 5),
        "status": status,   # <-- always shows WHY it's neutral, if it is
    }

    if signal == "BUY_TREND":
        stop_loss = pullback_extreme if pullback_extreme is not None else latest['close'] * 0.99
        risk = latest['close'] - stop_loss
        take_profit = latest['close'] + (risk * 2)
        base_response.update({
            "setup_type": "BREAKOUT_PULLBACK_BUY",
            "signal": "BUY",
            "key_level": round(key_level, 5),
            "stop_loss": round(stop_loss, 5),
            "take_profit": round(take_profit, 5),
            "risk_reward": "1:2",
        })

    elif signal == "SELL_TREND":
        stop_loss = pullback_extreme if pullback_extreme is not None else latest['close'] * 1.01
        risk = stop_loss - latest['close']
        take_profit = latest['close'] - (risk * 2)
        base_response.update({
            "setup_type": "BREAKOUT_PULLBACK_SELL",
            "signal": "SELL",
            "key_level": round(key_level, 5),
            "stop_loss": round(stop_loss, 5),
            "take_profit": round(take_profit, 5),
            "risk_reward": "1:2",
        })

    else:
        base_response.update({
            "setup_type": "NO_SETUP",
            "signal": "NEUTRAL",
            "info": "No entry trigger on the latest candle yet — see 'status' for current phase.",
            "key_level": None,
            "stop_loss": None,
            "take_profit": None,
        })

    return base_response


@app.get("/")
def home():
    return {"message": "EMA50 Breakout + Pullback Strategy API (state-machine version) running successfully"}
