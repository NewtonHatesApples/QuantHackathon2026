import time
import os
import json
import requests
import warnings

import pandas as pd
import numpy as np

from collections import deque
from datetime import datetime
from zoneinfo import ZoneInfo
from api import RoostooAPI

# ====================== CONFIG ======================
warnings.filterwarnings("ignore")

COINS = ["BTC", "ETH", "SOL", "XRP", "BNB"]
ROOSTOO_PAIRS = [f"{coin}/USD" for coin in COINS]
BINANCE_SYMBOLS = [f"{coin}USDT" for coin in COINS]

# Hard-coded best Optuna parameters
PARAMS = {
    'K': 1386,
    'lambda_sigma': 0.9417,
    'target_vol': 0.0009435,
    'hysteresis': 0.07011,
    'cost_buffer': 0.001695,
    'liq_log': 2.5500
}

c = 0.001  # 0.1%

# ====================== BOT ======================
class MultiCoinSTBAIBot:
    def __init__(self):
        self.api = RoostooAPI(
            api_key=os.environ.get("API_KEY"),
            api_secret=os.environ.get("API_SECRET")
        )

        # === Fetch and store exchange rules (PricePrecision, AmountPrecision, MiniOrder) ===
        print("Fetching Roostoo exchangeInfo...")
        ex_info = self.api.get_exchange_info()
        self.rules = {}
        for pair, info in ex_info.get("TradePairs", {}).items():
            self.rules[pair] = {
                "amount_prec": int(info.get("AmountPrecision", 6)),
                "price_prec": int(info.get("PricePrecision", 2)),
                "min_order": float(info.get("MiniOrder", 0.0001))
            }
        print(f"Loaded rules for {len(self.rules)} pairs. Example ETH/USD: {self.rules.get('ETH/USD')}")

        self.position = {coin: 0.0 for coin in COINS}
        self.history = {coin: deque(maxlen=PARAMS['K'] + 20) for coin in COINS}
        self.sigma = {coin: 0.001 for coin in COINS}
        self.last_portfolio_print = time.time()

        print("🚀 Multi-Coin STBAI Bot started with full exchange rule compliance")
        print(f"Coins: {COINS}")

    def fetch_latest_klines(self, binance_sym: str) -> pd.DataFrame:
        url = f"https://api.binance.com/api/v3/klines?symbol={binance_sym}&interval=1m&limit=500"
        data = requests.get(url, timeout=15).json()
        df = pd.DataFrame(data, columns=["open_time", "open", "high", "low", "close", "volume",
                                         "close_time", "quote_volume", "trades", "tb_base", "tb_quote", "ignore"])
        for col in ["open", "high", "low", "close", "volume", "trades", "tb_base", "tb_quote", "quote_volume"]:
            df[col] = df[col].astype(float)
        df["datetime"] = pd.to_datetime(df["open_time"], unit="ms")
        return df

    def build_features(self, df: pd.DataFrame) -> np.ndarray:
        """Full real 1m + current 1h + current 1d features (no dummy)"""
        latest = df.iloc[-1].copy()

        # 1m
        I_B_m = 2 * latest['tb_base'] / latest['volume'] - 1 if latest['volume'] > 0 else 0.0
        I_Q_m = 2 * latest['tb_quote'] / latest['quote_volume'] - 1 if latest['quote_volume'] > 0 else 0.0
        TI_m = np.log(latest['trades'] + 1)
        r_m = np.log(latest['close'] / latest['open']) if latest['open'] > 0 else 0.0
        v_m = np.log(latest['high'] / latest['low']) if latest['low'] > 0 else 0.0
        log_vol_m = np.log(latest['volume'] + 1)

        # Current 1h
        current_hour = latest['datetime'].floor('H')
        hour_df = df[df['datetime'].dt.floor('H') == current_hour]
        if len(hour_df) > 0:
            I_B_h = 2 * hour_df['tb_base'].sum() / hour_df['volume'].sum() - 1 if hour_df['volume'].sum() > 0 else 0.0
            I_Q_h = 2 * hour_df['tb_quote'].sum() / hour_df['quote_volume'].sum() - 1 if hour_df['quote_volume'].sum() > 0 else 0.0
            TI_h = np.log(hour_df['trades'].sum() + 1)
            r_h = np.log(hour_df['close'].iloc[-1] / hour_df['open'].iloc[0]) if hour_df['open'].iloc[0] > 0 else 0.0
            v_h = np.log(hour_df['high'].max() / hour_df['low'].min()) if hour_df['low'].min() > 0 else 0.0
        else:
            I_B_h = I_Q_h = TI_h = r_h = v_h = 0.0

        # Current 1d
        current_day = latest['datetime'].floor('D')
        day_df = df[df['datetime'].dt.floor('D') == current_day]
        if len(day_df) > 0:
            I_B_d = 2 * day_df['tb_base'].sum() / day_df['volume'].sum() - 1 if day_df['volume'].sum() > 0 else 0.0
            I_Q_d = 2 * day_df['tb_quote'].sum() / day_df['quote_volume'].sum() - 1 if day_df['quote_volume'].sum() > 0 else 0.0
            TI_d = np.log(day_df['trades'].sum() + 1)
            r_d = np.log(day_df['close'].iloc[-1] / day_df['open'].iloc[0]) if day_df['open'].iloc[0] > 0 else 0.0
            v_d = np.log(day_df['high'].max() / day_df['low'].min()) if day_df['low'].min() > 0 else 0.0
        else:
            I_B_d = I_Q_d = TI_d = r_d = v_d = 0.0

        sin_h = np.sin(2 * np.pi * latest['datetime'].hour / 24)
        cos_h = np.cos(2 * np.pi * latest['datetime'].hour / 24)

        return np.array([
            I_B_m, I_Q_m, TI_m, r_m, v_m, log_vol_m,
            I_B_h, I_Q_h, TI_h, r_h, v_h,
            I_B_d, I_Q_d, TI_d, r_d, v_d,
            sin_h, cos_h
        ], dtype=np.float64)

    def get_portfolio_value(self) -> float:
        try:
            bal = self.api.get_balance()
            total = 0.0
            for coin in COINS:
                pair = f"{coin}/USD"
                ticker = self.api.get_ticker(pair)
                price = float(ticker.get("LastPrice", 1.0))
                free = float(bal.get(coin, {}).get("Free", 0))
                total += free * price
            usd_free = float(bal.get("USD", {}).get("Free", 0))
            return usd_free + total
        except Exception as e:
            print("Portfolio fetch error:", e)
            return 0.0

    def run(self):
        print("Bot main loop started (checks every 60s)...")
        while True:
            try:
                for i, coin in enumerate(COINS):
                    bin_sym = BINANCE_SYMBOLS[i]
                    roo_pair = ROOSTOO_PAIRS[i]

                    df = self.fetch_latest_klines(bin_sym)
                    if len(df) < 20:
                        continue

                    features = self.build_features(df)

                    # Simulate last realized 5m return for training (past data only)
                    realized_5m = np.log(df['close'].iloc[-1] / df['close'].iloc[-6]) if len(df) >= 6 else 0.0

                    # Update history & rolling OLS (correct lagged)
                    self.history[coin].append((features, realized_5m))
                    hat_r = 0.0
                    if len(self.history[coin]) > PARAMS['K'] + 10:
                        data = list(self.history[coin])
                        X = np.array([d[0] for d in data[:-5]])
                        y = np.array([d[1] for d in data[:-5]])
                        if len(y) >= 30 and np.std(y) > 1e-8:
                            beta = np.linalg.lstsq(X, y, rcond=None)[0]
                            hat_r = np.dot(beta, features)

                    # Volatility
                    v = np.log(df['high'].iloc[-1] / df['low'].iloc[-1]) if df['low'].iloc[-1] > 0 else 0.001
                    parkinson = np.sqrt(max(v, 1e-12)) / (4 * np.log(2))
                    self.sigma[coin] = PARAMS['lambda_sigma'] * self.sigma[coin] + (1 - PARAMS['lambda_sigma']) * parkinson

                    TI = features[2]

                    # Entry / Exit (exact PDF)
                    if hat_r > PARAMS['cost_buffer'] and TI > PARAMS['liq_log']:
                        p_target = min(1.0, PARAMS['target_vol'] / max(self.sigma[coin], 1e-8))
                    else:
                        p_target = 0.0

                    # Rebalance with hysteresis + EXCHANGE RULE COMPLIANCE
                    if abs(p_target - self.position[coin]) > PARAMS['hysteresis']:
                        delta = p_target - self.position[coin]
                        side = "BUY" if delta > 0 else "SELL"

                        # Respect MiniOrder and AmountPrecision
                        rules = self.rules.get(roo_pair, {"amount_prec": 6, "min_order": 0.0001})
                        raw_qty = abs(delta) * 0.05   # base allocation example
                        qty = max(rules["min_order"], round(raw_qty, rules["amount_prec"]))

                        if qty < rules["min_order"]:
                            qty = rules["min_order"]   # enforce minimum

                        order_resp = self.api.place_order(
                            pair=roo_pair,
                            side=side,
                            type_="MARKET",
                            quantity=qty
                        )

                        print(f"\n🔥 TRADE EXECUTED on {roo_pair} | Side: {side} | Qty: {qty}")
                        print("Full place_order() response:")
                        print(json.dumps(order_resp, indent=2))

                        self.position[coin] = p_target

                # Portfolio every 10 minutes
                if time.time() - self.last_portfolio_print > 600:
                    value = self.get_portfolio_value()
                    pos_str = " | ".join([f"{c}:{self.position[c]:.4f}" for c in COINS])
                    print(f"\n📊 [{datetime.now(ZoneInfo('Asia/Hong_Kong')).strftime('%Y %b %d %H:%M:%S')}] Portfolio Value = ${value:,.2f} | Positions: {pos_str}")
                    self.last_portfolio_print = time.time()

                time.sleep(60)

            except Exception as e:
                print("Loop error:", e)
                time.sleep(10)


if __name__ == "__main__":
    bot = MultiCoinSTBAIBot()
    bot.run()
