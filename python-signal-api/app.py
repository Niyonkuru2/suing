from fastapi import FastAPI
from pydantic import BaseModel
import pandas as pd
from ta.trend import EMAIndicator
from ta.volatility import AverageTrueRange

app = FastAPI(title="EMA50 Breakout + Pullback Strategy API")


# ================================================================
# CONFIGURATION
# ================================================================

EMA_PERIOD = 50

# Minimum number of consecutive opposite candles required
MIN_PULLBACK_CANDLES = 2

# ATR settings
ATR_PERIOD = 14

# Small buffer beyond the pullback extreme for the stop loss.
# This prevents placing SL exactly on the obvious swing.
SL_ATR_BUFFER = 0.15

# How close price must come to the broken level to count as a retest.
# Example: 0.10 ATR means price can come within 10% of ATR of the level.
RETEST_ATR_TOLERANCE = 0.10

# Reward/risk
RISK_REWARD = 2.0


# ================================================================
# REQUEST MODEL
# ================================================================

class MarketData(BaseModel):
    values: list          # OHLC data, newest first
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
# CORE STRATEGY
# ================================================================

def run_strategy(df: pd.DataFrame):

    n = len(df)

    # ------------------------------------------------------------
    # BULLISH STATE
    #
    # IDLE
    # TRACKING_HIGH
    # PULLBACK
    # WAITING_FOR_RETEST
    # ------------------------------------------------------------

    bull_state = "IDLE"

    bull_swing_high = None
    bull_pullback_count = 0
    bull_pullback_low = None

    bull_breakout_level = None
    bull_breakout_index = None


    # ------------------------------------------------------------
    # BEARISH STATE
    # ------------------------------------------------------------

    bear_state = "IDLE"

    bear_swing_low = None
    bear_pullback_count = 0
    bear_pullback_high = None

    bear_breakout_level = None
    bear_breakout_index = None


    # ------------------------------------------------------------
    # LATEST SIGNAL
    # ------------------------------------------------------------

    last_signal = None
    last_key_level = None
    last_pullback_extreme = None
    last_entry_status = "NOT_READY"


    # ============================================================
    # WALK THROUGH CANDLES
    # ============================================================

    for i in range(1, n):

        prev_close = df["close"].iloc[i - 1]
        prev_ema = df["ema50"].iloc[i - 1]

        close = df["close"].iloc[i]
        ema = df["ema50"].iloc[i]

        high = df["high"].iloc[i]
        low = df["low"].iloc[i]

        row = df.iloc[i]

        atr = df["atr"].iloc[i]

        if pd.isna(atr) or atr <= 0:
            continue


        # --------------------------------------------------------
        # EMA CROSS
        # --------------------------------------------------------

        crossed_up = (
            prev_close <= prev_ema
            and close > ema
        )

        crossed_down = (
            prev_close >= prev_ema
            and close < ema
        )


        # ========================================================
        # BULLISH SETUP
        # ========================================================

        if crossed_up:

            # New bullish setup starts
            bull_state = "TRACKING_HIGH"

            bull_swing_high = high
            bull_pullback_count = 0
            bull_pullback_low = None

            bull_breakout_level = None
            bull_breakout_index = None

            # Cancel bearish setup
            bear_state = "IDLE"

            bear_swing_low = None
            bear_pullback_count = 0
            bear_pullback_high = None

            last_signal = None
            last_entry_status = "NOT_READY"


        # --------------------------------------------------------
        # BULLISH: TRACKING THE IMPULSE HIGH
        # --------------------------------------------------------

        elif bull_state == "TRACKING_HIGH":

            # Price continues making new highs.
            # Update the swing high.
            if high > bull_swing_high:

                bull_swing_high = high

                # Pullback hasn't started yet
                bull_pullback_count = 0
                bull_pullback_low = None


            # First / consecutive red candle
            elif is_red(row):

                bull_pullback_count += 1

                # IMPORTANT:
                # Track the actual LOW of the pullback.
                bull_pullback_low = (
                    low
                    if bull_pullback_low is None
                    else min(bull_pullback_low, low)
                )

                # Minimum pullback achieved
                if bull_pullback_count >= MIN_PULLBACK_CANDLES:

                    bull_state = "PULLBACK"


            # Green candle before minimum pullback
            else:

                bull_pullback_count = 0
                bull_pullback_low = None


            # Bullish setup invalidated if price closes below EMA
            if close < ema:

                bull_state = "IDLE"

                bull_swing_high = None
                bull_pullback_count = 0
                bull_pullback_low = None


        # --------------------------------------------------------
        # BULLISH: PULLBACK
        # --------------------------------------------------------

        elif bull_state == "PULLBACK":

            # IMPORTANT:
            # Track LOW on EVERY candle, regardless of candle color.
            if bull_pullback_low is None:
                bull_pullback_low = low
            else:
                bull_pullback_low = min(
                    bull_pullback_low,
                    low
                )


            # If price closes below EMA, setup is invalid.
            if close < ema:

                bull_state = "IDLE"

                bull_swing_high = None
                bull_pullback_count = 0
                bull_pullback_low = None

            # ----------------------------------------------------
            # BREAKOUT
            # ----------------------------------------------------
            elif close > bull_swing_high:

                # Breakout happened.
                # DO NOT BUY YET.
                #
                # We now wait for price to retest the broken level.
                bull_state = "WAITING_FOR_RETEST"

                bull_breakout_level = bull_swing_high
                bull_breakout_index = i


        # --------------------------------------------------------
        # BULLISH: WAITING FOR RETEST
        # --------------------------------------------------------

        elif bull_state == "WAITING_FOR_RETEST":

            # Continue tracking the original pullback low.
            if low < bull_pullback_low:
                bull_pullback_low = low


            # If price completely loses the EMA,
            # bullish setup is invalid.
            if close < ema:

                bull_state = "IDLE"

                bull_swing_high = None
                bull_pullback_count = 0
                bull_pullback_low = None
                bull_breakout_level = None
                bull_breakout_index = None

                continue


            # ----------------------------------------------------
            # STRUCTURAL INVALIDATION
            #
            # If price breaks below the original pullback low,
            # the bullish setup has failed.
            # ----------------------------------------------------

            if low < bull_pullback_low:

                bull_state = "IDLE"

                bull_swing_high = None
                bull_pullback_count = 0
                bull_pullback_low = None
                bull_breakout_level = None
                bull_breakout_index = None

                continue


            # ----------------------------------------------------
            # RETEST TOLERANCE
            # ----------------------------------------------------

            retest_tolerance = atr * RETEST_ATR_TOLERANCE

            retest_zone_low = (
                bull_breakout_level - retest_tolerance
            )

            retest_zone_high = (
                bull_breakout_level + retest_tolerance
            )


            # Price must actually come back toward
            # the broken resistance.
            touched_retest = (
                low <= retest_zone_high
                and high >= retest_zone_low
            )


            # ----------------------------------------------------
            # RETEST CONFIRMATION
            #
            # We want:
            #
            # 1. Price retests broken resistance
            # 2. Candle closes back above it
            # 3. Candle is bullish
            # ----------------------------------------------------

            bullish_rejection = (
                touched_retest
                and close > bull_breakout_level
                and is_green(row)
            )


            if bullish_rejection:

                last_signal = "BUY_TREND"
                last_key_level = bull_breakout_level
                last_pullback_extreme = bull_pullback_low
                last_entry_status = "READY"

                # Reset after confirmed entry
                bull_state = "IDLE"

            else:

                last_entry_status = "WAITING_FOR_RETEST"


        # ========================================================
        # BEARISH SETUP
        # ========================================================

        if crossed_down:

            bear_state = "TRACKING_LOW"

            bear_swing_low = low
            bear_pullback_count = 0
            bear_pullback_high = None

            bear_breakout_level = None
            bear_breakout_index = None

            # Cancel bullish setup
            bull_state = "IDLE"

            bull_swing_high = None
            bull_pullback_count = 0
            bull_pullback_low = None

            last_signal = None
            last_entry_status = "NOT_READY"


        # --------------------------------------------------------
        # BEARISH: TRACKING IMPULSE LOW
        # --------------------------------------------------------

        elif bear_state == "TRACKING_LOW":

            if low < bear_swing_low:

                bear_swing_low = low

                bear_pullback_count = 0
                bear_pullback_high = None


            elif is_green(row):

                bear_pullback_count += 1

                # Track actual HIGH
                bear_pullback_high = (
                    high
                    if bear_pullback_high is None
                    else max(
                        bear_pullback_high,
                        high
                    )
                )

                if bear_pullback_count >= MIN_PULLBACK_CANDLES:

                    bear_state = "PULLBACK"


            else:

                bear_pullback_count = 0
                bear_pullback_high = None


            # Bearish setup invalidated
            if close > ema:

                bear_state = "IDLE"

                bear_swing_low = None
                bear_pullback_count = 0
                bear_pullback_high = None


        # --------------------------------------------------------
        # BEARISH: PULLBACK
        # --------------------------------------------------------

        elif bear_state == "PULLBACK":

            # Track HIGH of every candle.
            if bear_pullback_high is None:
                bear_pullback_high = high
            else:
                bear_pullback_high = max(
                    bear_pullback_high,
                    high
                )


            # Invalidated if price closes above EMA
            if close > ema:

                bear_state = "IDLE"

                bear_swing_low = None
                bear_pullback_count = 0
                bear_pullback_high = None

            # ----------------------------------------------------
            # BREAKDOWN
            # ----------------------------------------------------

            elif close < bear_swing_low:

                # Breakdown happened.
                # DO NOT SELL YET.
                #
                # Wait for retest of broken support.
                bear_state = "WAITING_FOR_RETEST"

                bear_breakout_level = bear_swing_low
                bear_breakout_index = i


        # --------------------------------------------------------
        # BEARISH: WAITING FOR RETEST
        # --------------------------------------------------------

        elif bear_state == "WAITING_FOR_RETEST":

            # Continue tracking actual pullback high
            if high > bear_pullback_high:
                bear_pullback_high = high


            # EMA invalidation
            if close > ema:

                bear_state = "IDLE"

                bear_swing_low = None
                bear_pullback_count = 0
                bear_pullback_high = None
                bear_breakout_level = None
                bear_breakout_index = None

                continue


            # ----------------------------------------------------
            # STRUCTURAL INVALIDATION
            # ----------------------------------------------------

            if high > bear_pullback_high:

                bear_state = "IDLE"

                bear_swing_low = None
                bear_pullback_count = 0
                bear_pullback_high = None
                bear_breakout_level = None
                bear_breakout_index = None

                continue


            # ----------------------------------------------------
            # RETEST TOLERANCE
            # ----------------------------------------------------

            retest_tolerance = atr * RETEST_ATR_TOLERANCE

            retest_zone_low = (
                bear_breakout_level - retest_tolerance
            )

            retest_zone_high = (
                bear_breakout_level + retest_tolerance
            )


            touched_retest = (
                high >= retest_zone_low
                and low <= retest_zone_high
            )


            # ----------------------------------------------------
            # BEARISH RETEST CONFIRMATION
            # ----------------------------------------------------

            bearish_rejection = (
                touched_retest
                and close < bear_breakout_level
                and is_red(row)
            )


            if bearish_rejection:

                last_signal = "SELL_TREND"
                last_key_level = bear_breakout_level
                last_pullback_extreme = bear_pullback_high
                last_entry_status = "READY"

                bear_state = "IDLE"

            else:

                last_entry_status = "WAITING_FOR_RETEST"


        # ========================================================
        # IMPORTANT:
        #
        # We ONLY keep a signal from the FINAL candle.
        # ========================================================

        if i < n - 1:

            last_signal = None
            last_key_level = None
            last_pullback_extreme = None


    # ============================================================
    # STATUS
    # ============================================================

    status = {

        "bull_phase": bull_state,

        "bull_pullback_candles": bull_pullback_count,

        "bull_swing_high": (
            round(bull_swing_high, 5)
            if bull_swing_high is not None
            else None
        ),

        "bull_pullback_low": (
            round(bull_pullback_low, 5)
            if bull_pullback_low is not None
            else None
        ),

        "bear_phase": bear_state,

        "bear_pullback_candles": bear_pullback_count,

        "bear_swing_low": (
            round(bear_swing_low, 5)
            if bear_swing_low is not None
            else None
        ),

        "bear_pullback_high": (
            round(bear_pullback_high, 5)
            if bear_pullback_high is not None
            else None
        ),

        "entry_status": last_entry_status,
    }


    return (
        last_signal,
        last_key_level,
        last_pullback_extreme,
        status
    )


