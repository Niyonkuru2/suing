from fastapi import FastAPI
from pydantic import BaseModel
import pandas as pd
from ta.trend import EMAIndicator
import numpy as np

app = FastAPI(title="EMA50 Breakout + Pullback Strategy API")


class MarketData(BaseModel):
    values: list
    symbol: str
    timeframe: str


def detect_breakout_setup(df):
    """
    Detects your specific setup:
    BUY: Price under EMA50 → breaks above EMA50 → makes a high → pulls back → closes above that high
    SELL: Price above EMA50 → breaks below EMA50 → makes a low → pulls back → closes below that low
    """
    
    # Get last 30 candles for analysis
    if len(df) < 30:
        return None, None, None
    
    # We need to check the recent history
    recent_df = df.iloc[-30:].copy()
    
    # Find where price crossed EMA50
    recent_df['above_ema'] = recent_df['close'] > recent_df['ema50']
    recent_df['below_ema'] = recent_df['close'] < recent_df['ema50']
    recent_df['ema_cross_up'] = (recent_df['above_ema'] & recent_df['below_ema'].shift(1))
    recent_df['ema_cross_down'] = (recent_df['below_ema'] & recent_df['above_ema'].shift(1))
    
    # Get latest candle
    latest = df.iloc[-1]
    
    # Check if we have any recent crosses
    if not recent_df['ema_cross_up'].any() and not recent_df['ema_cross_down'].any():
        return None, None, None
    
    # =========================
    # BUY SETUP DETECTION
    # =========================
    # Find the most recent EMA cross up
    cross_up_indices = recent_df[recent_df['ema_cross_up']].index
    if len(cross_up_indices) > 0:
        last_cross_up_idx = cross_up_indices[-1]
        
        # Check if price was under EMA50 before cross
        if last_cross_up_idx > 0 and recent_df.loc[last_cross_up_idx - 1, 'close'] < recent_df.loc[last_cross_up_idx - 1, 'ema50']:
            
            # Look for a high made after the cross
            candles_after_cross = recent_df.loc[last_cross_up_idx:].copy()
            
            if len(candles_after_cross) >= 3:
                # Find the highest high after cross
                high_after_cross = candles_after_cross['high'].max()
                high_idx_after_cross = candles_after_cross['high'].idxmax()
                
                # Check if current price pulled back and closed above that high
                if high_idx_after_cross < len(df) - 1:  # Make sure we have candles after the high
                    # Find candles after the high
                    candles_after_high = df.loc[high_idx_after_cross + 1:].copy()
                    
                    if len(candles_after_high) > 0:
                        # Check if price pulled back below the high
                        if any(candles_after_high['close'] < df.loc[high_idx_after_cross, 'high']):
                            # Check if current close is above that high
                            if latest['close'] > df.loc[high_idx_after_cross, 'high']:
                                return "BUY_TREND", df.loc[high_idx_after_cross, 'high'], high_idx_after_cross
    
    # =========================
    # SELL SETUP DETECTION
    # =========================
    # Find the most recent EMA cross down
    cross_down_indices = recent_df[recent_df['ema_cross_down']].index
    if len(cross_down_indices) > 0:
        last_cross_down_idx = cross_down_indices[-1]
        
        # Check if price was above EMA50 before cross
        if last_cross_down_idx > 0 and recent_df.loc[last_cross_down_idx - 1, 'close'] > recent_df.loc[last_cross_down_idx - 1, 'ema50']:
            
            # Look for a low made after the cross
            candles_after_cross = recent_df.loc[last_cross_down_idx:].copy()
            
            if len(candles_after_cross) >= 3:
                # Find the lowest low after cross
                low_after_cross = candles_after_cross['low'].min()
                low_idx_after_cross = candles_after_cross['low'].idxmin()
                
                # Check if current price pulled back and closed below that low
                if low_idx_after_cross < len(df) - 1:  # Make sure we have candles after the low
                    # Find candles after the low
                    candles_after_low = df.loc[low_idx_after_cross + 1:].copy()
                    
                    if len(candles_after_low) > 0:
                        # Check if price pulled back above the low
                        if any(candles_after_low['close'] > df.loc[low_idx_after_cross, 'low']):
                            # Check if current close is below that low
                            if latest['close'] < df.loc[low_idx_after_cross, 'low']:
                                return "SELL_TREND", df.loc[low_idx_after_cross, 'low'], low_idx_after_cross
    
    return None, None, None


