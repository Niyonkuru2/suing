from fastapi import FastAPI
from pydantic import BaseModel
from typing import List, Dict, Any, Optional

import pandas as pd
import numpy as np

from ta.trend import EMAIndicator
from ta.volatility import AverageTrueRange


app = FastAPI(
    title="EMA50 Breakout + Pullback Trading Strategy API",
    version="2.0.0"
)


# ================================================================
# CONFIGURATION
# ================================================================

EMA_PERIOD = 50

# Minimum number of opposite-colored candles required
MIN_PULLBACK_CANDLES = 2

# ATR settings for Chandelier Stop
ATR_PERIOD = 14
CHANDLIER_MULTIPLIER = 3.0

# Number of candles used to calculate average candle range
BREAKOUT_AVG_PERIOD = 20

# Reject breakout candle if its range is this many times
# larger than the average candle range.
#
# Set to None to disable this filter.
MAX_BREAKOUT_RANGE_MULTIPLIER = 4.0

# How many candles are allowed between the EMA cross
# and completion of the setup.
MAX_SETUP_CANDLES = 30

# Require candle BODY to close beyond breakout level.
# This is always True for this implementation.
REQUIRE_BODY_CLOSE = True


# ================================================================
# REQUEST MODEL
# ================================================================

class MarketData(BaseModel):
    values: List[Dict[str, Any]]
    symbol: str
    timeframe: str


# ================================================================
# CANDLE HELPERS
# ================================================================

def is_red(row) -> bool:
    """Bearish candle."""
    return row["close"] < row["open"]


def is_green(row) -> bool:
    """Bullish candle."""
    return row["close"] > row["open"]


def candle_range(row) -> float:
    """Full candle range."""
    return float(row["high"] - row["low"])


# ================================================================
# ATR / CHANDELIER STOP
# ================================================================

def calculate_indicators(df: pd.DataFrame) -> pd.DataFrame:
    """
    Calculate all indicators used by the strategy.
    """

    # EMA 50
    df["ema50"] = EMAIndicator(
        close=df["close"],
        window=EMA_PERIOD
    ).ema_indicator()

    # ATR
    atr = AverageTrueRange(
        high=df["high"],
        low=df["low"],
        close=df["close"],
        window=ATR_PERIOD
    )

    df["atr"] = atr.average_true_range()

    # Average candle range
    df["candle_range"] = (
        df["high"] - df["low"]
    )

    df["avg_candle_range"] = (
        df["candle_range"]
        .rolling(BREAKOUT_AVG_PERIOD)
        .mean()
    )

    # Chandelier calculations
    df["highest_high"] = (
        df["high"]
        .rolling(ATR_PERIOD)
        .max()
    )

    df["lowest_low"] = (
        df["low"]
        .rolling(ATR_PERIOD)
        .min()
    )

    # Long Chandelier Stop
    df["chandelier_long"] = (
        df["highest_high"]
        - (df["atr"] * CHANDLIER_MULTIPLIER)
    )

    # Short Chandelier Stop
    df["chandelier_short"] = (
        df["lowest_low"]
        + (df["atr"] * CHANDLIER_MULTIPLIER)
    )

    return df


# ================================================================
# EMA CROSS DETECTION
# ================================================================

def find_last_ema_cross(
    df: pd.DataFrame,
    direction: str
) -> Optional[int]:
    """
    Find the most recent EMA50 cross.

    BUY:
        Previous close < previous EMA50
        Current close > current EMA50

    SELL:
        Previous close > previous EMA50
        Current close < current EMA50
    """

    last_cross = None

    for i in range(1, len(df)):

        previous = df.iloc[i - 1]
        current = df.iloc[i]

        if direction == "BUY":

            if (
                previous["close"] < previous["ema50"]
                and
                current["close"] > current["ema50"]
            ):
                last_cross = i

        elif direction == "SELL":

            if (
                previous["close"] > previous["ema50"]
                and
                current["close"] < current["ema50"]
            ):
                last_cross = i

    return last_cross


# ================================================================
# BREAKOUT CANDLE FILTER
# ================================================================

