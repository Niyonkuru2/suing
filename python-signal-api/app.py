from fastapi import FastAPI
from pydantic import BaseModel
import pandas as pd
from ta.trend import EMAIndicator

app = FastAPI(
    title="EMA50 Breakout + Pullback Strategy API",
    version="2.0"
)


# ================================================================
# REQUEST MODEL
# ================================================================

class MarketData(BaseModel):
    values: list
    symbol: str
    timeframe: str


# ================================================================
# CANDLE HELPERS
# ================================================================

def is_red(row):
    return row["close"] < row["open"]


def is_green(row):
    return row["close"] > row["open"]


# ================================================================
# RESET HELPERS
# ================================================================

def reset_bull():
    return {
        "state": "IDLE",
        "swing_high": None,
        "pullback_count": 0,
        "pullback_low": None,
        "setup_start": None,
    }


def reset_bear():
    return {
        "state": "IDLE",
        "swing_low": None,
        "pullback_count": 0,
        "pullback_high": None,
        "setup_start": None,
    }


# ================================================================
# CORE STRATEGY
# ================================================================

def run_strategy(df: pd.DataFrame):

    n = len(df)

    bull = reset_bull()
    bear = reset_bear()

    latest_signal = None
    latest_key_level = None
    latest_pullback_extreme = None

    # ------------------------------------------------------------
    # We scan from oldest candle to newest candle.
    # ------------------------------------------------------------

    for i in range(1, n):

        prev_close = df["close"].iloc[i - 1]
        prev_ema = df["ema50"].iloc[i - 1]

        close = df["close"].iloc[i]
        ema = df["ema50"].iloc[i]

        high = df["high"].iloc[i]
        low = df["low"].iloc[i]

        row = df.iloc[i]

        # ========================================================
        # EMA TREND CONDITIONS
        # ========================================================

        crossed_up = (
            prev_close <= prev_ema
            and close > ema
        )

        crossed_down = (
            prev_close >= prev_ema
            and close < ema
        )

        above_ema = close > ema
        below_ema = close < ema

        # ========================================================
        # NEW BULLISH EMA CROSS
        # ========================================================

        if crossed_up:

            bull = {
                "state": "TRACKING_HIGH",
                "swing_high": high,
                "pullback_count": 0,
                "pullback_low": None,
                "setup_start": i,
            }

            # Opposite setup is invalidated
            bear = reset_bear()

        # ========================================================
        # NEW BEARISH EMA CROSS
        # ========================================================

        elif crossed_down:

            bear = {
                "state": "TRACKING_LOW",
                "swing_low": low,
                "pullback_count": 0,
                "pullback_high": None,
                "setup_start": i,
            }

            # Opposite setup is invalidated
            bull = reset_bull()

        # ========================================================
        # BULLISH SETUP
        # ========================================================

        if bull["state"] == "TRACKING_HIGH":

            # If price continues making higher highs,
            # update the swing high.
            if high > bull["swing_high"]:

                bull["swing_high"] = high

                # New high means pullback has not been confirmed.
                bull["pullback_count"] = 0
                bull["pullback_low"] = None

            # Red candle = pullback candle
            elif is_red(row):

                bull["pullback_count"] += 1

                if bull["pullback_low"] is None:
                    bull["pullback_low"] = low
                else:
                    bull["pullback_low"] = min(
                        bull["pullback_low"],
                        low
                    )

                # Two or more pullback candles = ARMED
                if bull["pullback_count"] >= 2:

                    bull["state"] = "ARMED"

            # Green candle after pullback has not reached
            # required confirmation yet.
            else:

                # Do not destroy the entire bullish trend.
                # Only reset the pullback counter.
                bull["pullback_count"] = 0
                bull["pullback_low"] = None

            # If candle closes below EMA, invalidate.
            if close < ema:

                bull = reset_bull()

        # ========================================================
        # BULLISH ARMED STATE
        # ========================================================

        elif bull["state"] == "ARMED":

            # Continue tracking the lowest point of pullback.
            if low < bull["pullback_low"]:
                bull["pullback_low"] = low

            # ----------------------------------------------------
            # BREAKOUT CONFIRMATION
            #
            # IMPORTANT:
            # We use CLOSE > swing high.
            # A wick above the level is NOT enough.
            # ----------------------------------------------------

            if close > bull["swing_high"]:

                latest_signal = "BUY_TREND"
                latest_key_level = bull["swing_high"]
                latest_pullback_extreme = bull["pullback_low"]

                # Reset after signal
                bull = reset_bull()

            # Price lost EMA before breakout
            elif close < ema:

                bull = reset_bull()

        # ========================================================
        # BEARISH SETUP
        # ========================================================

        if bear["state"] == "TRACKING_LOW":

            # Continue making lower lows
            if low < bear["swing_low"]:

                bear["swing_low"] = low

                bear["pullback_count"] = 0
                bear["pullback_high"] = None

            # Green candle = bearish pullback
            elif is_green(row):

                bear["pullback_count"] += 1

                if bear["pullback_high"] is None:
                    bear["pullback_high"] = high
                else:
                    bear["pullback_high"] = max(
                        bear["pullback_high"],
                        high
                    )

                # Two or more pullback candles
                if bear["pullback_count"] >= 2:

                    bear["state"] = "ARMED"

            else:

                bear["pullback_count"] = 0
                bear["pullback_high"] = None

            # Price closed above EMA -> invalidate
            if close > ema:

                bear = reset_bear()

        # ========================================================
        # BEARISH ARMED STATE
        # ========================================================

        elif bear["state"] == "ARMED":

            # Continue tracking highest pullback point
            if high > bear["pullback_high"]:
                bear["pullback_high"] = high

            # ----------------------------------------------------
            # BREAKDOWN CONFIRMATION
            #
            # CLOSE must be below swing low.
            # ----------------------------------------------------

            if close < bear["swing_low"]:

                latest_signal = "SELL_TREND"
                latest_key_level = bear["swing_low"]
                latest_pullback_extreme = bear["pullback_high"]

                bear = reset_bear()

            # Price lost bearish trend
            elif close > ema:

                bear = reset_bear()

    # ============================================================
    # CURRENT STATUS
    # ============================================================

    status = {

        # ---------------- BULL ----------------

        "bull_phase": bull["state"],

        "bull_pullback_candles": bull["pullback_count"],

        "bull_swing_high": (
            round(bull["swing_high"], 5)
            if bull["swing_high"] is not None
            else None
        ),

        "bull_pullback_low": (
            round(bull["pullback_low"], 5)
            if bull["pullback_low"] is not None
            else None
        ),

        # ---------------- BEAR ----------------

        "bear_phase": bear["state"],

        "bear_pullback_candles": bear["pullback_count"],

        "bear_swing_low": (
            round(bear["swing_low"], 5)
            if bear["swing_low"] is not None
            else None
        ),

        "bear_pullback_high": (
            round(bear["pullback_high"], 5)
            if bear["pullback_high"] is not None
            else None
        ),
    }

    return (
        latest_signal,
        latest_key_level,
        latest_pullback_extreme,
        status
    )


