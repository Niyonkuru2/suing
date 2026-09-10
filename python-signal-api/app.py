from fastapi import FastAPI
from pydantic import BaseModel
from typing import Optional
import pandas as pd
from datetime import datetime
from zoneinfo import ZoneInfo


app = FastAPI(
    title="New York 4H Range Breakout + Re-entry Strategy API"
)


# ================================================================
# Configuration
# ================================================================

NY_TZ = ZoneInfo("America/New_York")
RISK_REWARD = 2.0


# ================================================================
# Request model
# ================================================================

class MarketData(BaseModel):
    values: list
    symbol: str
    timeframe: str


# ================================================================
# Candle helpers
# ================================================================

def is_red(row):
    return row["close"] < row["open"]


def is_green(row):
    return row["close"] > row["open"]


# ================================================================
# Time handling
# ================================================================

def convert_to_new_york(series):
    """
    Convert timestamps to America/New_York.

    Supports:
    - ISO timestamps with timezone
    - Unix timestamps in seconds
    - Unix timestamps in milliseconds
    """

    # Try normal datetime parsing first
    parsed = pd.to_datetime(series, errors="coerce", utc=True)

    # If parsing failed for numeric timestamps, try numeric conversion
    failed = parsed.isna()

    if failed.any():
        numeric = pd.to_numeric(series[failed], errors="coerce")

        # Determine seconds vs milliseconds
        parsed_numeric = pd.to_datetime(
            numeric,
            unit="ms",
            errors="coerce",
            utc=True
        )

        # Try seconds for values that didn't work
        still_failed = parsed_numeric.isna()

        if still_failed.any():
            parsed_seconds = pd.to_datetime(
                numeric[still_failed],
                unit="s",
                errors="coerce",
                utc=True
            )

            parsed_numeric.loc[still_failed] = parsed_seconds

        parsed.loc[failed] = parsed_numeric

    return parsed.dt.tz_convert(NY_TZ)


# ================================================================
# Find today's first New York 4H candle
# ================================================================

def find_new_york_range(df):
    """
    Finds the first 4H candle of the New York trading day.

    Expected candle:
        00:00 -> 04:00 New York

    Returns:
        range_high
        range_low
        range_start
        range_end
    """

    if "time" not in df.columns:
        return None

    df = df.copy()

    df["ny_time"] = convert_to_new_york(df["time"])

    if df["ny_time"].isna().all():
        return None

    latest_ny = df["ny_time"].iloc[-1]
    current_date = latest_ny.date()

    # Find today's 00:00 candle
    candidates = df[
        (df["ny_time"].dt.date == current_date)
        & (df["ny_time"].dt.hour == 0)
        & (df["ny_time"].dt.minute == 0)
    ]

    if candidates.empty:
        return None

    # There should normally be exactly one
    range_candle = candidates.iloc[0]

    range_start = range_candle["ny_time"]
    range_end = range_start + pd.Timedelta(hours=4)

    # Make sure this is actually the first 4H candle
    if range_start.hour != 0:
        return None

    return {
        "high": float(range_candle["high"]),
        "low": float(range_candle["low"]),
        "start": range_start,
        "end": range_end,
    }


# ================================================================
# Core strategy
# ================================================================

