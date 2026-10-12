from __future__ import annotations

from typing import Any, Literal

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field


app = FastAPI(
    title="Pure Price Action Strategy API",
    description=(
        "Indicator-free market-structure and pullback-zone detector. "
        "Uses OHLC candles only; it does not issue lower-timeframe entry orders."
    ),
    version="2.0.0",
)


# ================================================================
# CONFIGURATION — PRICE ACTION ONLY
# ================================================================

# A swing is confirmed only after this many candles have formed on
# BOTH sides of the candidate candle. With 2, the pivot is delayed by
# two candles, which helps avoid using an unconfirmed swing.
SWING_STRENGTH = 2

# Number of recent candles used to describe whether price has started
# moving against the current trend. This is a candle count, not an indicator.
PULLBACK_LOOKBACK = 5

# Minimum number of candles needed for reliable swing comparisons.
MIN_CANDLES = (SWING_STRENGTH * 2) + 8


# ================================================================
# REQUEST MODEL
# ================================================================

class MarketData(BaseModel):
    symbol: str = Field(..., min_length=1, max_length=40)
    timeframe: str = Field(..., min_length=1, max_length=10)

    # Each item must contain open, high, low and close.
    # Extra fields (such as timestamp) are accepted and ignored.
    values: list[dict[str, Any]] = Field(..., min_length=1)

    # The previous implementation expected newest candle first.
    # Keep that as the default for backward compatibility.
    newest_first: bool = True


# ================================================================
# CANDLE / SWING HELPERS
# ================================================================

def candle_body_high(candle: dict[str, float]) -> float:
    return max(candle["open"], candle["close"])


def candle_body_low(candle: dict[str, float]) -> float:
    return min(candle["open"], candle["close"])