def is_abnormally_large_breakout(
    df: pd.DataFrame,
    index: int
) -> bool:
    """
    Reject breakout candles that are excessively large
    relative to recent average candle size.
    """

    if MAX_BREAKOUT_RANGE_MULTIPLIER is None:
        return False

    row = df.iloc[index]

    average_range = row["avg_candle_range"]

    if pd.isna(average_range) or average_range <= 0:
        return False

    current_range = candle_range(row)

    return (
        current_range
        >= average_range * MAX_BREAKOUT_RANGE_MULTIPLIER
    )


# ================================================================
# FIND BUY SETUP
# ================================================================

def find_buy_setup(
    df: pd.DataFrame,
    cross_idx: int
) -> Dict[str, Any]:
    """
    Full BUY algorithm.

    Sequence:

    EMA50 bullish cross
          ↓
    establish high
          ↓
    >= 2 red candles
          ↓
    pullback stays above EMA50
          ↓
    wait for close above key high
          ↓
    BUY
    """

    n = len(df)

    latest_idx = n - 1

    # Prevent extremely old setups
    if latest_idx - cross_idx > MAX_SETUP_CANDLES:
        return {
            "valid": False,
            "reason": "BUY setup expired"
        }

    # ------------------------------------------------------------
    # STEP 1 — EMA CROSS
    # ------------------------------------------------------------

    cross_candle = df.iloc[cross_idx]

    if cross_candle["close"] <= cross_candle["ema50"]:
        return {
            "valid": False,
            "reason": "BUY EMA cross not confirmed"
        }

    # ------------------------------------------------------------
    # STEP 2 — FIND THE HIGH BEFORE PULLBACK
    # ------------------------------------------------------------

    key_high = cross_candle["high"]
    key_high_idx = cross_idx

    pullback_start = None
    pullback_end = None

    i = cross_idx + 1

    while i < n:

        row = df.iloc[i]

        # --------------------------------------------------------
        # INVALIDATION:
        # Price closes back below EMA50
        # --------------------------------------------------------

        if row["close"] < row["ema50"]:
            return {
                "valid": False,
                "reason": "BUY invalidated: pullback closed below EMA50"
            }

        # --------------------------------------------------------
        # New high before correction
        # --------------------------------------------------------

        if row["high"] > key_high:

            key_high = row["high"]
            key_high_idx = i

            i += 1
            continue

        # --------------------------------------------------------
        # Start looking for red pullback
        # --------------------------------------------------------

        if is_red(row):

            if pullback_start is None:
                pullback_start = i

            j = i
            red_count = 0

            while j < n and is_red(df.iloc[j]):

                # Every pullback candle must remain above EMA50
                if df.iloc[j]["close"] < df.iloc[j]["ema50"]:
                    return {
                        "valid": False,
                        "reason": (
                            "BUY invalidated: "
                            "pullback broke EMA50"
                        )
                    }

                red_count += 1
                j += 1

            # ----------------------------------------------------
            # Required 2+ red candles
            # ----------------------------------------------------

            if red_count >= MIN_PULLBACK_CANDLES:

                pullback_end = j
                break

            # Pullback too short
            i = j
            continue

        i += 1

    # No pullback found
    if pullback_start is None or pullback_end is None:
        return {
            "valid": False,
            "reason": "BUY waiting for 2+ red-candle pullback"
        }

    # ------------------------------------------------------------
    # STEP 3 — CHECK CURRENT PRICE
    # ------------------------------------------------------------

    if latest_idx < pullback_end:
        return {
            "valid": False,
            "reason": "BUY pullback still forming"
        }

    # ------------------------------------------------------------
    # STEP 4 — EMA MUST STILL SUPPORT TRADE
    # ------------------------------------------------------------

    latest = df.iloc[latest_idx]

    if latest["close"] < latest["ema50"]:
        return {
            "valid": False,
            "reason": "BUY invalidated: current price below EMA50"
        }

    # ------------------------------------------------------------
    # STEP 5 — BREAKOUT ABOVE KEY HIGH
    # ------------------------------------------------------------

    breakout_confirmed = (
        latest["close"] > key_high
    )

    if not breakout_confirmed:
        return {
            "valid": False,
            "reason": (
                "BUY waiting: price has not closed "
                "above key swing high"
            ),
            "key_level": float(key_high),
            "key_level_index": key_high_idx
        }

    # ------------------------------------------------------------
    # STEP 6 — REJECT HUGE BREAKOUT CANDLE
    # ------------------------------------------------------------

    if is_abnormally_large_breakout(
        df,
        latest_idx
    ):
        return {
            "valid": False,
            "reason": (
                "BUY rejected: breakout candle "
                "is abnormally large"
            ),
            "key_level": float(key_high)
        }

    # ------------------------------------------------------------
    # BUY CONFIRMED
    # ------------------------------------------------------------

    return {
        "valid": True,
        "direction": "BUY",
        "cross_idx": cross_idx,
        "key_level": float(key_high),
        "key_level_idx": key_high_idx,
        "pullback_start": pullback_start,
        "pullback_end": pullback_end,
        "breakout_idx": latest_idx
    }