# ================================================================
# ANALYZE ENDPOINT
# ================================================================

@app.post("/analyze")
def analyze(data: MarketData):

    df = pd.DataFrame(data.values)


    # ------------------------------------------------------------
    # VALIDATE OHLC
    # ------------------------------------------------------------

    required_columns = [
        "open",
        "high",
        "low",
        "close"
    ]

    if not all(
        col in df.columns
        for col in required_columns
    ):

        return {
            "error": "Missing OHLC data"
        }


    if len(df) < 100:

        return {
            "error": (
                "Not enough data. "
                "Need at least 100 candles."
            )
        }


    # ------------------------------------------------------------
    # DATA IS NEWEST FIRST
    #
    # Reverse so oldest candle is first.
    # ------------------------------------------------------------

    df = (
        df.iloc[::-1]
        .reset_index(drop=True)
    )


    # ------------------------------------------------------------
    # CONVERT OHLC TO FLOAT
    # ------------------------------------------------------------

    for col in required_columns:

        df[col] = pd.to_numeric(
            df[col],
            errors="coerce"
        )


    # Remove invalid rows
    df = df.dropna(
        subset=required_columns
    ).reset_index(drop=True)


    # ------------------------------------------------------------
    # EMA 50
    # ------------------------------------------------------------

    df["ema50"] = EMAIndicator(
        close=df["close"],
        window=EMA_PERIOD
    ).ema_indicator()


    # ------------------------------------------------------------
    # ATR
    # ------------------------------------------------------------

    atr_indicator = AverageTrueRange(
        high=df["high"],
        low=df["low"],
        close=df["close"],
        window=ATR_PERIOD
    )

    df["atr"] = atr_indicator.average_true_range()


    # Remove indicator warm-up rows
    df = df.dropna(
        subset=["ema50", "atr"]
    ).reset_index(drop=True)


    if len(df) < 10:

        return {
            "error": (
                "Not enough data after "
                "EMA50/ATR warm-up."
            )
        }


    # ============================================================
    # RUN STRATEGY
    # ============================================================

    latest = df.iloc[-1]

    (
        signal,
        key_level,
        pullback_extreme,
        status
    ) = run_strategy(df)


    # ============================================================
    # DEFAULT RESPONSE
    #
    # IMPORTANT:
    #
    # signal is NEVER BUY/SELL unless
    # entry_status == READY.
    # ============================================================

    base_response = {

        "symbol": data.symbol,

        "timeframe": data.timeframe,

        "entry_price": round(
            latest["close"],
            5
        ),

        "ema50": round(
            latest["ema50"],
            5
        ),

        "atr": round(
            latest["atr"],
            5
        ),

        "entry_status": "NOT_READY",

        "signal": "NEUTRAL",

        "setup_type": "NO_SETUP",

        "key_level": None,

        "stop_loss": None,

        "take_profit": None,

        "risk_reward": None,

        "status": status,
    }


    # ============================================================
    # BUY ENTRY
    # ============================================================

    if (
        signal == "BUY_TREND"
        and status["entry_status"] == "READY"
        and key_level is not None
        and pullback_extreme is not None
    ):

        entry_price = float(
            latest["close"]
        )

        atr = float(
            latest["atr"]
        )

        # SL goes below the REAL pullback low
        # with a small ATR buffer.
        stop_loss = (
            float(pullback_extreme)
            - (atr * SL_ATR_BUFFER)
        )

        risk = (
            entry_price
            - stop_loss
        )


        # Safety check
        if risk > 0:

            take_profit = (
                entry_price
                + (risk * RISK_REWARD)
            )


            base_response.update({

                "entry_status": "READY",

                "signal": "BUY",

                "setup_type":
                    "BREAKOUT_PULLBACK_RETEST_BUY",

                "entry_price":
                    round(entry_price, 5),

                "key_level":
                    round(float(key_level), 5),

                "pullback_extreme":
                    round(float(pullback_extreme), 5),

                "stop_loss":
                    round(stop_loss, 5),

                "take_profit":
                    round(take_profit, 5),

                "risk_reward":
                    "1:2",

                "info":
                    (
                        "BUY confirmed after bullish "
                        "breakout + retest + rejection."
                    ),
            })


    # ============================================================
    # SELL ENTRY
    # ============================================================

    elif (
        signal == "SELL_TREND"
        and status["entry_status"] == "READY"
        and key_level is not None
        and pullback_extreme is not None
    ):

        entry_price = float(
            latest["close"]
        )

        atr = float(
            latest["atr"]
        )

        # SL goes above REAL pullback high
        # with ATR buffer.
        stop_loss = (
            float(pullback_extreme)
            + (atr * SL_ATR_BUFFER)
        )

        risk = (
            stop_loss
            - entry_price
        )


        # Safety check
        if risk > 0:

            take_profit = (
                entry_price
                - (risk * RISK_REWARD)
            )


            base_response.update({

                "entry_status": "READY",

                "signal": "SELL",

                "setup_type":
                    "BREAKOUT_PULLBACK_RETEST_SELL",

                "entry_price":
                    round(entry_price, 5),

                "key_level":
                    round(float(key_level), 5),

                "pullback_extreme":
                    round(float(pullback_extreme), 5),

                "stop_loss":
                    round(stop_loss, 5),

                "take_profit":
                    round(take_profit, 5),

                "risk_reward":
                    "1:2",

                "info":
                    (
                        "SELL confirmed after bearish "
                        "breakdown + retest + rejection."
                    ),
            })


    # ============================================================
    # NOT READY
    #
    # Even if there is a setup, DO NOT output BUY/SELL.
    # ============================================================

    else:

        if status["bull_phase"] == "WAITING_FOR_RETEST":

            base_response["entry_status"] = (
                "WAITING_FOR_RETEST"
            )

            base_response["setup_type"] = (
                "BREAKOUT_PULLBACK_BUY_WAIT"
            )

            base_response["key_level"] = (
                round(
                    status["bull_swing_high"],
                    5
                )
                if status["bull_swing_high"]
                is not None
                else None
            )

            base_response["info"] = (
                "Bullish breakout detected. "
                "Wait for price to retest the "
                "broken level and close bullish."
            )


        elif status["bear_phase"] == "WAITING_FOR_RETEST":

            base_response["entry_status"] = (
                "WAITING_FOR_RETEST"
            )

            base_response["setup_type"] = (
                "BREAKOUT_PULLBACK_SELL_WAIT"
            )

            base_response["key_level"] = (
                round(
                    status["bear_swing_low"],
                    5
                )
                if status["bear_swing_low"]
                is not None
                else None
            )

            base_response["info"] = (
                "Bearish breakdown detected. "
                "Wait for price to retest the "
                "broken level and close bearish."
            )


        elif status["bull_phase"] == "PULLBACK":

            base_response["entry_status"] = (
                "WAITING_FOR_BREAKOUT"
            )

            base_response["setup_type"] = (
                "BULLISH_PULLBACK"
            )

            base_response["key_level"] = (
                round(
                    status["bull_swing_high"],
                    5
                )
                if status["bull_swing_high"]
                is not None
                else None
            )

            base_response["info"] = (
                "Bullish pullback confirmed. "
                "Wait for a close above the "
                "swing high."
            )


        elif status["bear_phase"] == "PULLBACK":

            base_response["entry_status"] = (
                "WAITING_FOR_BREAKDOWN"
            )

            base_response["setup_type"] = (
                "BEARISH_PULLBACK"
            )

            base_response["key_level"] = (
                round(
                    status["bear_swing_low"],
                    5
                )
                if status["bear_swing_low"]
                is not None
                else None
            )

            base_response["info"] = (
                "Bearish pullback confirmed. "
                "Wait for a close below the "
                "swing low."
            )


        elif status["bull_phase"] == "TRACKING_HIGH":

            base_response["entry_status"] = (
                "WAITING_FOR_PULLBACK"
            )

            base_response["setup_type"] = (
                "BULLISH_TREND_TRACKING"
            )

            base_response["info"] = (
                "Bullish EMA50 breakout detected. "
                "Waiting for at least 2 red "
                "pullback candles."
            )


        elif status["bear_phase"] == "TRACKING_LOW":

            base_response["entry_status"] = (
                "WAITING_FOR_PULLBACK"
            )

            base_response["setup_type"] = (
                "BEARISH_TREND_TRACKING"
            )

            base_response["info"] = (
                "Bearish EMA50 breakdown detected. "
                "Waiting for at least 2 green "
                "pullback candles."
            )


        else:

            base_response["entry_status"] = (
                "NOT_READY"
            )

            base_response["info"] = (
                "No valid entry setup on "
                "the latest candle."
            )


    return base_response


# ================================================================
# HEALTH CHECK
# ================================================================

@app.get("/")
def home():

    return {
        "message":
            "EMA50 Breakout + Pullback Strategy API "
            "running successfully"
    }
