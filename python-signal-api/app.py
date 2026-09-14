from fastapi import FastAPI
from pydantic import BaseModel
import pandas as pd
from ta.trend import EMAIndicator
from ta.volatility import AverageTrueRange


app = FastAPI(
    title="50 EMA Pullback Analysis Strategy API"
)


# ================================================================
# CONFIGURATION
# ================================================================

EMA_PERIOD = 50
ATR_PERIOD = 14


# ------------------------------------------------
# Pullback requirements
# ------------------------------------------------

MIN_PULLBACK_CANDLES = 2
MAX_PULLBACK_CANDLES = 12


# ------------------------------------------------
# EMA interaction
#
# Example:
# 0.30 ATR means price can come within
# 0.30 ATR of EMA50.
# ------------------------------------------------

EMA_TOUCH_ATR_TOLERANCE = 0.30


# ------------------------------------------------
# Pullback depth
#
# These are not mandatory Fibonacci levels.
# They are measurements used to classify
# the quality of the pullback.
# ------------------------------------------------

MIN_PULLBACK_RETRACE = 0.20
MAX_PULLBACK_RETRACE = 0.786


# ------------------------------------------------
# Minimum impulse size
#
# Prevents tiny random movements from being
# considered an impulse.
# ------------------------------------------------

MIN_IMPULSE_ATR = 0.50


# ------------------------------------------------
# EMA slope
#
# EMA must move at least this many ATR fractions
# over the slope lookback to be considered
# directional.
# ------------------------------------------------

EMA_SLOPE_LOOKBACK = 5
MIN_EMA_SLOPE_ATR = 0.02


# ------------------------------------------------
# Stop loss
# ------------------------------------------------

SL_ATR_BUFFER = 0.15


# ------------------------------------------------
# Reward / Risk
# ------------------------------------------------

RISK_REWARD = 2.0


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

def is_green(row):

    return row["close"] > row["open"]


def is_red(row):

    return row["close"] < row["open"]


# ================================================================
# TREND DETECTION
# ================================================================

def get_trend(df, i):

    """
    Determine the directional environment using:

    1. Price relative to EMA50
    2. EMA50 slope

    Returns:

        BULL
        BEAR
        NEUTRAL
    """

    if i < EMA_SLOPE_LOOKBACK:

        return "NEUTRAL"


    close = float(df["close"].iloc[i])
    ema = float(df["ema50"].iloc[i])
    atr = float(df["atr"].iloc[i])

    previous_ema = float(
        df["ema50"].iloc[
            i - EMA_SLOPE_LOOKBACK
        ]
    )


    if pd.isna(ema) or pd.isna(atr) or atr <= 0:

        return "NEUTRAL"


    ema_slope = ema - previous_ema

    minimum_slope = (
        atr * MIN_EMA_SLOPE_ATR
    )


    # ------------------------------------------------
    # Bullish environment
    # ------------------------------------------------

    if (
        close > ema
        and ema_slope >= minimum_slope
    ):

        return "BULL"


    # ------------------------------------------------
    # Bearish environment
    # ------------------------------------------------

    if (
        close < ema
        and ema_slope <= -minimum_slope
    ):

        return "BEAR"


    return "NEUTRAL"


# ================================================================
# PULLBACK QUALITY
# ================================================================

def calculate_pullback_measurement(
    impulse_start,
    impulse_extreme,
    pullback_extreme,
    direction
):

    """
    Measures how deeply price has pulled back
    relative to the impulse.

    BUY:

        impulse_start = swing low
        impulse_extreme = impulse high
        pullback_extreme = pullback low

    SELL:

        impulse_start = swing high
        impulse_extreme = impulse low
        pullback_extreme = pullback high
    """

    if direction == "BULL":

        impulse_range = (
            impulse_extreme
            - impulse_start
        )

        pullback_distance = (
            impulse_extreme
            - pullback_extreme
        )


    else:

        impulse_range = (
            impulse_start
            - impulse_extreme
        )

        pullback_distance = (
            pullback_extreme
            - impulse_extreme
        )


    if impulse_range <= 0:

        return None


    retracement = (
        pullback_distance
        / impulse_range
    )


    return retracement


# ================================================================
# EMA PROXIMITY
# ================================================================

def is_near_ema(
    price,
    ema,
    atr
):

    if atr <= 0:

        return False


    distance = abs(
        price - ema
    )


    return (
        distance
        <= atr * EMA_TOUCH_ATR_TOLERANCE
    )


