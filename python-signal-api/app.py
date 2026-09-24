from fastapi import FastAPI
from pydantic import BaseModel
import pandas as pd
from ta.trend import EMAIndicator
from ta.volatility import AverageTrueRange


app = FastAPI(
    title="25/50/100 EMA Pullback Strategy API"
)


# ================================================================
# CONFIGURATION
# ================================================================

EMA_FAST = 25
EMA_MID = 50
EMA_SLOW = 100
ATR_PERIOD = 14

# Price may come this many ATRs away from EMA50 and still
# be considered an EMA50 pullback/touch.
EMA50_TOUCH_ATR_TOLERANCE = 0.30

# Rejection candle requirements.
# Example: wick >= 1.0 x body.
MIN_REJECTION_WICK_BODY_RATIO = 1.0

# Where the candle must close inside its range.
# 0.60 means bullish candle closes in the upper 40%;
# bearish candle closes in the lower 40%.
MIN_CLOSE_POSITION = 0.60

# Stop-loss / take-profit
SL_ATR_BUFFER = 0.15
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
# 25 / 50 / 100 EMA TREND
# ================================================================

def get_trend(df, i):
    """
    BUY environment:
        EMA25 > EMA50 > EMA100

    SELL environment:
        EMA100 > EMA50 > EMA25

    Otherwise:
        NEUTRAL
    """

    ema25 = float(df["ema25"].iloc[i])
    ema50 = float(df["ema50"].iloc[i])
    ema100 = float(df["ema100"].iloc[i])

    if any(pd.isna(x) for x in [ema25, ema50, ema100]):
        return "NEUTRAL"

    if ema25 > ema50 > ema100:
        return "BULL"

    if ema100 > ema50 > ema25:
        return "BEAR"

    return "NEUTRAL"


# ================================================================
# EMA50 PULLBACK / TOUCH
# ================================================================

def candle_touches_ema50(row, ema50, atr):
    """
    The candle must actually reach the EMA50 zone.

    A candle is considered near EMA50 when the candle range
    overlaps the EMA50 +/- ATR tolerance zone.
    """

    if pd.isna(ema50) or pd.isna(atr) or atr <= 0:
        return False

    tolerance = atr * EMA50_TOUCH_ATR_TOLERANCE

    zone_low = ema50 - tolerance
    zone_high = ema50 + tolerance

    return (
        float(row["low"]) <= zone_high
        and float(row["high"]) >= zone_low
    )


# ================================================================
# REJECTION CANDLES
# ================================================================

def bullish_rejection(row):
    """
    Bullish rejection:
      - bullish/green candle
      - meaningful lower wick
      - close in upper part of candle
    """

    open_price = float(row["open"])
    high = float(row["high"])
    low = float(row["low"])
    close = float(row["close"])

    candle_range = high - low
    body = abs(close - open_price)

    if candle_range <= 0 or body <= 0:
        return False

    lower_wick = min(open_price, close) - low
    close_position = (close - low) / candle_range

    return (
        close > open_price
        and lower_wick >= body * MIN_REJECTION_WICK_BODY_RATIO
        and close_position >= MIN_CLOSE_POSITION
    )


def bearish_rejection(row):
    """
    Bearish rejection:
      - bearish/red candle
      - meaningful upper wick
      - close in lower part of candle
    """

    open_price = float(row["open"])
    high = float(row["high"])
    low = float(row["low"])
    close = float(row["close"])

    candle_range = high - low
    body = abs(close - open_price)

    if candle_range <= 0 or body <= 0:
        return False

    upper_wick = high - max(open_price, close)
    close_position = (high - close) / candle_range

    return (
        close < open_price
        and upper_wick >= body * MIN_REJECTION_WICK_BODY_RATIO
        and close_position >= MIN_CLOSE_POSITION
    )


# ================================================================
# MAIN STRATEGY
# ================================================================