def run_strategy(df: pd.DataFrame):
    """
    New York 4H Range Breakout + Re-entry strategy.

    Rules:

    1. Identify the first 4H New York candle:
           00:00 - 04:00 New York

    2. After that candle closes:
           range_high = high
           range_low  = low

    3. SHORT:
           A 5m candle must CLOSE above range_high.
           Then a later 5m candle must CLOSE back below range_high.
           Entry = re-entry candle close.
           SL = highest high reached after breakout.
           TP = 2R.

    4. LONG:
           A 5m candle must CLOSE below range_low.
           Then a later 5m candle must CLOSE back above range_low.
           Entry = re-entry candle close.
           SL = lowest low reached after breakout.
           TP = 2R.

    5. Wick-only breaks do NOT count.

    6. Only a signal on the latest candle is actionable.
    """

    if len(df) < 2:
        return None, None, None, None, {
            "phase": "WAITING",
            "info": "Not enough candles"
        }

    df = df.copy()

    # ------------------------------------------------------------
    # Validate time
    # ------------------------------------------------------------

    if "time" not in df.columns:
        return None, None, None, None, {
            "phase": "ERROR",
            "info": "Missing 'time' field. Timestamp is required."
        }

    df["ny_time"] = convert_to_new_york(df["time"])

    if df["ny_time"].isna().any():
        return None, None, None, None, {
            "phase": "ERROR",
            "info": "Invalid timestamp found in market data."
        }

    # ------------------------------------------------------------
    # Get today's range
    # ------------------------------------------------------------

    range_info = find_new_york_range(df)

    if range_info is None:
        return None, None, None, None, {
            "phase": "WAITING_FOR_4H",
            "info": "Today's 00:00 New York 4H candle was not found yet."
        }

    range_high = range_info["high"]
    range_low = range_info["low"]
    range_start = range_info["start"]
    range_end = range_info["end"]

    # ------------------------------------------------------------
    # 4H candle must be closed before trading
    # ------------------------------------------------------------

    latest_time = df["ny_time"].iloc[-1]

    if latest_time < range_end:
        return None, None, None, None, {
            "phase": "WAITING_FOR_4H_CLOSE",
            "range_high": round(range_high, 5),
            "range_low": round(range_low, 5),
            "range_start": str(range_start),
            "range_end": str(range_end),
            "info": "Waiting for the first New York 4H candle to close."
        }

    # ------------------------------------------------------------
    # Only candles AFTER the 4H range
    # ------------------------------------------------------------

    trading_df = df[
        df["ny_time"] >= range_end
    ].copy()

    if trading_df.empty:
        return None, None, None, None, {
            "phase": "WAITING_FOR_5M",
            "range_high": round(range_high, 5),
            "range_low": round(range_low, 5),
            "info": "4H range confirmed. Waiting for 5M breakout."
        }

    # ============================================================
    # State
    # ============================================================

    short_breakout = False
    short_breakout_extreme = None
    short_breakout_time = None

    long_breakout = False
    long_breakout_extreme = None
    long_breakout_time = None

    last_signal = None
    last_key_level = None
    last_breakout_extreme = None

    # ============================================================
    # Walk through 5M candles
    # ============================================================

    for i in range(len(trading_df)):

        row = trading_df.iloc[i]

        close = float(row["close"])
        high = float(row["high"])
        low = float(row["low"])

        current_time = row["ny_time"]

        # --------------------------------------------------------
        # SHORT SETUP
        #
        # Break ABOVE range high
        # --------------------------------------------------------

        if not short_breakout:

            if close > range_high:

                short_breakout = True
                short_breakout_extreme = high
                short_breakout_time = current_time

        else:

            # Track highest high since breakout
            short_breakout_extreme = max(
                short_breakout_extreme,
                high
            )

            # Re-entry inside range
            if close < range_high:

                last_signal = "SELL"
                last_key_level = range_high
                last_breakout_extreme = short_breakout_extreme

                # Reset short setup after trade
                short_breakout = False
                short_breakout_extreme = None
                short_breakout_time = None

                # Only latest bar is actionable
                if i == len(trading_df) - 1:

                    entry = close
                    stop_loss = last_breakout_extreme
                    risk = stop_loss - entry

                    if risk > 0:

                        take_profit = entry - (
                            risk * RISK_REWARD
                        )

                        return (
                            last_signal,
                            last_key_level,
                            stop_loss,
                            take_profit,
                            {
                                "phase": "SHORT_ENTRY",
                                "range_high": round(range_high, 5),
                                "range_low": round(range_low, 5),
                                "breakout_time": str(short_breakout_time),
                                "entry_time": str(current_time),
                                "entry_price": round(entry, 5),
                                "breakout_extreme": round(
                                    last_breakout_extreme, 5
                                ),
                                "risk": round(risk, 5),
                            }
                        )

        # --------------------------------------------------------
        # LONG SETUP
        #
        # Break BELOW range low
        # --------------------------------------------------------

        if not long_breakout:

            if close < range_low:

                long_breakout = True
                long_breakout_extreme = low
                long_breakout_time = current_time

        else:

            # Track lowest low since breakout
            long_breakout_extreme = min(
                long_breakout_extreme,
                low
            )

            # Re-entry inside range
            if close > range_low:

                last_signal = "BUY"
                last_key_level = range_low
                last_breakout_extreme = long_breakout_extreme

                long_breakout = False
                long_breakout_extreme = None
                long_breakout_time = None

                # Only latest bar is actionable
                if i == len(trading_df) - 1:

                    entry = close
                    stop_loss = last_breakout_extreme
                    risk = entry - stop_loss

                    if risk > 0:

                        take_profit = entry + (
                            risk * RISK_REWARD
                        )

                        return (
                            last_signal,
                            last_key_level,
                            stop_loss,
                            take_profit,
                            {
                                "phase": "LONG_ENTRY",
                                "range_high": round(range_high, 5),
                                "range_low": round(range_low, 5),
                                "breakout_time": str(long_breakout_time),
                                "entry_time": str(current_time),
                                "entry_price": round(entry, 5),
                                "breakout_extreme": round(
                                    last_breakout_extreme, 5
                                ),
                                "risk": round(risk, 5),
                            }
                        )

    # ============================================================
    # No signal on latest candle
    # ============================================================

    phase = "WAITING"

    if short_breakout and long_breakout:
        phase = "BOTH_BREAKOUTS_ACTIVE"

    elif short_breakout:
        phase = "SHORT_BREAKOUT_ACTIVE"

    elif long_breakout:
        phase = "LONG_BREAKOUT_ACTIVE"

    else:
        phase = "WAITING_FOR_BREAKOUT"

    return (
        None,
        None,
        None,
        None,
        {
            "phase": phase,
            "range_high": round(range_high, 5),
            "range_low": round(range_low, 5),

            "short_breakout": short_breakout,
            "short_breakout_extreme": (
                round(short_breakout_extreme, 5)
                if short_breakout_extreme is not None
                else None
            ),

            "long_breakout": long_breakout,
            "long_breakout_extreme": (
                round(long_breakout_extreme, 5)
                if long_breakout_extreme is not None
                else None
            ),

            "range_start": str(range_start),
            "range_end": str(range_end),

            "latest_candle_ny": str(latest_time),

            "info": (
                "No re-entry signal on the latest 5M candle."
            )
        }
    )


