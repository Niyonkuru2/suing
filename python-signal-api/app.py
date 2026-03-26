from fastapi import FastAPI
from pydantic import BaseModel
import pandas as pd
from ta.trend import EMAIndicator

app = FastAPI(title="Triple EMA Trend Strategy API")


class MarketData(BaseModel):
    values: list
    symbol: str
    timeframe: str


@app.post("/analyze")
def analyze(data: MarketData):

    df = pd.DataFrame(data.values)

    if not all(col in df.columns for col in ['open', 'high', 'low', 'close']):
        return {"error": "Missing OHLC data"}

    if len(df) < 120:
        return {"error": "Not enough data"}

    # Latest candle at bottom
    df = df.iloc[::-1].reset_index(drop=True)

    # Convert to float
    for col in ['open', 'high', 'low', 'close']:
        df[col] = df[col].astype(float)

    # =========================
    # EMAs
    # =========================
    df['ema20'] = EMAIndicator(close=df['close'], window=20).ema_indicator()
    df['ema50'] = EMAIndicator(close=df['close'], window=50).ema_indicator()
    df['ema100'] = EMAIndicator(close=df['close'], window=100).ema_indicator()

    latest = df.iloc[-1]
    prev = df.iloc[-2]

    signal = "NO_TRADE"
    structure = "RANGE"
    stop_loss = None
    take_profit = None

    # Distance check (EMAs spreading)
    spread_up = (latest['ema20'] - latest['ema50']) > (prev['ema20'] - prev['ema50']) \
                and (latest['ema50'] - latest['ema100']) > (prev['ema50'] - prev['ema100'])

    spread_down = (latest['ema50'] - latest['ema20']) > (prev['ema50'] - prev['ema20']) \
                  and (latest['ema100'] - latest['ema50']) > (prev['ema100'] - prev['ema50'])

    # =========================
    # BUY CONDITIONS
    # =========================
    if (
        latest['close'] > latest['ema20'] > latest['ema50'] > latest['ema100']
        and spread_up
    ):

        structure = "UPTREND"

        # Pullback detection
        if latest['low'] <= latest['ema20'] or latest['low'] <= latest['ema50']:
            signal = "BUY_PULLBACK"
        else:
            signal = "BUY_ALERT"

        stop_loss = df['low'].iloc[-6:-1].min()
        risk = latest['close'] - stop_loss
        take_profit = latest['close'] + (risk * 2)

    # =========================
    # SELL CONDITIONS
    # =========================
    elif (
        latest['close'] < latest['ema20'] < latest['ema50'] < latest['ema100']
        and spread_down
    ):

        structure = "DOWNTREND"

        # Pullback detection
        if latest['high'] >= latest['ema20'] or latest['high'] >= latest['ema50']:
            signal = "SELL_PULLBACK"
        else:
            signal = "SELL_ALERT"

        stop_loss = df['high'].iloc[-6:-1].max()
        risk = stop_loss - latest['close']
        take_profit = latest['close'] - (risk * 2)

    return {
        "symbol": data.symbol,
        "timeframe": data.timeframe,
        "structure": structure,
        "signal": signal,
        "entry": round(latest['close'], 5),
        "ema20": round(latest['ema20'], 5),
        "ema50": round(latest['ema50'], 5),
        "ema100": round(latest['ema100'], 5),
        "stop_loss": round(stop_loss, 5) if stop_loss else None,
        "take_profit": round(take_profit, 5) if take_profit else None
    }


@app.get("/")
def home():
    return {"message": "Triple EMA Strategy API running successfully"}
