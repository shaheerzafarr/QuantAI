"""Live Binance USDT-M Perpetual Futures Execution Client.

Provides direct authenticated REST and CCXT execution for real-money trading,
including precision formatting, isolated leverage controls, bracket TP/SL orders,
live balance synchronization, and position reconciliation.
"""

import hashlib
import hmac
import logging
import os
import time
from typing import Any, Dict, List, Optional
import ccxt
import requests

from quantai.config.settings import get_config

logger = logging.getLogger("quantai.execution.binance_live")


class BinanceLiveFuturesExecutor:
    """Manages real-money order routing and position lifecycle on Binance Futures."""

    def __init__(
        self,
        api_key: Optional[str] = None,
        api_secret: Optional[str] = None,
        default_leverage: int = 3,
        default_margin_mode: str = "ISOLATED",
    ):
        self.config = get_config()
        self.api_key = api_key or self.config.exchange.api_key or os.getenv("BINANCE_API_KEY", "")
        self.api_secret = api_secret or self.config.exchange.api_secret or os.getenv("BINANCE_API_SECRET", "")
        self.default_leverage = default_leverage
        self.default_margin_mode = default_margin_mode

        if not self.api_key or not self.api_secret:
            logger.warning("Binance API credentials missing. Live executor running in unauthenticated mode.")
            self.exchange = None
        else:
            self.exchange = ccxt.binance({
                "apiKey": self.api_key,
                "secret": self.api_secret,
                "options": {
                    "defaultType": "future",
                    "adjustForTimeDifference": True,
                },
                "enableRateLimit": True,
            })

        self._markets_loaded = False

    def load_markets_safe(self):
        """Loads Binance markets metadata once."""
        if self.exchange and not self._markets_loaded:
            try:
                self.exchange.load_markets()
                self._markets_loaded = True
            except Exception as e:
                logger.warning(f"Error loading Binance markets metadata: {e}")

    def check_api_permissions(self) -> Dict[str, Any]:
        """Queries Binance API restriction status to verify Futures trading capability."""
        if not self.api_key or not self.api_secret:
            return {
                "authenticated": False,
                "can_read": False,
                "can_trade_futures": False,
                "can_trade_spot": False,
                "reason": "Missing API Key or Secret",
            }

        headers = {"X-MBX-APIKEY": self.api_key}
        ts = int(time.time() * 1000)
        query = f"timestamp={ts}"
        sig = hmac.new(self.api_secret.encode("utf-8"), query.encode("utf-8"), hashlib.sha256).hexdigest()
        url = f"https://api.binance.com/sapi/v1/account/apiRestrictions?{query}&signature={sig}"

        try:
            r = requests.get(url, headers=headers, timeout=10)
            if r.status_code == 200:
                data = r.json()
                return {
                    "authenticated": True,
                    "can_read": data.get("enableReading", False),
                    "can_trade_futures": data.get("enableFutures", False),
                    "can_trade_spot": data.get("enableSpotAndMarginTrading", False),
                    "ip_restricted": data.get("ipRestrict", False),
                    "reason": "OK" if data.get("enableFutures") else "Futures trading permission disabled on API key",
                }
            return {
                "authenticated": False,
                "can_read": False,
                "can_trade_futures": False,
                "reason": f"HTTP {r.status_code}: {r.text}",
            }
        except Exception as e:
            return {
                "authenticated": False,
                "can_read": False,
                "can_trade_futures": False,
                "reason": str(e),
            }

    def get_live_futures_balance(self) -> Dict[str, float]:
        """Fetches live USDT wallet and margin balance from Binance Futures."""
        if not self.exchange:
            return {"total_usdt": 0.0, "free_usdt": 0.0, "used_usdt": 0.0}

        try:
            balance = self.exchange.fetch_balance()
            usdt = balance.get("USDT", {})
            return {
                "total_usdt": float(usdt.get("total", 0.0) or 0.0),
                "free_usdt": float(usdt.get("free", 0.0) or 0.0),
                "used_usdt": float(usdt.get("used", 0.0) or 0.0),
            }
        except Exception as e:
            logger.error(f"Failed to fetch Binance Futures balance: {e}")
            return {"total_usdt": 0.0, "free_usdt": 0.0, "used_usdt": 0.0}

    def _normalize_symbol(self, pair: str) -> str:
        """Converts standard 'BTC/USDT' or 'BTCUSDT' into CCXT perpetual symbol 'BTC/USDT:USDT'."""
        clean = pair.strip().upper()
        if ":" in clean:
            return clean
        if "/" in clean:
            return f"{clean}:USDT"
        if clean.endswith("USDT"):
            return f"{clean[:-4]}/USDT:USDT"
        return f"{clean}/USDT:USDT"

    def setup_symbol_margin_and_leverage(self, symbol: str, leverage: Optional[int] = None) -> bool:
        """Ensures isolated margin mode and target leverage are set for the perpetual contract."""
        if not self.exchange:
            return False

        lev = leverage or self.default_leverage
        ccxt_symbol = self._normalize_symbol(symbol)

        try:
            self.exchange.set_leverage(lev, ccxt_symbol)
            logger.info(f"Set leverage {lev}x for {ccxt_symbol} successfully.")
        except Exception as e:
            err_msg = str(e)
            if "No need to change leverage" not in err_msg and "-2015" not in err_msg:
                logger.debug(f"Leverage notice for {ccxt_symbol}: {e}")

        try:
            self.exchange.set_margin_mode(self.default_margin_mode, ccxt_symbol)
            logger.info(f"Set margin mode {self.default_margin_mode} for {ccxt_symbol}.")
        except Exception as e:
            err_msg = str(e)
            if "No need to change margin type" not in err_msg and "-2015" not in err_msg:
                logger.debug(f"Margin mode notice for {ccxt_symbol}: {e}")

        return True

    def calculate_order_quantity(
        self,
        symbol: str,
        notional_usd: float,
        current_price: float,
    ) -> float:
        """Calculates exchange-compliant order quantity conforming to lot stepSize and minNotional."""
        self.load_markets_safe()
        ccxt_symbol = self._normalize_symbol(symbol)
        market = self.exchange.markets.get(ccxt_symbol) if self.exchange and self.exchange.markets else None

        min_cost = 5.0
        min_amount = 0.001
        amount_precision = 0.001

        if market:
            limits = market.get("limits", {})
            min_cost = float(limits.get("cost", {}).get("min") or 5.0)
            min_amount = float(limits.get("amount", {}).get("min") or 0.001)
            prec = market.get("precision", {})
            amount_precision = prec.get("amount", 0.001)

        # Enforce minimum cost
        effective_notional = max(notional_usd, min_cost)
        raw_qty = effective_notional / current_price
        target_qty = max(raw_qty, min_amount)

        if self.exchange:
            try:
                formatted_qty = float(self.exchange.amount_to_precision(ccxt_symbol, target_qty))
                return formatted_qty
            except Exception:
                pass

        # Fallback rounding to decimal places based on precision
        if isinstance(amount_precision, float) and amount_precision < 1:
            import math
            decimals = max(0, -int(math.floor(math.log10(amount_precision))))
            return round(target_qty, decimals)
        elif isinstance(amount_precision, int):
            return round(target_qty, amount_precision)
        return round(target_qty, 4)

    def execute_live_entry(
        self,
        symbol: str,
        side: str,  # "BUY" or "SELL" / "LONG" or "SHORT"
        notional_usd: float,
        current_price: float,
        leverage: Optional[int] = None,
        stop_loss_price: Optional[float] = None,
        take_profit_price: Optional[float] = None,
    ) -> Dict[str, Any]:
        """Places a real-money market entry order on Binance USDT-M Futures."""
        if not self.exchange:
            return {
                "success": False,
                "order_id": None,
                "error": "Exchange client not initialized",
            }

        perms = self.check_api_permissions()
        if not perms.get("can_trade_futures", False):
            return {
                "success": False,
                "order_id": None,
                "error": f"Binance API permission check failed: {perms.get('reason')}",
                "perms": perms,
            }

        ccxt_symbol = self._normalize_symbol(symbol)
        order_side = "buy" if side.upper() in ["BUY", "LONG"] else "sell"
        lev = leverage or self.default_leverage

        # 1. Setup leverage
        self.setup_symbol_margin_and_leverage(symbol=symbol, leverage=lev)

        # 2. Format precise order quantity
        qty = self.calculate_order_quantity(
            symbol=symbol,
            notional_usd=notional_usd,
            current_price=current_price,
        )

        logger.info(
            f"SUBMITTING REAL-MONEY BINANCE FUTURES ORDER: {order_side.upper()} {qty} {ccxt_symbol} (Notional: ~${qty * current_price:,.2f})"
        )

        try:
            order = self.exchange.create_market_order(
                symbol=ccxt_symbol,
                side=order_side,
                amount=qty,
            )
            order_id = str(order.get("id"))
            filled_qty = float(order.get("filled", qty) or qty)
            avg_price = float(order.get("average", current_price) or current_price)

            logger.info(
                f"✅ BINANCE FUTURES ORDER FILLED: ID={order_id} | {order_side.upper()} {filled_qty} @ ${avg_price:,.4f}"
            )

            # 3. Submit bracket conditional orders if requested
            sl_order_id = None
            tp_order_id = None
            exit_side = "sell" if order_side == "buy" else "buy"

            if stop_loss_price:
                try:
                    sl_order = self.exchange.create_order(
                        symbol=ccxt_symbol,
                        type="STOP_MARKET",
                        side=exit_side,
                        amount=filled_qty,
                        params={"stopPrice": self.exchange.price_to_precision(ccxt_symbol, stop_loss_price), "reduceOnly": True},
                    )
                    sl_order_id = str(sl_order.get("id"))
                except Exception as e:
                    logger.warning(f"Could not submit STOP_MARKET order on Binance: {e}")

            if take_profit_price:
                try:
                    tp_order = self.exchange.create_order(
                        symbol=ccxt_symbol,
                        type="TAKE_PROFIT_MARKET",
                        side=exit_side,
                        amount=filled_qty,
                        params={"stopPrice": self.exchange.price_to_precision(ccxt_symbol, take_profit_price), "reduceOnly": True},
                    )
                    tp_order_id = str(tp_order.get("id"))
                except Exception as e:
                    logger.warning(f"Could not submit TAKE_PROFIT_MARKET order on Binance: {e}")

            return {
                "success": True,
                "order_id": order_id,
                "symbol": ccxt_symbol,
                "side": order_side.upper(),
                "filled_qty": filled_qty,
                "avg_price": avg_price,
                "stop_loss_order_id": sl_order_id,
                "take_profit_order_id": tp_order_id,
                "raw": order,
            }

        except Exception as e:
            logger.error(f"❌ Real-money Binance Futures order failed: {e}", exc_info=True)
            return {
                "success": False,
                "order_id": None,
                "error": str(e),
            }

    def execute_live_close(
        self,
        symbol: str,
        side: str,  # Original trade side: "LONG" -> close with "SELL", "SHORT" -> close with "BUY"
        amount: float,
    ) -> Dict[str, Any]:
        """Closes an open real-money position on Binance Futures with a reduce-only market order."""
        if not self.exchange:
            return {"success": False, "error": "Exchange not initialized"}

        ccxt_symbol = self._normalize_symbol(symbol)
        close_side = "sell" if side.upper() in ["BUY", "LONG"] else "buy"

        try:
            # 1. Cancel any open conditional/trigger orders
            try:
                self.exchange.cancel_all_orders(ccxt_symbol)
            except Exception as e:
                logger.debug(f"Cancel orders notice for {ccxt_symbol}: {e}")

            # 2. Place market close order with reduceOnly
            close_order = self.exchange.create_order(
                symbol=ccxt_symbol,
                type="MARKET",
                side=close_side,
                amount=amount,
                params={"reduceOnly": True},
            )
            order_id = str(close_order.get("id"))
            avg_price = float(close_order.get("average", 0.0) or 0.0)
            logger.info(f"✅ BINANCE POSITION CLOSED: ID={order_id} | {ccxt_symbol} | Fill: ${avg_price:,.4f}")
            return {
                "success": True,
                "order_id": order_id,
                "exit_price": avg_price,
                "raw": close_order,
            }
        except Exception as e:
            logger.error(f"❌ Failed to close Binance position on {ccxt_symbol}: {e}")
            return {"success": False, "error": str(e)}

    def fetch_active_positions(self) -> List[Dict[str, Any]]:
        """Queries Binance Futures to retrieve all currently open contracts."""
        if not self.exchange:
            return []

        try:
            positions = self.exchange.fetch_positions()
            active = []
            for p in positions:
                contracts = float(p.get("contracts", 0.0) or 0.0)
                if contracts > 0:
                    active.append({
                        "symbol": p.get("symbol"),
                        "side": p.get("side", "").upper(),
                        "contracts": contracts,
                        "notional": float(p.get("notional", 0.0) or 0.0),
                        "entry_price": float(p.get("entryPrice", 0.0) or 0.0),
                        "mark_price": float(p.get("markPrice", 0.0) or 0.0),
                        "unrealized_pnl": float(p.get("unrealizedPnl", 0.0) or 0.0),
                        "liquidation_price": float(p.get("liquidationPrice", 0.0) or 0.0),
                        "leverage": int(p.get("leverage", 3) or 3),
                    })
            return active
        except Exception as e:
            logger.error(f"Error fetching active positions from Binance: {e}")
            return []