# ================================================================
# CONFIRMATION CANDLE
# ================================================================

def bullish_confirmation(row):

    """
    Basic bullish rejection:

    - Green candle
    - Close above open
    - Close in upper portion of candle
    """

    candle_range = (
        row["high"]
        - row["low"]
    )


    if candle_range <= 0:

        return False


    close_position = (
        row["close"]
        - row["low"]
    ) / candle_range


    return (
        is_green(row)
        and close_position >= 0.60
    )


def bearish_confirmation(row):

    """
    Basic bearish rejection:

    - Red candle
    - Close below open
    - Close in lower portion of candle
    """

    candle_range = (
        row["high"]
        - row["low"]
    )


    if candle_range <= 0:

        return False


    close_position = (
        row["high"]
        - row["close"]
    ) / candle_range


    return (
        is_red(row)
        and close_position >= 0.60
    )


# ================================================================
# MAIN STRATEGY
# ================================================================

def run_pullback_strategy(df):

    n = len(df)


    # ============================================================
    # BULLISH STATE
    # ============================================================

    bull_state = "IDLE"

    bull_impulse_start = None
    bull_impulse_high = None
    bull_pullback_low = None

    bull_impulse_start_index = None
    bull_impulse_high_index = None
    bull_pullback_start_index = None

    bull_pullback_count = 0


    # ============================================================
    # BEARISH STATE
    # ============================================================

    bear_state = "IDLE"

    bear_impulse_start = None
    bear_impulse_low = None
    bear_pullback_high = None

    bear_impulse_start_index = None
    bear_impulse_low_index = None
    bear_pullback_start_index = None

    bear_pullback_count = 0


    # ============================================================
    # FINAL SIGNAL
    # ============================================================

    signal = None

    key_level = None

    pullback_extreme = None

    entry_status = "NOT_READY"

    setup_type = "NO_SETUP"

    analysis = {}


    # ============================================================
    # PROCESS CANDLES
    # ============================================================

    for i in range(
        EMA_SLOPE_LOOKBACK,
        n
    ):

        row = df.iloc[i]

        close = float(row["close"])
        high = float(row["high"])
        low = float(row["low"])

        ema = float(row["ema50"])
        atr = float(row["atr"])


        if (
            pd.isna(ema)
            or pd.isna(atr)
            or atr <= 0
        ):

            continue


        trend = get_trend(
            df,
            i
        )


        # ========================================================
        # BULLISH ENVIRONMENT
        # ========================================================

        if trend == "BULL":

            # ----------------------------------------------------
            # Cancel bearish setup
            # ----------------------------------------------------

            bear_state = "IDLE"

            bear_impulse_start = None
            bear_impulse_low = None
            bear_pullback_high = None

            bear_pullback_count = 0


            # ----------------------------------------------------
            # START BULLISH IMPULSE
            # ----------------------------------------------------

            if bull_state == "IDLE":

                bull_state = "IMPULSE"

                bull_impulse_start = low

                bull_impulse_high = high

                bull_impulse_start_index = i

                bull_impulse_high_index = i

                bull_pullback_low = None

                bull_pullback_count = 0


                entry_status = (
                    "WAITING_FOR_IMPULSE"
                )

                setup_type = (
                    "BULLISH_TREND"
                )


            # ====================================================
            # TRACK BULLISH IMPULSE
            # ====================================================

            if bull_state == "IMPULSE":

                # -----------------------------------------------
                # New high = impulse continues
                # -----------------------------------------------

                if high >= bull_impulse_high:

                    bull_impulse_high = high

                    bull_impulse_high_index = i

                    bull_pullback_count = 0

                    bull_pullback_low = None


                # -----------------------------------------------
                # Red candle = possible pullback
                # -----------------------------------------------

                elif is_red(row):

                    bull_pullback_count += 1

                    if bull_pullback_low is None:

                        bull_pullback_low = low

                        bull_pullback_start_index = i

                    else:

                        bull_pullback_low = min(
                            bull_pullback_low,
                            low
                        )


                    # -------------------------------------------
                    # Check impulse size
                    # -------------------------------------------

                    impulse_size = (
                        bull_impulse_high
                        - bull_impulse_start
                    )


                    impulse_is_large_enough = (
                        impulse_size
                        >= atr * MIN_IMPULSE_ATR
                    )


                    if (
                        bull_pullback_count
                        >= MIN_PULLBACK_CANDLES
                        and impulse_is_large_enough
                    ):

                        bull_state = "PULLBACK"

                        entry_status = (
                            "PULLBACK_DETECTED"
                        )

                        setup_type = (
                            "BULLISH_PULLBACK"
                        )


                else:

                    # Green candle during impulse
                    # means momentum continues.

                    bull_pullback_count = 0

                    bull_pullback_low = None


            # ====================================================
            # BULLISH PULLBACK
            # ====================================================

            if bull_state == "PULLBACK":

                # ------------------------------------------------
                # Track REAL pullback low
                # ------------------------------------------------

                bull_pullback_low = min(
                    bull_pullback_low,
                    low
                )


                bull_pullback_count += 1


                # ------------------------------------------------
                # Calculate retracement
                # ------------------------------------------------

                retracement = (
                    calculate_pullback_measurement(
                        bull_impulse_start,
                        bull_impulse_high,
                        bull_pullback_low,
                        "BULL"
                    )
                )


                if retracement is None:

                    continue


                # ------------------------------------------------
                # Distance to EMA50
                # ------------------------------------------------

                ema_distance = abs(
                    bull_pullback_low
                    - ema
                )


                ema_distance_atr = (
                    ema_distance / atr
                )


                near_ema = is_near_ema(
                    bull_pullback_low,
                    ema,
                    atr
                )


                # ------------------------------------------------
                # Pullback too deep
                # ------------------------------------------------

                if (
                    retracement
                    > MAX_PULLBACK_RETRACE
                ):

                    bull_state = "IDLE"

                    bull_pullback_count = 0

                    continue


                # ------------------------------------------------
                # Structure invalidation
                #
                # Pullback cannot break the original
                # impulse starting point.
                # ------------------------------------------------

                if (
                    bull_pullback_low
                    <= bull_impulse_start
                ):

                    bull_state = "IDLE"

                    bull_pullback_count = 0

                    continue


                # ------------------------------------------------
                # Need EMA interaction
                # ------------------------------------------------

                if near_ema:

                    entry_status = (
                        "WAITING_FOR_CONFIRMATION"
                    )

                    setup_type = (
                        "BULLISH_PULLBACK_AT_EMA50"
                    )


                # ------------------------------------------------
                # Confirmation
                #
                # We require:
                #
                # 1. Pullback has reached EMA zone
                # 2. Current candle is bullish
                # 3. Close is above EMA
                # 4. Pullback is within acceptable depth
                # ------------------------------------------------

                confirmation = (
                    near_ema
                    and bullish_confirmation(row)
                    and close > ema
                    and retracement >= MIN_PULLBACK_RETRACE
                )


                if confirmation:

                    signal = "BUY"

                    key_level = ema

                    pullback_extreme = (
                        bull_pullback_low
                    )

                    entry_status = "READY"

                    setup_type = (
                        "EMA50_PULLBACK_BUY"
                    )


                    analysis = {

                        "trend": "BULL",

                        "impulse_start":
                            round(
                                bull_impulse_start,
                                5
                            ),

                        "impulse_high":
                            round(
                                bull_impulse_high,
                                5
                            ),

                        "pullback_low":
                            round(
                                bull_pullback_low,
                                5
                            ),

                        "pullback_candles":
                            bull_pullback_count,

                        "pullback_retracement":
                            round(
                                retracement * 100,
                                2
                            ),

                        "ema_distance_atr":
                            round(
                                ema_distance_atr,
                                3
                            ),

                        "ema50_touched":
                            True,

                        "confirmation":
                            "BULLISH_REJECTION",

                    }


                    # -------------------------------------------
                    # Reset
                    # -------------------------------------------

                    bull_state = "IDLE"

                    bull_pullback_count = 0


                else:

                    # Still waiting

                    if near_ema:

                        entry_status = (
                            "WAITING_FOR_CONFIRMATION"
                        )


                    else:

                        entry_status = (
                            "WAITING_FOR_EMA_PULLBACK"
                        )


        # ========================================================
        # BEARISH ENVIRONMENT
        # ========================================================

        elif trend == "BEAR":

            # ----------------------------------------------------
            # Cancel bullish setup
            # ----------------------------------------------------

            bull_state = "IDLE"

            bull_impulse_start = None
            bull_impulse_high = None
            bull_pullback_low = None

            bull_pullback_count = 0


            # ----------------------------------------------------
            # Start bearish impulse
            # ----------------------------------------------------

            if bear_state == "IDLE":

                bear_state = "IMPULSE"

                bear_impulse_start = high

                bear_impulse_low = low

                bear_impulse_start_index = i

                bear_impulse_low_index = i

                bear_pullback_high = None

                bear_pullback_count = 0


                entry_status = (
                    "WAITING_FOR_IMPULSE"
                )

                setup_type = (
                    "BEARISH_TREND"
                )


            # ====================================================
            # TRACK BEARISH IMPULSE
            # ====================================================

            if bear_state == "IMPULSE":

                # -----------------------------------------------
                # New low = impulse continues
                # -----------------------------------------------

                if low <= bear_impulse_low:

                    bear_impulse_low = low

                    bear_impulse_low_index = i

                    bear_pullback_count = 0

                    bear_pullback_high = None


                # -----------------------------------------------
                # Green candle = possible pullback
                # -----------------------------------------------

                elif is_green(row):

                    bear_pullback_count += 1

                    if bear_pullback_high is None:

                        bear_pullback_high = high

                        bear_pullback_start_index = i

                    else:

                        bear_pullback_high = max(
                            bear_pullback_high,
                            high
                        )


                    impulse_size = (
                        bear_impulse_start
                        - bear_impulse_low
                    )


                    impulse_is_large_enough = (
                        impulse_size
                        >= atr * MIN_IMPULSE_ATR
                    )


                    if (
                        bear_pullback_count
                        >= MIN_PULLBACK_CANDLES
                        and impulse_is_large_enough
                    ):

                        bear_state = "PULLBACK"

                        entry_status = (
                            "PULLBACK_DETECTED"
                        )

                        setup_type = (
                            "BEARISH_PULLBACK"
                        )


                else:

                    bear_pullback_count = 0

                    bear_pullback_high = None


            # ====================================================
            # BEARISH PULLBACK
            # ====================================================

            if bear_state == "PULLBACK":

                # ------------------------------------------------
                # Track REAL pullback high
                # ------------------------------------------------

                bear_pullback_high = max(
                    bear_pullback_high,
                    high
                )


                bear_pullback_count += 1


                # ------------------------------------------------
                # Calculate retracement
                # ------------------------------------------------

                retracement = (
                    calculate_pullback_measurement(
                        bear_impulse_start,
                        bear_impulse_low,
                        bear_pullback_high,
                        "BEAR"
                    )
                )


                if retracement is None:

                    continue


                # ------------------------------------------------
                # EMA distance
                # ------------------------------------------------

                ema_distance = abs(
                    bear_pullback_high
                    - ema
                )


                ema_distance_atr = (
                    ema_distance / atr
                )


                near_ema = is_near_ema(
                    bear_pullback_high,
                    ema,
                    atr
                )


                # ------------------------------------------------
                # Pullback too deep
                # ------------------------------------------------

                if (
                    retracement
                    > MAX_PULLBACK_RETRACE
                ):

                    bear_state = "IDLE"

                    bear_pullback_count = 0

                    continue


                # ------------------------------------------------
                # Structure invalidation
                # ------------------------------------------------

                if (
                    bear_pullback_high
                    >= bear_impulse_start
                ):

                    bear_state = "IDLE"

                    bear_pullback_count = 0

                    continue


                # ------------------------------------------------
                # EMA reached
                # ------------------------------------------------

                if near_ema:

                    entry_status = (
                        "WAITING_FOR_CONFIRMATION"
                    )

                    setup_type = (
                        "BEARISH_PULLBACK_AT_EMA50"
                    )


                # ------------------------------------------------
                # Confirmation
                # ------------------------------------------------

                confirmation = (
                    near_ema
                    and bearish_confirmation(row)
                    and close < ema
                    and retracement >= MIN_PULLBACK_RETRACE
                )


                if confirmation:

                    signal = "SELL"

                    key_level = ema

                    pullback_extreme = (
                        bear_pullback_high
                    )

                    entry_status = "READY"

                    setup_type = (
                        "EMA50_PULLBACK_SELL"
                    )


                    analysis = {

                        "trend": "BEAR",

                        "impulse_start":
                            round(
                                bear_impulse_start,
                                5
                            ),

                        "impulse_low":
                            round(
                                bear_impulse_low,
                                5
                            ),

                        "pullback_high":
                            round(
                                bear_pullback_high,
                                5
                            ),

                        "pullback_candles":
                            bear_pullback_count,

                        "pullback_retracement":
                            round(
                                retracement * 100,
                                2
                            ),

                        "ema_distance_atr":
                            round(
                                ema_distance_atr,
                                3
                            ),

                        "ema50_touched":
                            True,

                        "confirmation":
                            "BEARISH_REJECTION",

                    }


                    bear_state = "IDLE"

                    bear_pullback_count = 0


                else:

                    if near_ema:

                        entry_status = (
                            "WAITING_FOR_CONFIRMATION"
                        )

                    else:

                        entry_status = (
                            "WAITING_FOR_EMA_PULLBACK"
                        )


        # ========================================================
        # NEUTRAL
        # ========================================================

        else:

            # Don't immediately destroy everything.
            # A temporary neutral candle is allowed.

            if bull_state == "PULLBACK":

                entry_status = (
                    "PULLBACK_ACTIVE"
                )

            elif bear_state == "PULLBACK":

                entry_status = (
                    "PULLBACK_ACTIVE"
                )


    # ============================================================
    # STATUS OBJECT
    # ============================================================

    status = {

        "bull_phase":
            bull_state,

        "bull_impulse_start":
            round(
                bull_impulse_start,
                5
            )
            if bull_impulse_start is not None
            else None,

        "bull_impulse_high":
            round(
                bull_impulse_high,
                5
            )
            if bull_impulse_high is not None
            else None,

        "bull_pullback_low":
            round(
                bull_pullback_low,
                5
            )
            if bull_pullback_low is not None
            else None,

        "bull_pullback_candles":
            bull_pullback_count,


        "bear_phase":
            bear_state,

        "bear_impulse_start":
            round(
                bear_impulse_start,
                5
            )
            if bear_impulse_start is not None
            else None,

        "bear_impulse_low":
            round(
                bear_impulse_low,
                5
            )
            if bear_impulse_low is not None
            else None,

        "bear_pullback_high":
            round(
                bear_pullback_high,
                5
            )
            if bear_pullback_high is not None
            else None,

        "bear_pullback_candles":
            bear_pullback_count,


        "entry_status":
            entry_status,

    }


    return (
        signal,
        key_level,
        pullback_extreme,
        setup_type,
        analysis,
        status
    )