# ================================================================
# FIND SELL SETUP
# ================================================================

def find_sell_setup(
    df: pd.DataFrame,
    cross_idx: int
) -> Dict[str, Any]:
    """
    Full SELL algorithm.

    Sequence:

    EMA50 bearish cross
          ↓
    establish low
          ↓
    >= 2 green candles
          ↓
    pullback stays below EMA50
          ↓
    wait for close below key low
          ↓
    SELL
    """

    n = len(df)

    latest_idx = n - 1

    # Prevent extremely old setups
    if latest_idx - cross_idx > MAX_SETUP_CANDLES:
        return {
            "valid": False,
            "reason": "SELL setup expired"
        }

    cross_candle = df.iloc[cross_idx]

    if cross_candle["close"] >= cross_candle["ema50"]:
        return {
            "valid": False,
            "reason": "SELL EMA cross not confirmed"
        }

    # ------------------------------------------------------------
    # STEP 1 — FIND LOW BEFORE PULLBACK
    # ------------------------------------------------------------

    key_low = cross_candle["low"]
    key_low_idx = cross_idx

    pullback_start = None
    pullback_end = None

    i = cross_idx + 1

    while i < n:

        row = df.iloc[i]

        # --------------------------------------------------------
        # INVALIDATION:
        # Price closes back above EMA50
        # --------------------------------------------------------

        if row["close"] > row["ema50"]:
            return {
                "valid": False,
                "reason": (
                    "SELL invalidated: "
                    "pullback closed above EMA50"
                )
            }

        # --------------------------------------------------------
        # New low before correction
        # --------------------------------------------------------

        if row["low"] < key_low:

            key_low = row["low"]
            key_low_idx = i

            i += 1
            continue

        # --------------------------------------------------------
        # Start looking for green pullback
        # --------------------------------------------------------

        if is_green(row):

            if pullback_start is None:
                pullback_start = i

            j = i
            green_count = 0

            while j < n and is_green(df.iloc[j]):

                # Every pullback candle must remain below EMA50
                if df.iloc[j]["close"] > df.iloc[j]["ema50"]:
                    return {
                        "valid": False,
                        "reason": (
                            "SELL invalidated: "
                            "pullback broke EMA50"
                        )
                    }

                green_count += 1
                j += 1

            # ----------------------------------------------------
            # Required 2+ green candles
            # ----------------------------------------------------

            if green_count >= MIN_PULLBACK_CANDLES:

                pullback_end = j
                break

            i = j
            continue

        i += 1

    # No pullback
    if pullback_start is None or pullback_end is None:
        return {
            "valid": False,
            "reason": "SELL waiting for 2+ green-candle pullback"
        }

    # ------------------------------------------------------------
    # STEP 2 — PULLBACK FINISHED?
    # ------------------------------------------------------------

    if latest_idx < pullback_end:
        return {
            "valid": False,
            "reason": "SELL pullback still forming"
        }

    latest = df.iloc[latest_idx]

    # ------------------------------------------------------------
    # STEP 3 — EMA SUPPORT
    # ------------------------------------------------------------

    if latest["close"] > latest["ema50"]:
        return {
            "valid": False,
            "reason": "SELL invalidated: current price above EMA50"
        }

    # ------------------------------------------------------------
    # STEP 4 — BREAK BELOW KEY LOW
    # ------------------------------------------------------------

    breakout_confirmed = (
        latest["close"] < key_low
    )

    if not breakout_confirmed:
        return {
            "valid": False,
            "reason": (
                "SELL waiting: price has not closed "
                "below key swing low"
            ),
            "key_level": float(key_low),
            "key_level_index": key_low_idx
        }

    # ------------------------------------------------------------
    # STEP 5 — HUGE BREAKOUT FILTER
    # ------------------------------------------------------------

    if is_abnormally_large_breakout(
        df,
        latest_idx
    ):
        return {
            "valid": False,
            "reason": (
                "SELL rejected: breakout candle "
                "is abnormally large"
            ),
            "key_level": float(key_low)
        }

    # ------------------------------------------------------------
    # SELL CONFIRMED
    # ------------------------------------------------------------

    return {
        "valid": True,
        "direction": "SELL",
        "cross_idx": cross_idx,
        "key_level": float(key_low),
        "key_level_idx": key_low_idx,
        "pullback_start": pullback_start,
        "pullback_end": pullback_end,
        "breakout_idx": latest_idx
    }