def run_ema_pullback_strategy(df):
    """
    Evaluate the MOST RECENT candle only.

    BUY:
      EMA25 > EMA50 > EMA100
      + recent price was above EMA50
      + current candle pulls back into EMA50 zone
      + current candle is bullish rejection
      + current candle closes above EMA50

    SELL:
      EMA100 > EMA50 > EMA25
      + recent price was below EMA50
      + current candle pulls back into EMA50 zone
      + current candle is bearish rejection
      + current candle closes below EMA50
    """

    n = len(df)

    signal = None
    key_level = None
    pullback_extreme = None
    setup_type = "NO_SETUP"
    entry_status = "NOT_READY"
    analysis = {}

    if n < 4:
        return (
            signal,
            key_level,
            pullback_extreme,
            setup_type,
            analysis,
            {"entry_status": entry_status}
        )

    i = n - 1
    row = df.iloc[i]

    ema25 = float(row["ema25"])
    ema50 = float(row["ema50"])
    ema100 = float(row["ema100"])
    atr = float(row["atr"])

    trend = get_trend(df, i)

    if any(pd.isna(x) for x in [ema25, ema50, ema100, atr]) or atr <= 0:
        return (
            signal,
            key_level,
            pullback_extreme,
            setup_type,
            analysis,
            {"entry_status": "NOT_READY"}
        )

    # Look back a few candles to confirm price was on the
    # correct side of EMA50 before the pullback.
    lookback_start = max(0, i - 3)
    recent = df.iloc[lookback_start:i]

    had_price_above_ema50 = any(
        float(r["close"]) > float(r["ema50"])
        for _, r in recent.iterrows()
    )

    had_price_below_ema50 = any(
        float(r["close"]) < float(r["ema50"])
        for _, r in recent.iterrows()
    )

    touched_ema50 = candle_touches_ema50(
        row,
        ema50,
        atr
    )

    # ============================================================
    # BUY
    # ============================================================

    if trend == "BULL":

        setup_type = "BULLISH_TREND"

        if had_price_above_ema50 and touched_ema50:
            setup_type = "BULLISH_PULLBACK_AT_EMA50"
            entry_status = "WAITING_FOR_CONFIRMATION"

        confirmation = (
            had_price_above_ema50
            and touched_ema50
            and bullish_rejection(row)
            and float(row["close"]) > ema50
        )

        if confirmation:

            signal = "BUY"
            key_level = ema50
            pullback_extreme = float(row["low"])
            entry_status = "READY"
            setup_type = "EMA50_PULLBACK_BUY"

            analysis = {
                "trend": "BULL",
                "ema25": round(ema25, 5),
                "ema50": round(ema50, 5),
                "ema100": round(ema100, 5),
                "ema_alignment": "EMA25 > EMA50 > EMA100",
                "price_pulled_back_to_ema50": True,
                "ema50_touched": True,
                "confirmation": "BULLISH_REJECTION",
                "entry_candle_low": round(float(row["low"]), 5),
                "entry_candle_high": round(float(row["high"]), 5),
                "entry_candle_close": round(float(row["close"]), 5),
            }

    # ============================================================
    # SELL
    # ============================================================

    elif trend == "BEAR":

        setup_type = "BEARISH_TREND"

        if had_price_below_ema50 and touched_ema50:
            setup_type = "BEARISH_PULLBACK_AT_EMA50"
            entry_status = "WAITING_FOR_CONFIRMATION"

        confirmation = (
            had_price_below_ema50
            and touched_ema50
            and bearish_rejection(row)
            and float(row["close"]) < ema50
        )

        if confirmation:

            signal = "SELL"
            key_level = ema50
            pullback_extreme = float(row["high"])
            entry_status = "READY"
            setup_type = "EMA50_PULLBACK_SELL"

            analysis = {
                "trend": "BEAR",
                "ema25": round(ema25, 5),
                "ema50": round(ema50, 5),
                "ema100": round(ema100, 5),
                "ema_alignment": "EMA100 > EMA50 > EMA25",
                "price_pulled_back_to_ema50": True,
                "ema50_touched": True,
                "confirmation": "BEARISH_REJECTION",
                "entry_candle_low": round(float(row["low"]), 5),
                "entry_candle_high": round(float(row["high"]), 5),
                "entry_candle_close": round(float(row["close"]), 5),
            }

    else:
        setup_type = "NO_SETUP"
        entry_status = "NOT_READY"

    status = {
        "entry_status": entry_status,
        "latest_trend": trend,
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

    if len(df) < EMA_SLOW:
        return {
            "error": f"Not enough data. Need at least {EMA_SLOW} candles."
        }

    # Incoming data is assumed to be newest first.
    # Convert to oldest -> newest for EMA/strategy calculations.
    df = (
        df.iloc[::-1]
        .reset_index(drop=True)
    )

    for col in required_columns:
        df[col] = pd.to_numeric(
            df[col],
            errors="coerce"
        )

    df = (
        df.dropna(subset=required_columns)
        .reset_index(drop=True)
    )

    # ============================================================
    # EMAs
    # ============================================================

    df["ema25"] = EMAIndicator(
        close=df["close"],
        window=EMA_FAST
    ).ema_indicator()

    df["ema50"] = EMAIndicator(
        close=df["close"],
        window=EMA_MID
    ).ema_indicator()

    df["ema100"] = EMAIndicator(
        close=df["close"],
        window=EMA_SLOW
    ).ema_indicator()

    # ============================================================
    # ATR
    # ============================================================

    atr_indicator = AverageTrueRange(
        high=df["high"],
        low=df["low"],
        close=df["close"],
        window=ATR_PERIOD
    )

    df["atr"] = atr_indicator.average_true_range()

    df = (
        df.dropna(
            subset=[
                "ema25",
                "ema50",
                "ema100",
                "atr"
            ]
        )
        .reset_index(drop=True)
    )

    if len(df) < 2:
        return {
            "error": "Not enough data after indicator warm-up."
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
    ) = run_ema_pullback_strategy(df)

    latest = df.iloc[-1]

    entry_price = float(latest["close"])
    ema25 = float(latest["ema25"])
    ema50 = float(latest["ema50"])
    ema100 = float(latest["ema100"])
    atr = float(latest["atr"])

    latest_trend = get_trend(df, len(df) - 1)

    response = {
        "symbol": data.symbol,
        "timeframe": data.timeframe,

        "entry_price": round(entry_price, 5),

        "ema25": round(ema25, 5),
        "ema50": round(ema50, 5),
        "ema100": round(ema100, 5),

        "ema_alignment": (
            "EMA25 > EMA50 > EMA100"
            if latest_trend == "BULL"
            else
            "EMA100 > EMA50 > EMA25"
            if latest_trend == "BEAR"
            else
            "NONE"
        ),

        "atr": round(atr, 5),

        "signal": "NEUTRAL",

        "entry_status": status["entry_status"],

        "setup_type": setup_type,

        "key_level": (
            round(float(key_level), 5)
            if key_level is not None
            else None
        ),

        "pullback_extreme": (
            round(float(pullback_extreme), 5)
            if pullback_extreme is not None
            else None
        ),

        "stop_loss": None,
        "take_profit": None,
        "risk_reward": None,

        "pullback_analysis": analysis,

        "status": status
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
            - (atr * SL_ATR_BUFFER)
        )

        risk = entry_price - stop_loss

        if risk > 0:

            take_profit = (
                entry_price
                + (risk * RISK_REWARD)
            )

            response.update({
                "signal": "BUY",
                "entry_status": "READY",

                "stop_loss": round(
                    stop_loss,
                    5
                ),

                "take_profit": round(
                    take_profit,
                    5
                ),

                "risk_reward": f"1:{RISK_REWARD:g}",

                "info": (
                    "EMA25 > EMA50 > EMA100 + "
                    "price pulled back to EMA50 + "
                    "bullish rejection candle."
                )
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
            + (atr * SL_ATR_BUFFER)
        )

        risk = stop_loss - entry_price

        if risk > 0:

            take_profit = (
                entry_price
                - (risk * RISK_REWARD)
            )

            response.update({
                "signal": "SELL",
                "entry_status": "READY",

                "stop_loss": round(
                    stop_loss,
                    5
                ),

                "take_profit": round(
                    take_profit,
                    5
                ),

                "risk_reward": f"1:{RISK_REWARD:g}",

                "info": (
                    "EMA100 > EMA50 > EMA25 + "
                    "price pulled back to EMA50 + "
                    "bearish rejection candle."
                )
            })

    # ============================================================
    # WAITING STATES
    # ============================================================

    else:

        if setup_type == "BULLISH_PULLBACK_AT_EMA50":

            response["info"] = (
                "Bullish EMA alignment detected and "
                "price reached the EMA50 zone. "
                "Wait for a bullish rejection candle."
            )

        elif setup_type == "BEARISH_PULLBACK_AT_EMA50":

            response["info"] = (
                "Bearish EMA alignment detected and "
                "price reached the EMA50 zone. "
                "Wait for a bearish rejection candle."
            )

        elif latest_trend == "BULL":

            response["info"] = (
                "Bullish EMA alignment: "
                "EMA25 > EMA50 > EMA100. "
                "Wait for price to pull back to EMA50."
            )

        elif latest_trend == "BEAR":

            response["info"] = (
                "Bearish EMA alignment: "
                "EMA100 > EMA50 > EMA25. "
                "Wait for price to pull back to EMA50."
            )

        else:

            response["info"] = (
                "No valid 25/50/100 EMA alignment."
            )

    return response


# ================================================================
# HEALTH CHECK
# ================================================================

@app.get("/")
def home():

    return {
        "message": (
            "25/50/100 EMA Pullback Strategy API "
            "running successfully"
        ),

        "strategy": (
            "EMA alignment -> EMA50 pullback -> "
            "rejection candle -> entry"
        ),

        "ema_periods": [
            EMA_FAST,
            EMA_MID,
            EMA_SLOW
        ],

        "atr_period": ATR_PERIOD,

        "supported_timeframes": "All candle timeframes"
    }
