"""
coinbase_client.py
──────────────────
Wrapper around the Coinbase Advanced Trade API.
Handles: account balances, price quotes, market orders, order status.
"""

import uuid
import logging
from coinbase.rest import RESTClient
from config import COINBASE_API_KEY, COINBASE_API_SECRET, MAX_TRADE_AMOUNT

log = logging.getLogger(__name__)


class CoinbaseClient:
    def __init__(self):
        self.client = RESTClient(
            api_key=COINBASE_API_KEY,
            api_secret=COINBASE_API_SECRET,
        )

    # ─── ACCOUNT ────────────────────────────────────────────────────────────

    def get_accounts(self):
        """Return list of all accounts with non-zero balances."""
        try:
            resp = self.client.get_accounts()
            accounts = []
            for acct in resp["accounts"]:
                balance = float(acct["available_balance"]["value"])
                if balance > 0:
                    accounts.append({
                        "currency": acct["currency"],
                        "balance":  round(balance, 8),
                    })
            return accounts
        except Exception as e:
            log.error(f"get_accounts error: {e}")
            return []

    def get_balance(self, currency="USD"):
        """Return available balance for a specific currency."""
        accounts = self.get_accounts()
        for acct in accounts:
            if acct["currency"] == currency:
                return acct["balance"]
        return 0.0

    # ─── PRICE ──────────────────────────────────────────────────────────────

    def get_price(self, product_id="BTC-USD"):
        """Return current best bid/ask and mid price."""
        try:
            resp = self.client.get_best_bid_ask(product_ids=[product_id])
            pricebook = resp["pricebooks"][0]
            best_bid = float(pricebook["bids"][0]["price"])
            best_ask = float(pricebook["asks"][0]["price"])
            mid = round((best_bid + best_ask) / 2, 2)
            return {"bid": best_bid, "ask": best_ask, "mid": mid}
        except Exception as e:
            log.error(f"get_price error: {e}")
            return None

    def get_candles(self, product_id="BTC-USD", granularity="ONE_HOUR", limit=100):
        """Return recent OHLCV candles."""
        try:
            resp = self.client.get_candles(
                product_id=product_id,
                granularity=granularity,
                limit=limit,
            )
            return resp.get("candles", [])
        except Exception as e:
            log.error(f"get_candles error: {e}")
            return []

    # ─── ORDERS ─────────────────────────────────────────────────────────────

    def _safe_amount(self, amount: float):
        """Clamp order amount to configured maximum."""
        return min(round(amount, 2), MAX_TRADE_AMOUNT)

    def market_buy(self, product_id="BTC-USD", usd_amount=10.0):
        """Place a market buy order for a USD amount."""
        amount = self._safe_amount(usd_amount)
        order_id = str(uuid.uuid4())
        try:
            resp = self.client.market_order_buy(
                client_order_id=order_id,
                product_id=product_id,
                quote_size=str(amount),
            )
            log.info(f"MARKET BUY {product_id} ${amount} | order_id={order_id}")
            return resp
        except Exception as e:
            log.error(f"market_buy error: {e}")
            return None

    def market_sell(self, product_id="BTC-USD", usd_amount=10.0):
        """Place a market sell order for a USD amount (converted to base size)."""
        price_data = self.get_price(product_id)
        if not price_data:
            log.error("Cannot sell — price unavailable")
            return None

        amount = self._safe_amount(usd_amount)
        base_size = round(amount / price_data["mid"], 8)
        order_id = str(uuid.uuid4())

        try:
            resp = self.client.market_order_sell(
                client_order_id=order_id,
                product_id=product_id,
                base_size=str(base_size),
            )
            log.info(f"MARKET SELL {product_id} ~${amount} ({base_size}) | order_id={order_id}")
            return resp
        except Exception as e:
            log.error(f"market_sell error: {e}")
            return None

    def limit_sell(self, product_id: str, base_size: float, limit_price: float,
                   label: str = "LIMIT"):
        """Place a limit sell order — used for take profit."""
        order_id = str(uuid.uuid4())
        try:
            resp = self.client.limit_order_gtc_sell(
                client_order_id=order_id,
                product_id=product_id,
                base_size=str(round(base_size, 8)),
                limit_price=str(round(limit_price, 2)),
            )
            log.info(f"{label} SELL {product_id} size={base_size} @ ${limit_price}")
            return resp
        except Exception as e:
            log.error(f"limit_sell error: {e}")
            return None

    def stop_limit_sell(self, product_id: str, base_size: float,
                        stop_price: float, limit_price: float):
        """Place a stop-limit sell order — used for stop loss."""
        order_id = str(uuid.uuid4())
        try:
            resp = self.client.stop_limit_order_gtc_sell(
                client_order_id=order_id,
                product_id=product_id,
                base_size=str(round(base_size, 8)),
                stop_price=str(round(stop_price, 2)),
                limit_price=str(round(limit_price * 0.998, 2)),  # 0.2% below stop
            )
            log.info(f"STOP-LIMIT SELL {product_id} stop=${stop_price} limit=${limit_price}")
            return resp
        except Exception as e:
            log.error(f"stop_limit_sell error: {e}")
            return None

    def execute_full_trade(self, product_id: str, usd_amount: float,
                           stop_loss: float, take_profit: float) -> dict:
        """
        Execute a full trade: market buy + stop loss + take profit orders.
        Returns dict with all order results.
        """
        buy_result = self.market_buy(product_id, usd_amount)
        if not buy_result:
            return {"error": "Market buy failed"}

        price_data  = self.get_price(product_id)
        fill_price  = price_data["mid"] if price_data else usd_amount
        base_size   = round(usd_amount / fill_price, 8)

        sl_result = None
        tp_result = None

        if stop_loss:
            sl_result = self.stop_limit_sell(product_id, base_size, stop_loss, stop_loss)

        if take_profit:
            tp_result = self.limit_sell(product_id, base_size, take_profit, "TAKE_PROFIT")

        return {
            "buy":         buy_result,
            "stop_loss":   sl_result,
            "take_profit": tp_result,
            "base_size":   base_size,
            "fill_price":  fill_price,
        }

    def get_order(self, order_id: str):
        """Look up a specific order by ID."""
        try:
            return self.client.get_order(order_id=order_id)
        except Exception as e:
            log.error(f"get_order error: {e}")
            return None

    def list_open_orders(self, product_id=None):
        """Return all open orders, optionally filtered by product."""
        try:
            kwargs = {"order_status": ["OPEN"]}
            if product_id:
                kwargs["product_id"] = product_id
            resp = self.client.list_orders(**kwargs)
            return resp.get("orders", [])
        except Exception as e:
            log.error(f"list_open_orders error: {e}")
            return []

    # ─── SWING HIGH / LOW (for Fibonacci) ───────────────────────────────────

    def get_swing_high_low(self, product_id="BTC-USD", granularity="ONE_HOUR", periods=50):
        """
        Calculate swing high and swing low from recent candles.
        Used by signal_generator to compute Fibonacci levels.
        """
        candles = self.get_candles(product_id, granularity, periods)
        if not candles:
            return None, None

        highs = [float(c["high"]) for c in candles]
        lows  = [float(c["low"])  for c in candles]
        return min(lows), max(highs)