# ================================================================
# STOP LOSS CALCULATION
# ================================================================

def calculate_buy_stop_loss(
    df: pd.DataFrame,
    setup: Dict[str, Any],
    entry: float
) -> float:
    """
    BUY SL.

    Primary:
        Chandelier Long Stop

    Also make sure SL remains below entry.
    """

    idx = setup["breakout_idx"]

    chandelier = df.iloc[idx]["chandelier_long"]

    # Fallback if ATR isn't available
    if pd.isna(chandelier):
        pullback_low = df.iloc[
            setup["key_level_idx"] + 1:
            setup["breakout_idx"] + 1
        ]["low"].min()

        return float(pullback_low)

    stop = float(chandelier)

    # Safety:
    # SL cannot be above entry
    if stop >= entry:
        pullback_low = df.iloc[
            setup["key_level_idx"] + 1:
            setup["breakout_idx"] + 1
        ]["low"].min()

        stop = float(pullback_low)

    return stop


def calculate_sell_stop_loss(
    df: pd.DataFrame,
    setup: Dict[str, Any],
    entry: float
) -> float:
    """
    SELL SL.

    Primary:
        Chandelier Short Stop
    """

    idx = setup["breakout_idx"]

    chandelier = df.iloc[idx]["chandelier_short"]

    if pd.isna(chandelier):

        pullback_high = df.iloc[
            setup["key_level_idx"] + 1:
            setup["breakout_idx"] + 1
        ]["high"].max()

        return float(pullback_high)

    stop = float(chandelier)

    # Safety:
    # SL cannot be below entry
    if stop <= entry:

        pullback_high = df.iloc[
            setup["key_level_idx"] + 1:
            setup["breakout_idx"] + 1
        ]["high"].max()

        stop = float(pullback_high)

    return stop


# ================================================================
# ROUNDING
# ================================================================

def round_price(value: Optional[float], decimals: int = 5):

    if value is None:
        return None

    if pd.isna(value):
        return None

    return round(float(value), decimals)


# ================================================================
# MAIN ANALYSIS
# ================================================================

