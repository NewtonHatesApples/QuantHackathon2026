import hmac
import hashlib
import time
import urllib.parse
import os
import requests
from typing import Dict, Any, Optional, List


class RoostooAPI:
    """
    Python client for Roostoo Mock Public API[](https://mock-api.roostoo.com).

    Supports all documented endpoints as of the latest README in
    https://github.com/roostoo/Roostoo-API-Documents

    ** Rate Limit: 30 - 60 requests per minute **

    Usage:
        api = RoostooAPI(api_key=os.environ.get("API_KEY"), api_secret=os.environ.get("API_SECRET"))
        server_time = api.get_server_time()
        ticker = api.get_ticker("BTC/USD")
        balance = api.get_balance()
    """

    BASE_URL = "https://mock-api.roostoo.com/v3"

    def __init__(self, api_key: Optional[str] = None, api_secret: Optional[str] = None, timeout: int = 15):
        self.api_key = api_key
        self.api_secret = api_secret
        self.session = requests.Session()
        self.session.headers.update({"Content-Type": "application/x-www-form-urlencoded"})
        self.timeout = timeout

    def _sign_request(self, params: Dict[str, Any]) -> str:
        """Create MSG-SIGNATURE using HMAC-SHA256 of raw sorted params (NO urlencode)."""
        if not self.api_secret:
            raise ValueError("api_secret is required for signed requests")

        # Force everything to str (timestamp was int, quantity already str, etc.)
        str_params = {k: str(v) for k, v in params.items()}
        sorted_params = sorted(str_params.items())  # alphabetical by key
        query_string = "&".join(f"{k}={v}" for k, v in sorted_params)

        signature = hmac.new(self.api_secret.encode('utf-8'), query_string.encode('utf-8'), hashlib.sha256).hexdigest()
        return signature

    def _request(self, method: str, endpoint: str, params: Optional[Dict[str, Any]] = None, require_auth: bool = False, require_ts: bool = False) -> Dict[str, Any]:
        url = f"{self.BASE_URL}/{endpoint.lstrip('/')}"
        params = params or {}

        if require_ts or require_auth:
            params["timestamp"] = int(time.time() * 1000)
            params = dict(sorted(params.items()))

        headers = {}
        if require_auth:
            if not self.api_key:
                raise ValueError("api_key is required for authenticated endpoints")

            headers["RST-API-KEY"] = self.api_key
            headers["MSG-SIGNATURE"] = self._sign_request(params)

        if method.upper() == "GET":
            response = self.session.get(url, params=params, headers=headers, timeout=self.timeout)
        elif method.upper() == "POST":
            str_params = {k: str(v) for k, v in params.items()}
            sorted_params = sorted(str_params.items())
            body = "&".join(f"{k}={v}" for k, v in sorted_params)
            headers["Content-Type"] = "application/x-www-form-urlencoded"
            response = self.session.post(url, data=body, headers=headers, timeout=self.timeout)
        else:
            raise ValueError(f"Unsupported method: {method}")

        response.raise_for_status()
        return response.json()

    # ── Public Endpoints (No auth) ──────────────────────────────────────────────

    def get_server_time(self) -> Dict[str, Any]:
        """GET /v3/serverTime — Test connectivity & get server time."""
        return self._request("GET", "serverTime")

    def get_exchange_info(self) -> Dict[str, Any]:
        """GET /v3/exchangeInfo — Trading rules, symbols, precision, min sizes."""
        return self._request("GET", "exchangeInfo")

    # ── Timestamp Check Endpoints ───────────────────────────────────────────────

    def get_ticker(self, pair: Optional[str] = None) -> Dict[str, Any]:
        """
        GET /v3/ticker — 24hr ticker data.

        pair: e.g. "BTC/USD" (optional → returns all pairs)
        """
        params = {}
        if pair:
            params["pair"] = pair
        resp = self._request("GET", "ticker", params=params, require_ts=True)
        return resp.get("Data")

    # ── Fully Authenticated Endpoints (RCL_TopLevelCheck) ───────────────────────

    def get_balance(self) -> Dict[str, Any]:
        """GET /v3/balance — Free & locked balances per asset."""

        resp = self._request("GET", "balance", require_auth=True)
        return resp.get("SpotWallet")

    def get_pending_count(self) -> Dict[str, Any]:
        """GET /v3/pending_count — Number of pending orders (total + per pair)."""
        return self._request("GET", "pending_count", require_auth=True)

    def place_order(self, pair: str, side: str, type_: str, quantity: float, price: Optional[float] = None) -> Dict[str, Any]:
        """
        POST /v3/place_order — Place new order
        :param pair: E.g. "BTC/USD".
        :param side: Must be "BUY" or "SELL".
        :param type_: Must be "LIMIT" or "MARKET".
        :param quantity: Amount you want to trade. At least `AmountPrecision`. See `GET /v3/exchangeInfo`.
        :param price: Required for limit order.
        Returns: OrderID, Status, FilledQuantity, etc.
        """
        params = {
            "pair": pair,
            "side": side.upper(),
            "type": type_.upper(),
            "quantity": str(quantity),  # API expects string for precision
        }
        if type_.upper() == "LIMIT":
            if price is None:
                raise ValueError("price is required for LIMIT orders")
            params["price"] = str(price)
        return self._request("POST", "place_order", params=params, require_auth=True)

    def query_order(self, order_id: Optional[int] = None, pair: Optional[str] = None, pending_only: bool = False, limit: int = 100, offset: int = 0) -> List[Dict[str, Any]]:
        """
        POST /v3/query_order — Query orders by ID or filters.

        Returns list of order objects.
        """
        params = {"limit": str(limit), "offset": str(offset)}
        if order_id is not None:
            params["order_id"] = str(order_id)
        if pair:
            params["pair"] = pair
        if pending_only:
            params["pending_only"] = "true"

        resp = self._request("POST", "query_order", params=params, require_auth=True)
        # Assuming response is {"orders": [...]} or direct list — adjust if needed
        return resp.get("OrderMatched", resp) if isinstance(resp, dict) else resp

    def cancel_order(self, order_id: Optional[int] = None, pair: Optional[str] = None) -> Dict[str, Any]:
        """
        POST /v3/cancel_order — Cancel specific order, pair's orders, or ALL pending.

        Provide order_id OR pair OR neither (cancels all pending).
        """
        params = {}
        if order_id is not None:
            params["order_id"] = str(order_id)
        if pair:
            params["pair"] = pair

        return self._request("POST", "cancel_order", params=params, require_auth=True)


# ── Example usage ────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    # Store API_KEY and API_SECRET into .env files first
    api = RoostooAPI(api_key=os.environ.get("API_KEY"), api_secret=os.environ.get("API_SECRET"))

    print("Server time:", api.get_server_time())
    print("Exchange info:", api.get_exchange_info())
    print("BTC/USD ticker:", api.get_ticker("BTC/USD"))

    # Signed calls (will fail without valid keys)
    # print(api.get_balance())
    # print(api.place_order("BTC/USD", "BUY", "LIMIT", 0.001, 50000))