def find_confirmed_swings(
    candles: list[dict[str, float]],
    strength: int = SWING_STRENGTH,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """
    Return confirmed swing highs and lows.

    A swing high has a high strictly greater than the highs of the
    `strength` candles before and after it. Swing lows use the inverse.

    The last `strength` candles cannot be confirmed pivots because the
    candles to their right do not exist yet.
    """
    swing_highs: list[dict[str, Any]] = []
    swing_lows: list[dict[str, Any]] = []

    for i in range(strength, len(candles) - strength):
        candidate = candles[i]
        left = candles[i - strength:i]
        right = candles[i + 1:i + strength + 1]

        if all(candidate["high"] > c["high"] for c in left + right):
            swing_highs.append({
                "index": i,
                "price": candidate["high"],
                "candle_low": candidate["low"],
                "candle_high": candidate["high"],
                "body_low": candle_body_low(candidate),
                "body_high": candle_body_high(candidate),
            })

        if all(candidate["low"] < c["low"] for c in left + right):
            swing_lows.append({
                "index": i,
                "price": candidate["low"],
                "candle_low": candidate["low"],
                "candle_high": candidate["high"],
                "body_low": candle_body_low(candidate),
                "body_high": candle_body_high(candidate),
            })

    return swing_highs, swing_lows


def classify_market_structure(
    swing_highs: list[dict[str, Any]],
    swing_lows: list[dict[str, Any]],
) -> dict[str, Any]:
    """
    Bullish: latest two confirmed swing highs rise AND latest two
    confirmed swing lows rise.
    Bearish: latest two confirmed swing highs fall AND latest two
    confirmed swing lows fall.
    Otherwise the structure is neutral/mixed.
    """
    result: dict[str, Any] = {
        "trend": "NEUTRAL",
        "reason": "Not enough confirmed swings or structure is mixed.",
        "higher_high": None,
        "higher_low": None,
        "lower_high": None,
        "lower_low": None,
    }

    if len(swing_highs) < 2 or len(swing_lows) < 2:
        result["reason"] = "Need at least two confirmed swing highs and two swing lows."
        return result

    previous_high, latest_high = swing_highs[-2], swing_highs[-1]
    previous_low, latest_low = swing_lows[-2], swing_lows[-1]

    higher_high = latest_high["price"] > previous_high["price"]
    higher_low = latest_low["price"] > previous_low["price"]
    lower_high = latest_high["price"] < previous_high["price"]
    lower_low = latest_low["price"] < previous_low["price"]

    result.update({
        "higher_high": higher_high,
        "higher_low": higher_low,
        "lower_high": lower_high,
        "lower_low": lower_low,
        "previous_swing_high": previous_high,
        "latest_swing_high": latest_high,
        "previous_swing_low": previous_low,
        "latest_swing_low": latest_low,
    })

    if higher_high and higher_low:
        result["trend"] = "BULLISH"
        result["reason"] = "Confirmed higher high and higher low."
    elif lower_high and lower_low:
        result["trend"] = "BEARISH"
        result["reason"] = "Confirmed lower high and lower low."
    else:
        result["reason"] = (
            "Swing highs and lows do not agree; wait for clearer structure."
        )

    return result


def zone_from_swing(
    swing: dict[str, Any],
    zone_type: Literal["SUPPORT", "RESISTANCE"],
) -> dict[str, float]:
    """
    Build a price-action zone from the pivot candle itself.
    No ATR, moving average, or other indicator is used.

    SUPPORT: pivot candle low to the top of its body.
    RESISTANCE: bottom of its body to pivot candle high.
    """
    if zone_type == "SUPPORT":
        return {
            "low": float(swing["candle_low"]),
            "high": float(swing["body_high"]),
        }

    return {
        "low": float(swing["body_low"]),
        "high": float(swing["candle_high"]),
    }


def candle_overlaps_zone(
    candle: dict[str, float],
    zone: dict[str, float],
) -> bool:
    """True when the candle's high-low range overlaps the zone."""
    return candle["low"] <= zone["high"] and candle["high"] >= zone["low"]


def pullback_has_started(
    candles: list[dict[str, float]],
    trend: Literal["BULLISH", "BEARISH"],
    lookback: int = PULLBACK_LOOKBACK,
) -> bool:
    """
    A simple price-only pullback check.

    Bullish trend: recent closes show downward movement, or latest close
    is below the recent high.
    Bearish trend: recent closes show upward movement, or latest close
    is above the recent low.

    This describes a possible retracement; it is not entry confirmation.
    """
    if len(candles) < 2:
        return False

    recent = candles[-(lookback + 1):]
    latest = recent[-1]

    if trend == "BULLISH":
        recent_high = max(c["high"] for c in recent[:-1])
        recent_close_falling = any(
            recent[i]["close"] < recent[i - 1]["close"]
            for i in range(1, len(recent))
        )
        return latest["close"] < recent_high or recent_close_falling

    recent_low = min(c["low"] for c in recent[:-1])
    recent_close_rising = any(
        recent[i]["close"] > recent[i - 1]["close"]
        for i in range(1, len(recent))
    )
    return latest["close"] > recent_low or recent_close_rising


def public_swing(swing: dict[str, Any] | None) -> dict[str, Any] | None:
    """Return the useful swing fields without internal implementation details."""
    if swing is None:
        return None
    return {
        "candle_index_oldest_first": swing["index"],
        "price": round(float(swing["price"]), 8),
        "candle_low": round(float(swing["candle_low"]), 8),
        "candle_high": round(float(swing["candle_high"]), 8),
    }


# ================================================================
# PURE PRICE-ACTION STRATEGY
# ================================================================

def run_price_action_strategy(
    candles: list[dict[str, float]],
) -> dict[str, Any]:
    """
    Analyze the latest candle.

    BUY_ZONE:
      - confirmed bullish structure (HH + HL)
      - latest confirmed higher-low support zone is not invalidated
      - price is pulling back
      - latest candle overlaps the support zone

    SELL_ZONE:
      - confirmed bearish structure (LH + LL)
      - latest confirmed lower-high resistance zone is not invalidated
      - price is pulling back
      - latest candle overlaps the resistance zone

    This endpoint identifies a higher-timeframe area of interest only.
    It does NOT confirm an entry. The trader should check 15M/5M for a
    lower-timeframe structure break/rejection before deciding to enter.
    """
    latest = candles[-1]
    swing_highs, swing_lows = find_confirmed_swings(candles)
    structure = classify_market_structure(swing_highs, swing_lows)
    trend = structure["trend"]

    response: dict[str, Any] = {
        "signal": "NO_SETUP",
        "entry_status": "NOT_READY",
        "market_structure": trend,
        "setup_type": "NO_SETUP",
        "pullback": {
            "detected": False,
            "direction": None,
        },
        "zone": None,
        "invalidation": {
            "invalidated": False,
            "level": None,
            "reason": None,
        },
        "structure": {
            "reason": structure["reason"],
            "previous_swing_high": public_swing(structure.get("previous_swing_high")),
            "latest_swing_high": public_swing(structure.get("latest_swing_high")),
            "previous_swing_low": public_swing(structure.get("previous_swing_low")),
            "latest_swing_low": public_swing(structure.get("latest_swing_low")),
            "confirmed_swing_high_count": len(swing_highs),
            "confirmed_swing_low_count": len(swing_lows),
        },
        "latest_candle": {
            "open": round(latest["open"], 8),
            "high": round(latest["high"], 8),
            "low": round(latest["low"], 8),
            "close": round(latest["close"], 8),
        },
        "lower_timeframe_plan": None,
        "info": "",
        "disclaimer": (
            "A zone is a potential area of interest, not a guaranteed trade. "
            "Wait for independent 15M/5M price-action confirmation."
        ),
    }

    if trend == "NEUTRAL":
        response["info"] = (
            "No clear HH/HL or LH/LL structure. Wait; do not force a trade."
        )
        return response

    is_pullback = pullback_has_started(candles, trend)
    response["pullback"] = {
        "detected": is_pullback,
        "direction": "BEARISH_PULLBACK" if trend == "BULLISH"
                     else "BULLISH_PULLBACK",
    }

    # ------------------------------------------------------------
    # BULLISH STRUCTURE: use latest confirmed higher-low pivot
    # as a support zone.
    # ------------------------------------------------------------
    if trend == "BULLISH":
        swing = swing_lows[-1]
        zone = zone_from_swing(swing, "SUPPORT")
        invalidation_level = float(swing["candle_low"])

        response["zone"] = {
            "type": "SUPPORT",
            "low": round(zone["low"], 8),
            "high": round(zone["high"], 8),
            "source": "Latest confirmed higher-low pivot candle",
            "pivot": public_swing(swing),
        }
        response["invalidation"]["level"] = round(invalidation_level, 8)

        # A candle close below the higher-low pivot invalidates this
        # simple bullish setup. A wick alone does not automatically do so.
        if latest["close"] < invalidation_level:
            response["invalidation"].update({
                "invalidated": True,
                "reason": "Latest candle closed below the structural higher-low.",
            })
            response["info"] = (
                "Bullish setup invalidated: latest close is below the "
                "higher-low pivot. Reassess market structure."
            )
            return response

        if not is_pullback:
            response["signal"] = "WAITING_FOR_PULLBACK"
            response["setup_type"] = "BULLISH_STRUCTURE"
            response["info"] = (
                "Bullish structure detected. Wait for price to retrace "
                "toward the marked support zone."
            )
            return response

        if not candle_overlaps_zone(latest, zone):
            response["signal"] = "WAITING_FOR_ZONE"
            response["setup_type"] = "BULLISH_PULLBACK"
            response["info"] = (
                "Bullish pullback detected, but the latest candle has not "
                "reached the support zone. Wait; do not chase price."
            )
            return response

        response.update({
            "signal": "BUY_ZONE",
            "entry_status": "WAIT_FOR_LOWER_TIMEFRAME_CONFIRMATION",
            "setup_type": "BULLISH_PULLBACK_AT_SUPPORT",
            "lower_timeframe_plan": {
                "timeframes": ["15M", "5M"],
                "direction": "BUY",
                "look_for": [
                    "Price reacts from the higher-timeframe support zone.",
                    "A local bearish pullback stops making lower lows.",
                    "A candle closes above a meaningful recent lower high "
                    "(bullish break of structure).",
                    "Consider entry only after the confirmation candle closes.",
                ],
                "stop_loss_reference": (
                    "Below the confirmed lower-timeframe swing low or the "
                    "structural invalidation point, allowing for the instrument's spread."
                ),
                "take_profit_reference": (
                    "Next meaningful higher-timeframe swing high/resistance; "
                    "check whether at least 1:2 reward-to-risk is available."
                ),
            },
            "info": (
                "BUY ZONE: bullish HH/HL structure and price is inside the "
                "support zone. Switch to 15M/5M and wait for bullish "
                "price-action confirmation. This is not an entry signal."
            ),
        })
        return response

    # ------------------------------------------------------------
    # BEARISH STRUCTURE: use latest confirmed lower-high pivot
    # as a resistance zone.
    # ------------------------------------------------------------
    swing = swing_highs[-1]
    zone = zone_from_swing(swing, "RESISTANCE")
    invalidation_level = float(swing["candle_high"])

    response["zone"] = {
        "type": "RESISTANCE",
        "low": round(zone["low"], 8),
        "high": round(zone["high"], 8),
        "source": "Latest confirmed lower-high pivot candle",
        "pivot": public_swing(swing),
    }
    response["invalidation"]["level"] = round(invalidation_level, 8)

    # A candle close above the lower-high pivot invalidates this
    # simple bearish setup. A wick alone does not automatically do so.
    if latest["close"] > invalidation_level:
        response["invalidation"].update({
            "invalidated": True,
            "reason": "Latest candle closed above the structural lower-high.",
        })
        response["info"] = (
            "Bearish setup invalidated: latest close is above the "
            "lower-high pivot. Reassess market structure."
        )
        return response

    if not is_pullback:
        response["signal"] = "WAITING_FOR_PULLBACK"
        response["setup_type"] = "BEARISH_STRUCTURE"
        response["info"] = (
            "Bearish structure detected. Wait for price to retrace "
            "toward the marked resistance zone."
        )
        return response

    if not candle_overlaps_zone(latest, zone):
        response["signal"] = "WAITING_FOR_ZONE"
        response["setup_type"] = "BEARISH_PULLBACK"
        response["info"] = (
            "Bearish pullback detected, but the latest candle has not "
            "reached the resistance zone. Wait; do not chase price."
        )
        return response

    response.update({
        "signal": "SELL_ZONE",
        "entry_status": "WAIT_FOR_LOWER_TIMEFRAME_CONFIRMATION",
        "setup_type": "BEARISH_PULLBACK_AT_RESISTANCE",
        "lower_timeframe_plan": {
            "timeframes": ["15M", "5M"],
            "direction": "SELL",
            "look_for": [
                "Price rejects the higher-timeframe resistance zone.",
                "A local bullish pullback stops making higher highs.",
                "A candle closes below a meaningful recent higher low "
                "(bearish break of structure).",
                "Consider entry only after the confirmation candle closes.",
            ],
            "stop_loss_reference": (
                "Above the confirmed lower-timeframe swing high or the "
                "structural invalidation point, allowing for the instrument's spread."
            ),
            "take_profit_reference": (
                "Next meaningful higher-timeframe swing low/support; "
                "check whether at least 1:2 reward-to-risk is available."
            ),
        },
        "info": (
            "SELL ZONE: bearish LH/LL structure and price is inside the "
            "resistance zone. Switch to 15M/5M and wait for bearish "
            "price-action confirmation. This is not an entry signal."
        ),
    })
    return response


# ================================================================
# ANALYZE ENDPOINT
# ================================================================

@app.post("/analyze")
def analyze(data: MarketData) -> dict[str, Any]:
    required_columns = ("open", "high", "low", "close")

    if len(data.values) < MIN_CANDLES:
        raise HTTPException(
            status_code=422,
            detail=(
                f"Not enough candles. Provide at least {MIN_CANDLES} "
                "OHLC candles so confirmed swings can be detected."
            ),
        )

    candles: list[dict[str, float]] = []

    for index, raw in enumerate(data.values):
        missing = [key for key in required_columns if key not in raw]
        if missing:
            raise HTTPException(
                status_code=422,
                detail=f"Candle {index} is missing fields: {', '.join(missing)}",
            )

        try:
            candle = {key: float(raw[key]) for key in required_columns}
        except (TypeError, ValueError):
            raise HTTPException(
                status_code=422,
                detail=f"Candle {index} contains a non-numeric OHLC value.",
            )

        import math
        if not all(math.isfinite(value) for value in candle.values()):
            raise HTTPException(
                status_code=422,
                detail=f"Candle {index} contains NaN or infinite OHLC values.",
            )

        if candle["high"] < max(candle["open"], candle["close"], candle["low"]):
            raise HTTPException(
                status_code=422,
                detail=f"Candle {index} has an invalid high value.",
            )

        if candle["low"] > min(candle["open"], candle["close"], candle["high"]):
            raise HTTPException(
                status_code=422,
                detail=f"Candle {index} has an invalid low value.",
            )

        candles.append(candle)

    # Internally, all processing uses oldest candle -> newest candle.
    if data.newest_first:
        candles.reverse()

    result = run_price_action_strategy(candles)
    result["symbol"] = data.symbol
    result["timeframe"] = data.timeframe
    result["candles_used"] = len(candles)
    result["method"] = "PURE_PRICE_ACTION_OHLC_ONLY"
    result["indicators_used"] = []

    return result


# ================================================================
# HEALTH CHECK
# ================================================================

@app.get("/")
def home() -> dict[str, Any]:
    return {
        "message": "Pure Price Action Strategy API is running.",
        "strategy": (
            "Confirmed swing points -> HH/HL or LH/LL structure -> "
            "pullback -> structural support/resistance zone"
        ),
        "method": "PURE_PRICE_ACTION_OHLC_ONLY",
        "indicators_used": [],
        "supported_timeframes": "Any candle timeframe supplied by the client",
        "signals": [
            "BUY_ZONE",
            "SELL_ZONE",
            "WAITING_FOR_PULLBACK",
            "WAITING_FOR_ZONE",
            "NO_SETUP",
        ],
        "important": (
            "BUY_ZONE/SELL_ZONE are higher-timeframe areas of interest, "
            "not trade entries. Confirm manually on 15M/5M."
        ),
    }