# ================================================================
# API endpoint
# ================================================================

@app.post("/analyze")
def analyze(data: MarketData):

    df = pd.DataFrame(data.values)

    # ------------------------------------------------------------
    # Validate OHLC
    # ------------------------------------------------------------

    required_columns = [
        "open",
        "high",
        "low",
        "close"
    ]

    if not all(col in df.columns for col in required_columns):

        return {
            "error": (
                "Missing OHLC data. Required: "
                "open, high, low, close"
            )
        }

    # ------------------------------------------------------------
    # Timestamp required
    # ------------------------------------------------------------

    if "time" not in df.columns:

        return {
            "error": (
                "Missing 'time' field. "
                "Timestamp is required to identify "
                "the New York 4H range."
            )
        }

    if len(df) < 10:

        return {
            "error": "Not enough market data."
        }

    # ------------------------------------------------------------
    # Incoming data is newest-first
    # Flip it so oldest candle comes first.
    # ------------------------------------------------------------

    df = df.iloc[::-1].reset_index(drop=True)

    # ------------------------------------------------------------
    # Convert OHLC
    # ------------------------------------------------------------

    for col in required_columns:

        df[col] = pd.to_numeric(
            df[col],
            errors="coerce"
        )

    if df[required_columns].isna().any().any():

        return {
            "error": "Invalid OHLC values found."
        }

    # ------------------------------------------------------------
    # Run strategy
    # ------------------------------------------------------------

    (
        signal,
        key_level,
        stop_loss,
        take_profit,
        status
    ) = run_strategy(df)

    latest = df.iloc[-1]

    entry_price = float(latest["close"])

    # ------------------------------------------------------------
    # Base response
    # ------------------------------------------------------------

    response = {
        "symbol": data.symbol,
        "timeframe": data.timeframe,

        "entry_price": round(entry_price, 5),

        "signal": signal if signal else "NEUTRAL",

        "setup_type": (
            "NEW_YORK_RANGE_BREAKOUT_REENTRY"
            if signal
            else "NO_SETUP"
        ),

        "key_level": (
            round(key_level, 5)
            if key_level is not None
            else None
        ),

        "stop_loss": (
            round(stop_loss, 5)
            if stop_loss is not None
            else None
        ),

        "take_profit": (
            round(take_profit, 5)
            if take_profit is not None
            else None
        ),

        "risk_reward": (
            "1:2"
            if signal
            else None
        ),

        "status": status
    }

    return response


# ================================================================
# Health check
# ================================================================

@app.get("/")
def home():

    return {
        "message": (
            "New York 4H Range Breakout + "
            "5M Re-entry Strategy API running successfully"
        ),
        "timezone": "America/New_York",
        "range": "00:00 - 04:00 New York",
        "entry_timeframe": "5m",
        "risk_reward": "1:2"
    }