@app.post("/analyze")
def analyze(data: MarketData):
    df = pd.DataFrame(data.values)
    
    if not all(col in df.columns for col in ['open', 'high', 'low', 'close']):
        return {"error": "Missing OHLC data"}
    
    if len(df) < 60:
        return {"error": "Not enough data"}
    
    # Latest candle at bottom
    df = df.iloc[::-1].reset_index(drop=True)
    
    # Convert to float
    for col in ['open', 'high', 'low', 'close']:
        df[col] = df[col].astype(float)
    
    # =========================
    # EMA 50
    # =========================
    df['ema50'] = EMAIndicator(close=df['close'], window=50).ema_indicator()
    
    latest = df.iloc[-1]
    
    # =========================
    # DETECT YOUR SETUP
    # =========================
    signal, key_level, key_idx = detect_breakout_setup(df)
    
    stop_loss = None
    take_profit = None
    structure_type = "NO_CLEAR_SETUP"
    
    # =========================
    # BUY CONDITIONS
    # =========================
    if signal == "BUY_TREND":
        structure_type = "BREAKOUT_PULLBACK_BUY"
        
        # SL below the pullback low (the swing low after the breakout)
        # Check candles after the breakout high
        candles_after_breakout = df.loc[key_idx + 1:].copy()
        if len(candles_after_breakout) > 0:
            # Find the lowest low during pullback
            pullback_low = candles_after_breakout['low'].min()
            stop_loss = pullback_low  # SL below pullback low
        else:
            stop_loss = latest['close'] - (latest['close'] * 0.01)  # Default 1% stop
        
        # 1:2 Risk Reward
        risk = latest['close'] - stop_loss
        take_profit = latest['close'] + (risk * 2)
        
        return {
            "symbol": data.symbol,
            "timeframe": data.timeframe,
            "setup_type": structure_type,
            "signal": signal,
            "entry": round(latest['close'], 5),
            "key_level": round(key_level, 5) if key_level else None,
            "ema50": round(latest['ema50'], 5),
            "stop_loss": round(stop_loss, 5),
            "take_profit": round(take_profit, 5),
            "risk_reward": "1:2"
        }
    
    # =========================
    # SELL CONDITIONS
    # =========================
    elif signal == "SELL_TREND":
        structure_type = "BREAKOUT_PULLBACK_SELL"
        
        # SL above the pullback high (the swing high after the breakdown)
        candles_after_breakdown = df.loc[key_idx + 1:].copy()
        if len(candles_after_breakdown) > 0:
            # Find the highest high during pullback
            pullback_high = candles_after_breakdown['high'].max()
            stop_loss = pullback_high  # SL above pullback high
        else:
            stop_loss = latest['close'] + (latest['close'] * 0.01)  # Default 1% stop
        
        # 1:2 Risk Reward
        risk = stop_loss - latest['close']
        take_profit = latest['close'] - (risk * 2)
        
        return {
            "symbol": data.symbol,
            "timeframe": data.timeframe,
            "setup_type": structure_type,
            "signal": signal,
            "entry": round(latest['close'], 5),
            "key_level": round(key_level, 5) if key_level else None,
            "ema50": round(latest['ema50'], 5),
            "stop_loss": round(stop_loss, 5),
            "take_profit": round(take_profit, 5),
            "risk_reward": "1:2"
        }
    
    # =========================
    # NO SIGNAL
    # =========================
    else:
        # Check if we have any recent crosses for informational purposes
        recent_df = df.iloc[-30:].copy()
        recent_df['above_ema'] = recent_df['close'] > recent_df['ema50']
        recent_df['below_ema'] = recent_df['close'] < recent_df['ema50']
        recent_df['ema_cross_up'] = (recent_df['above_ema'] & recent_df['below_ema'].shift(1))
        recent_df['ema_cross_down'] = (recent_df['below_ema'] & recent_df['above_ema'].shift(1))
        
        info = "No setup detected. "
        if recent_df['ema_cross_up'].any():
            info += "EMA cross up detected but no pullback and close above high yet. "
        if recent_df['ema_cross_down'].any():
            info += "EMA cross down detected but no pullback and close below low yet. "
        
        return {
            "symbol": data.symbol,
            "timeframe": data.timeframe,
            "setup_type": "NO_SETUP",
            "signal": "NO_TRADE",
            "info": info,
            "entry": round(latest['close'], 5),
            "ema50": round(latest['ema50'], 5),
            "stop_loss": None,
            "take_profit": None
        }


@app.get("/")
def home():
    return {"message": "EMA50 Breakout + Pullback Strategy API running successfully"}