# ================================================================
# ANALYZE ENDPOINT
# ================================================================

@app.post("/analyze")
def analyze(data: MarketData):

    # ------------------------------------------------------------
    # Create dataframe
    # ------------------------------------------------------------

    df = pd.DataFrame(data.values)

    required_columns = [
        "open",
        "high",
        "low",
        "close"
    ]

    if not all(col in df.columns for col in required_columns):

        return {
            "error": "Missing OHLC data"
        }

    # ------------------------------------------------------------
    # Minimum data
    # ------------------------------------------------------------

    if len(df) < 60:

        return {
            "error": (
                "Not enough data. "
                "Need at least 60 candles "
                "for EMA50 calculation."
            )
        }

    # ------------------------------------------------------------
    # API sends newest FIRST.
    #
    # Convert to oldest FIRST.
    # ------------------------------------------------------------

    df = (
        df.iloc[::-1]
        .reset_index(drop=True)
    )

    # ------------------------------------------------------------
    # Convert OHLC to numbers
    # ------------------------------------------------------------

    for col in required_columns:

        df[col] = pd.to_numeric(
            df[col],
            errors="coerce"
        )

    # Remove invalid candles
    df = df.dropna(
        subset=required_columns
    ).reset_index(drop=True)

    # ------------------------------------------------------------
    # EMA50
    # ------------------------------------------------------------

    df["ema50"] = EMAIndicator(
        close=df["close"],
        window=50
    ).ema_indicator()

    # Remove EMA warm-up
    df = df.dropna(
        subset=["ema50"]
    ).reset_index(drop=True)

    if len(df) < 5:

        return {
            "error": "Not enough data after EMA50 calculation"
        }

    # ------------------------------------------------------------
    # Latest candle
    # ------------------------------------------------------------

    latest = df.iloc[-1]

    # ------------------------------------------------------------
    # Run strategy
    # ------------------------------------------------------------

    (
        signal,
        key_level,
        pullback_extreme,
        status
    ) = run_strategy(df)

    # ------------------------------------------------------------
    # Base response
    # ------------------------------------------------------------

    response = {

        "symbol": data.symbol,

        "timeframe": data.timeframe,

        "entry_price": round(
            float(latest["close"]),
            5
        ),

        "ema50": round(
            float(latest["ema50"]),
            5
        ),

        "price_vs_ema": (
            "ABOVE"
            if latest["close"] > latest["ema50"]
            else "BELOW"
        ),

        "status": status,
    }

    # ============================================================
    # BUY
    # ============================================================

    if signal == "BUY_TREND":

        if (
            pullback_extreme is None
            or pullback_extreme >= latest["close"]
        ):

            return {
                **response,
                "setup_type": "INVALID_BUY_SETUP",
                "signal": "NEUTRAL",
                "info": "Invalid pullback stop level."
            }

        stop_loss = float(
            pullback_extreme
        )

        entry = float(
            latest["close"]
        )

        risk = entry - stop_loss

        if risk <= 0:

            return {
                **response,
                "setup_type": "INVALID_BUY_SETUP",
                "signal": "NEUTRAL",
                "info": "Invalid BUY risk distance."
            }

        take_profit = (
            entry + (risk * 2)
        )

        response.update({

            "setup_type":
                "BREAKOUT_PULLBACK_BUY",

            "signal":
                "BUY",

            "key_level":
                round(float(key_level), 5),

            "stop_loss":
                round(stop_loss, 5),

            "take_profit":
                round(take_profit, 5),

            "risk_distance":
                round(risk, 5),

            "risk_reward":
                "1:2",

            "confirmation":
                "Candle closed above swing high."
        })

    # ============================================================
    # SELL
    # ============================================================

    elif signal == "SELL_TREND":

        if (
            pullback_extreme is None
            or pullback_extreme <= latest["close"]
        ):

            return {
                **response,
                "setup_type": "INVALID_SELL_SETUP",
                "signal": "NEUTRAL",
                "info": "Invalid pullback stop level."
            }

        stop_loss = float(
            pullback_extreme
        )

        entry = float(
            latest["close"]
        )

        risk = stop_loss - entry

        if risk <= 0:

            return {
                **response,
                "setup_type": "INVALID_SELL_SETUP",
                "signal": "NEUTRAL",
                "info": "Invalid SELL risk distance."
            }

        take_profit = (
            entry - (risk * 2)
        )

        response.update({

            "setup_type":
                "BREAKOUT_PULLBACK_SELL",

            "signal":
                "SELL",

            "key_level":
                round(float(key_level), 5),

            "stop_loss":
                round(stop_loss, 5),

            "take_profit":
                round(take_profit, 5),

            "risk_distance":
                round(risk, 5),

            "risk_reward":
                "1:2",

            "confirmation":
                "Candle closed below swing low."
        })

    # ============================================================
    # NO ACTIONABLE SIGNAL
    # ============================================================

    else:

        # Determine useful human-readable status

        if status["bull_phase"] == "ARMED":

            info = (
                "Bullish setup armed. "
                "Waiting for candle close above "
                "the swing high."
            )

            setup_type = (
                "BREAKOUT_PULLBACK_BUY_WAITING"
            )

            signal_status = "WAIT_BUY"

        elif status["bear_phase"] == "ARMED":

            info = (
                "Bearish setup armed. "
                "Waiting for candle close below "
                "the swing low."
            )

            setup_type = (
                "BREAKOUT_PULLBACK_SELL_WAITING"
            )

            signal_status = "WAIT_SELL"

        elif status["bull_phase"] == "TRACKING_HIGH":

            info = (
                "Bullish trend detected. "
                "Waiting for pullback confirmation."
            )

            setup_type = (
                "BULLISH_PULLBACK_FORMING"
            )

            signal_status = "WAIT_BUY"

        elif status["bear_phase"] == "TRACKING_LOW":

            info = (
                "Bearish trend detected. "
                "Waiting for pullback confirmation."
            )

            setup_type = (
                "BEARISH_PULLBACK_FORMING"
            )

            signal_status = "WAIT_SELL"

        else:

            info = (
                "No active breakout-pullback setup."
            )

            setup_type = "NO_SETUP"

            signal_status = "NEUTRAL"

        response.update({

            "setup_type":
                setup_type,

            "signal":
                signal_status,

            "info":
                info,

            "key_level":
                None,

            "stop_loss":
                None,

            "take_profit":
                None,

            "risk_reward":
                None
        })

    return response


# ================================================================
# HEALTH CHECK
# ================================================================

@app.get("/")
def home():

    return {
        "message":
            "EMA50 Breakout + Pullback Strategy API running successfully",

        "version":
            "2.0"
    }