# ================================================================
# ANALYZE ENDPOINT
# ================================================================

@app.post("/analyze")
def analyze(data: MarketData):

    df = pd.DataFrame(
        data.values
    )


    # ============================================================
    # VALIDATE
    # ============================================================

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


    # ============================================================
    # NEWEST FIRST → OLDEST FIRST
    # ============================================================

    df = (
        df.iloc[::-1]
        .reset_index(drop=True)
    )


    # ============================================================
    # CONVERT OHLC
    # ============================================================

    for col in required_columns:

        df[col] = pd.to_numeric(
            df[col],
            errors="coerce"
        )


    df = df.dropna(
        subset=required_columns
    ).reset_index(drop=True)


    # ============================================================
    # EMA50
    # ============================================================

    df["ema50"] = EMAIndicator(
        close=df["close"],
        window=EMA_PERIOD
    ).ema_indicator()


    # ============================================================
    # ATR14
    # ============================================================

    atr_indicator = AverageTrueRange(
        high=df["high"],
        low=df["low"],
        close=df["close"],
        window=ATR_PERIOD
    )


    df["atr"] = (
        atr_indicator
        .average_true_range()
    )


    # ============================================================
    # REMOVE WARMUP
    # ============================================================

    df = df.dropna(
        subset=[
            "ema50",
            "atr"
        ]
    ).reset_index(drop=True)


    if len(df) < 20:

        return {
            "error": (
                "Not enough data after "
                "indicator warm-up."
            )
        }


    # ============================================================
    # RUN STRATEGY
    # ============================================================

    (
        signal,
        key_level,
        pullback_extreme,
        setup_type,
        analysis,
        status
    ) = run_pullback_strategy(df)


    latest = df.iloc[-1]


    entry_price = float(
        latest["close"]
    )

    ema50 = float(
        latest["ema50"]
    )

    atr = float(
        latest["atr"]
    )


    # ============================================================
    # DEFAULT RESPONSE
    # ============================================================

    response = {

        "symbol":
            data.symbol,

        "timeframe":
            data.timeframe,

        "entry_price":
            round(
                entry_price,
                5
            ),

        "ema50":
            round(
                ema50,
                5
            ),

        "atr":
            round(
                atr,
                5
            ),

        "signal":
            "NEUTRAL",

        "entry_status":
            status["entry_status"],

        "setup_type":
            setup_type,

        "key_level":
            round(
                float(key_level),
                5
            )
            if key_level is not None
            else None,

        "pullback_extreme":
            round(
                float(pullback_extreme),
                5
            )
            if pullback_extreme is not None
            else None,

        "stop_loss":
            None,

        "take_profit":
            None,

        "risk_reward":
            None,

        "pullback_analysis":
            analysis,

        "status":
            status,
    }


    # ============================================================
    # BUY
    # ============================================================

    if (
        signal == "BUY"
        and pullback_extreme is not None
    ):

        stop_loss = (
            pullback_extreme
            - (
                atr
                * SL_ATR_BUFFER
            )
        )


        risk = (
            entry_price
            - stop_loss
        )


        if risk > 0:

            take_profit = (
                entry_price
                + (
                    risk
                    * RISK_REWARD
                )
            )


            response.update({

                "signal":
                    "BUY",

                "entry_status":
                    "READY",

                "stop_loss":
                    round(
                        stop_loss,
                        5
                    ),

                "take_profit":
                    round(
                        take_profit,
                        5
                    ),

                "risk_reward":
                    f"1:{RISK_REWARD:g}",

                "info":
                    (
                        "Bullish trend + impulse + "
                        "healthy pullback + EMA50 "
                        "interaction + bullish "
                        "confirmation."
                    ),
            })


    # ============================================================
    # SELL
    # ============================================================

    elif (
        signal == "SELL"
        and pullback_extreme is not None
    ):

        stop_loss = (
            pullback_extreme
            + (
                atr
                * SL_ATR_BUFFER
            )
        )


        risk = (
            stop_loss
            - entry_price
        )


        if risk > 0:

            take_profit = (
                entry_price
                - (
                    risk
                    * RISK_REWARD
                )
            )


            response.update({

                "signal":
                    "SELL",

                "entry_status":
                    "READY",

                "stop_loss":
                    round(
                        stop_loss,
                        5
                    ),

                "take_profit":
                    round(
                        take_profit,
                        5
                    ),

                "risk_reward":
                    f"1:{RISK_REWARD:g}",

                "info":
                    (
                        "Bearish trend + impulse + "
                        "healthy pullback + EMA50 "
                        "interaction + bearish "
                        "confirmation."
                    ),
            })


    # ============================================================
    # WAITING STATES
    # ============================================================

    else:

        if setup_type == "BULLISH_PULLBACK":

            response["info"] = (
                "Bullish impulse detected. "
                "Price is pulling back. "
                "Measure the retracement and "
                "wait for EMA50 interaction."
            )


        elif (
            setup_type
            == "BULLISH_PULLBACK_AT_EMA50"
        ):

            response["info"] = (
                "Bullish pullback reached the "
                "EMA50 measurement zone. "
                "Wait for bullish confirmation."
            )


        elif setup_type == "BEARISH_PULLBACK":

            response["info"] = (
                "Bearish impulse detected. "
                "Price is pulling back. "
                "Measure the retracement and "
                "wait for EMA50 interaction."
            )


        elif (
            setup_type
            == "BEARISH_PULLBACK_AT_EMA50"
        ):

            response["info"] = (
                "Bearish pullback reached the "
                "EMA50 measurement zone. "
                "Wait for bearish confirmation."
            )


        elif setup_type == "BULLISH_TREND":

            response["info"] = (
                "Bullish trend detected. "
                "Waiting for a meaningful "
                "impulse and pullback."
            )


        elif setup_type == "BEARISH_TREND":

            response["info"] = (
                "Bearish trend detected. "
                "Waiting for a meaningful "
                "impulse and pullback."
            )


        else:

            response["info"] = (
                "No valid pullback entry "
                "on the latest candle."
            )


    return response


# ================================================================
# HEALTH CHECK
# ================================================================

@app.get("/")
def home():

    return {

        "message":
            "50 EMA Pullback Analysis Strategy API "
            "running successfully",

        "strategy":
            (
                "Trend → Impulse → Pullback → "
                "EMA50 Measurement → Confirmation"
            ),

        "ema_period":
            EMA_PERIOD,

        "atr_period":
            ATR_PERIOD,

        "supported_timeframes":
            "All candle timeframes"

    }