@app.post("/analyze")
def analyze(data: MarketData):

    # ------------------------------------------------------------
    # BUILD DATAFRAME
    # ------------------------------------------------------------

    df = pd.DataFrame(data.values)

    required_columns = [
        "open",
        "high",
        "low",
        "close"
    ]

    if not all(
        column in df.columns
        for column in required_columns
    ):
        return {
            "error": (
                "Missing OHLC data. "
                "Required: open, high, low, close"
            )
        }

    if len(df) < 100:
        return {
            "error": (
                "Not enough data. "
                "At least 100 candles recommended."
            )
        }

    # ------------------------------------------------------------
    # INPUT ORDER
    # ------------------------------------------------------------
    #
    # We assume:
    #
    # values[0] = newest
    # values[-1] = oldest
    #
    # Reverse it so:
    #
    # df.iloc[0] = oldest
    # df.iloc[-1] = newest
    # ------------------------------------------------------------

    df = (
        df
        .iloc[::-1]
        .reset_index(drop=True)
    )

    # Convert OHLC to numeric
    for column in required_columns:

        df[column] = pd.to_numeric(
            df[column],
            errors="coerce"
        )

    # Remove invalid rows
    df = df.dropna(
        subset=required_columns
    ).reset_index(drop=True)

    # ------------------------------------------------------------
    # INDICATORS
    # ------------------------------------------------------------

    df = calculate_indicators(df)

    # Remove indicator warm-up
    df = df.dropna(
        subset=["ema50"]
    ).reset_index(drop=True)

    if len(df) < 60:

        return {
            "error": (
                "Not enough candles after "
                "indicator warm-up."
            )
        }

    # ------------------------------------------------------------
    # LATEST CANDLE
    # ------------------------------------------------------------

    latest_idx = len(df) - 1
    latest = df.iloc[latest_idx]

    # ------------------------------------------------------------
    # FIND LAST EMA CROSS
    # ------------------------------------------------------------

    buy_cross = find_last_ema_cross(
        df,
        "BUY"
    )

    sell_cross = find_last_ema_cross(
        df,
        "SELL"
    )

    # ------------------------------------------------------------
    # DETECT BUY
    # ------------------------------------------------------------

    buy_setup = None

    if buy_cross is not None:

        buy_setup = find_buy_setup(
            df,
            buy_cross
        )

    # ------------------------------------------------------------
    # DETECT SELL
    # ------------------------------------------------------------

    sell_setup = None

    if sell_cross is not None:

        sell_setup = find_sell_setup(
            df,
            sell_cross
        )

    # ============================================================
    # BUY SIGNAL
    # ============================================================

    if buy_setup and buy_setup.get("valid"):

        entry = float(latest["close"])

        stop_loss = calculate_buy_stop_loss(
            df,
            buy_setup,
            entry
        )

        risk = entry - stop_loss

        # Invalid risk
        if risk <= 0:

            return {
                "symbol": data.symbol,
                "timeframe": data.timeframe,
                "setup_type": "INVALID_BUY",
                "signal": "NO_TRADE",
                "reason": (
                    "BUY setup found but calculated "
                    "stop loss is invalid."
                ),
                "entry": round_price(entry),
                "ema50": round_price(latest["ema50"])
            }

        take_profit = entry + (
            risk * 2
        )

        return {
            "symbol": data.symbol,
            "timeframe": data.timeframe,

            "setup_type":
                "EMA50_BREAKOUT_PULLBACK",

            "signal":
                "BUY",

            "decision":
                "ALLOW_BUY",

            "conditions": {

                "price_below_ema_before_cross": True,

                "ema50_bullish_breakout": True,

                "breakout_close_above_ema50":
                    True,

                "minimum_pullback_candles":
                    MIN_PULLBACK_CANDLES,

                "pullback_type":
                    "RED_CANDLES",

                "pullback_stayed_above_ema50":
                    True,

                "key_level_broken":
                    True,

                "breakout_closed_above_key_level":
                    True,

                "large_breakout_rejected":
                    not is_abnormally_large_breakout(
                        df,
                        latest_idx
                    )
            },

            "entry":
                round_price(entry),

            "key_level":
                round_price(
                    buy_setup["key_level"]
                ),

            "ema50":
                round_price(
                    latest["ema50"]
                ),

            "atr":
                round_price(
                    latest["atr"]
                ),

            "stop_loss":
                round_price(stop_loss),

            "take_profit":
                round_price(take_profit),

            "risk_distance":
                round_price(risk),

            "reward_distance":
                round_price(risk * 2),

            "risk_reward":
                "1:2",

            "breakout_candle_index":
                latest_idx,

            "message":
                "BUY conditions fully confirmed."
        }

    # ============================================================
    # SELL SIGNAL
    # ============================================================

    if sell_setup and sell_setup.get("valid"):

        entry = float(latest["close"])

        stop_loss = calculate_sell_stop_loss(
            df,
            sell_setup,
            entry
        )

        risk = stop_loss - entry

        if risk <= 0:

            return {
                "symbol": data.symbol,
                "timeframe": data.timeframe,
                "setup_type": "INVALID_SELL",
                "signal": "NO_TRADE",
                "reason": (
                    "SELL setup found but calculated "
                    "stop loss is invalid."
                ),
                "entry": round_price(entry),
                "ema50": round_price(latest["ema50"])
            }

        take_profit = entry - (
            risk * 2
        )

        return {
            "symbol": data.symbol,
            "timeframe": data.timeframe,

            "setup_type":
                "EMA50_BREAKOUT_PULLBACK",

            "signal":
                "SELL",

            "decision":
                "ALLOW_SELL",

            "conditions": {

                "price_above_ema_before_cross":
                    True,

                "ema50_bearish_breakout":
                    True,

                "breakout_close_below_ema50":
                    True,

                "minimum_pullback_candles":
                    MIN_PULLBACK_CANDLES,

                "pullback_type":
                    "GREEN_CANDLES",

                "pullback_stayed_below_ema50":
                    True,

                "key_level_broken":
                    True,

                "breakout_closed_below_key_level":
                    True,

                "large_breakout_rejected":
                    not is_abnormally_large_breakout(
                        df,
                        latest_idx
                    )
            },

            "entry":
                round_price(entry),

            "key_level":
                round_price(
                    sell_setup["key_level"]
                ),

            "ema50":
                round_price(
                    latest["ema50"]
                ),

            "atr":
                round_price(
                    latest["atr"]
                ),

            "stop_loss":
                round_price(stop_loss),

            "take_profit":
                round_price(take_profit),

            "risk_distance":
                round_price(risk),

            "reward_distance":
                round_price(risk * 2),

            "risk_reward":
                "1:2",

            "breakout_candle_index":
                latest_idx,

            "message":
                "SELL conditions fully confirmed."
        }

    # ============================================================
    # NO TRADE
    # ============================================================

    reasons = []

    if buy_setup:
        reasons.append(
            f"BUY: {buy_setup.get('reason', 'not confirmed')}"
        )

    if sell_setup:
        reasons.append(
            f"SELL: {sell_setup.get('reason', 'not confirmed')}"
        )

    if not reasons:
        reasons.append(
            "No valid EMA50 breakout detected."
        )

    # Determine current market state
    if latest["close"] > latest["ema50"]:
        market_state = "ABOVE_EMA50"
    elif latest["close"] < latest["ema50"]:
        market_state = "BELOW_EMA50"
    else:
        market_state = "AT_EMA50"

    return {

        "symbol":
            data.symbol,

        "timeframe":
            data.timeframe,

        "setup_type":
            "NO_SETUP",

        "signal":
            "NO_TRADE",

        "decision":
            "WAIT",

        "market_state":
            market_state,

        "latest_price":
            round_price(
                latest["close"]
            ),

        "ema50":
            round_price(
                latest["ema50"]
            ),

        "reasons":
            reasons,

        "entry":
            round_price(
                latest["close"]
            ),

        "stop_loss":
            None,

        "take_profit":
            None,

        "risk_reward":
            "1:2",

        "message":
            "No complete trading setup. WAIT."
    }


# ================================================================
# HEALTH CHECK
# ================================================================

@app.get("/")
def home():

    return {
        "message":
            "EMA50 Breakout + Pullback Strategy API running",

        "strategy":
            "EMA50 Breakout + Pullback",

        "buy_rule":
            "EMA50 bullish break → 2+ red pullback → "
            "stay above EMA50 → close above key high",

        "sell_rule":
            "EMA50 bearish break → 2+ green pullback → "
            "stay below EMA50 → close below key low",

        "risk_reward":
            "1:2",

        "ema_period":
            EMA_PERIOD,

        "minimum_pullback_candles":
            MIN_PULLBACK_CANDLES,

        "atr_period":
            ATR_PERIOD,

        "chandelier_multiplier":
            CHANDLIER_MULTIPLIER
    }
