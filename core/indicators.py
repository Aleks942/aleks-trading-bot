import pandas as pd
import numpy as np

# ---------------------------------------------------------
# 1. SMA / EMA
# ---------------------------------------------------------

def sma(series, period: int = 14):
    return series.rolling(period).mean()

def ema(series, period: int = 14):
    return series.ewm(span=period, adjust=False).mean()

# ---------------------------------------------------------
# 2. MACD
# ---------------------------------------------------------

def macd(series, fast=12, slow=26, signal=9):
    fast_ema = ema(series, fast)
    slow_ema = ema(series, slow)
    macd_line = fast_ema - slow_ema
    signal_line = ema(macd_line, signal)
    histogram = macd_line - signal_line
    return macd_line, signal_line, histogram

# ---------------------------------------------------------
# 3. RSI
# ---------------------------------------------------------

def rsi(series, period=14):
    delta = series.diff()
    gain = np.where(delta > 0, delta, 0)
    loss = np.where(delta < 0, -delta, 0)
    avg_gain = pd.Series(gain).rolling(period).mean()
    avg_loss = pd.Series(loss).rolling(period).mean()
    rs = avg_gain / avg_loss
    return 100 - (100 / (1 + rs))

# ---------------------------------------------------------
# 4. STOCHASTIC
# ---------------------------------------------------------

def stochastic(df, k_period=14, d_period=3):
    low = df["low"].rolling(k_period).min()
    high = df["high"].rolling(k_period).max()
    k = 100 * ((df["close"] - low) / (high - low))
    d = k.rolling(d_period).mean()
    return k, d

# ---------------------------------------------------------
# 5. ATR (VOLATILITY)
# ---------------------------------------------------------

def atr(df, period=14):
    high_low = df["high"] - df["low"]
    high_close = (df["high"] - df["close"].shift()).abs()
    low_close = (df["low"] - df["close"].shift()).abs()
    tr = pd.concat([high_low, high_close, low_close], axis=1).max(axis=1)
    return tr.rolling(period).mean()

# ---------------------------------------------------------
# 6. ADX (trend strength)
# ---------------------------------------------------------

def adx(df, period=14):
    plus_dm = df["high"].diff()
    minus_dm = df["low"].diff() * -1

    plus_dm = np.where((plus_dm > minus_dm) & (plus_dm > 0), plus_dm, 0)
    minus_dm = np.where((minus_dm > plus_dm) & (minus_dm > 0), minus_dm, 0)

    trur = atr(df, period)
    plus_di = 100 * (pd.Series(plus_dm).rolling(period).sum() / trur)
    minus_di = 100 * (pd.Series(minus_dm).rolling(period).sum() / trur)

    dx = (abs(plus_di - minus_di) / (plus_di + minus_di)) * 100
    return dx.rolling(period).mean()

# ---------------------------------------------------------
# 7. BOLLINGER BANDS
# ---------------------------------------------------------

def bollinger(series, period=20, mult=2):
    mid = series.rolling(period).mean()
    std = series.rolling(period).std()
    upper = mid + mult * std
    lower = mid - mult * std
    return mid, upper, lower

# ---------------------------------------------------------
# 8. VWAP
# ---------------------------------------------------------

def vwap(df):
    pv = df["close"] * df["volume"]
    return pv.cumsum() / df["volume"].cumsum()

# ---------------------------------------------------------
# 9. OBV (volume trend)
# ---------------------------------------------------------

def obv(df):
    obv = [0]
    for i in range(1, len(df)):
        if df["close"].iloc[i] > df["close"].iloc[i-1]:
            obv.append(obv[-1] + df["volume"].iloc[i])
        elif df["close"].iloc[i] < df["close"].iloc[i-1]:
            obv.append(obv[-1] - df["volume"].iloc[i])
        else:
            obv.append(obv[-1])
    return pd.Series(obv)

# ---------------------------------------------------------
# 10. MOMENTUM
# ---------------------------------------------------------

def momentum(series, period=10):
    return series - series.shift(period)

# ---------------------------------------------------------
# 11. ROC (rate of change)
# ---------------------------------------------------------

def roc(series, period=12):
    return (series / series.shift(period) - 1) * 100

# ---------------------------------------------------------
# 12. SuperTrend
# ---------------------------------------------------------

def supertrend(df, period=10, multiplier=3):

    atr_value = atr(df, period)
    hl2 = (df["high"] + df["low"]) / 2

    upperband = hl2 + multiplier * atr_value
    lowerband = hl2 - multiplier * atr_value

    st = [0]
    for i in range(1, len(df)):
        if df["close"].iloc[i] > upperband.iloc[i-1]:
            st.append(lowerband.iloc[i])
        elif df["close"].iloc[i] < lowerband.iloc[i-1]:
            st.append(upperband.iloc[i])
        else:
            st.append(st[i-1])
    return pd.Series(st)

