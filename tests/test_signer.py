"""
Tests unitarios para la firma HMAC-SHA256 de peticiones Binance.

Usa credenciales de test inyectadas (no toca ``~/.panzer_creds``).
No requiere conexion a internet.
"""

from __future__ import annotations

import hashlib
import hmac
import os
import time

import pytest

from panzer.credentials import CredentialManager
from panzer.exchanges.binance.signer import BinanceRequestSigner

# =====================================================================
# Fixtures
# =====================================================================

TEST_API_KEY = "vmPUZE6mv9SD5VNHk4HlWFsOr6aKE2zvsw0MuIgwCIPy6utIco14y7Ju91duEh8A"
TEST_API_SECRET = "NhqPtmdSJYdKjVHjA7PZj4Mge3R5YNiP1e3UZjInClVN65XAbvqqM6A7H5fATj0j"


@pytest.fixture()
def signer(tmp_path: object) -> BinanceRequestSigner:
    """Signer con credenciales de test en archivo temporal."""
    filepath = os.path.join(str(tmp_path), ".panzer_test_creds")
    cm = CredentialManager.__new__(CredentialManager)
    from panzer.crypto import AesCipher

    cm._cipher = AesCipher()
    cm._cache = {}
    cm._filepath = filepath
    cm._ensure_file()
    cm.add("api_key", TEST_API_KEY)
    cm.add("api_secret", TEST_API_SECRET)
    return BinanceRequestSigner(credentials=cm)


# =====================================================================
# Propiedades de la API key
# =====================================================================

class TestSignerCredentials:
    """Acceso a credenciales descifradas."""

    def test_api_key(self, signer: BinanceRequestSigner) -> None:
        assert signer.api_key == TEST_API_KEY

    def test_api_secret(self, signer: BinanceRequestSigner) -> None:
        assert signer.api_secret == TEST_API_SECRET


# =====================================================================
# Headers
# =====================================================================

class TestSignerHeaders:
    """Inyeccion de X-MBX-APIKEY en headers."""

    def test_headers_from_none(self, signer: BinanceRequestSigner) -> None:
        h = signer.headers_with_api_key()
        assert h == {"X-MBX-APIKEY": TEST_API_KEY}

    def test_headers_preserve_existing(self, signer: BinanceRequestSigner) -> None:
        h = signer.headers_with_api_key({"Content-Type": "application/json"})
        assert h["X-MBX-APIKEY"] == TEST_API_KEY
        assert h["Content-Type"] == "application/json"

    def test_headers_dont_mutate_input(self, signer: BinanceRequestSigner) -> None:
        original = {"Custom": "value"}
        signer.headers_with_api_key(original)
        assert "X-MBX-APIKEY" not in original


# =====================================================================
# Firma de parametros
# =====================================================================

class TestSignParams:
    """Firma HMAC-SHA256 de parametros."""

    def test_adds_timestamp_and_signature(self, signer: BinanceRequestSigner) -> None:
        params = [("symbol", "BTCUSDT")]
        signed = signer.sign_params(params)
        keys = [k for k, _ in signed]
        assert "timestamp" in keys
        assert "signature" in keys
        assert len(signed) == 3

    def test_signature_is_sha256_hex(self, signer: BinanceRequestSigner) -> None:
        signed = signer.sign_params([("symbol", "BTCUSDT")])
        sig = signed[-1][1]
        assert isinstance(sig, str)
        assert len(sig) == 64  # SHA256 hex = 64 chars
        # Debe ser hex valido
        int(sig, 16)

    def test_timestamp_is_recent_ms(self, signer: BinanceRequestSigner) -> None:
        before = int(time.time() * 1000)
        signed = signer.sign_params([("symbol", "ETHUSDT")])
        after = int(time.time() * 1000)
        ts = dict(signed)["timestamp"]
        assert before <= ts <= after

    def test_no_duplicate_timestamp(self, signer: BinanceRequestSigner) -> None:
        """Si ya viene timestamp, no lo duplica."""
        params = [("symbol", "BTCUSDT"), ("timestamp", 1234567890)]
        signed = signer.sign_params(params)
        ts_count = sum(1 for k, _ in signed if k == "timestamp")
        assert ts_count == 1
        assert dict(signed)["timestamp"] == 1234567890

    def test_skip_timestamp(self, signer: BinanceRequestSigner) -> None:
        signed = signer.sign_params(
            [("symbol", "BTCUSDT")],
            add_timestamp=False,
        )
        keys = [k for k, _ in signed]
        assert "timestamp" not in keys
        assert "signature" in keys

    def test_server_time_offset(self, signer: BinanceRequestSigner) -> None:
        """El offset se suma al timestamp."""
        offset = 5000
        before = int(time.time() * 1000) + offset
        signed = signer.sign_params(
            [("symbol", "BTCUSDT")],
            server_time_offset_ms=offset,
        )
        after = int(time.time() * 1000) + offset
        ts = dict(signed)["timestamp"]
        assert before <= ts <= after

    def test_does_not_mutate_input(self, signer: BinanceRequestSigner) -> None:
        params = [("symbol", "BTCUSDT")]
        original_len = len(params)
        signer.sign_params(params)
        assert len(params) == original_len

    def test_multiple_params(self, signer: BinanceRequestSigner) -> None:
        params = [
            ("symbol", "BTCUSDT"),
            ("side", "BUY"),
            ("type", "LIMIT"),
            ("quantity", "0.001"),
            ("price", "50000"),
            ("timeInForce", "GTC"),
        ]
        signed = signer.sign_params(params)
        # 6 originales + timestamp + signature = 8
        assert len(signed) == 8

    def test_signature_verification(self, signer: BinanceRequestSigner) -> None:
        """Verificar manualmente que la firma HMAC es correcta."""
        params = [("symbol", "BTCUSDT"), ("timestamp", 1000000000000)]
        signed = signer.sign_params(params, add_timestamp=False)

        # Recalcular la firma manualmente
        query = "symbol=BTCUSDT&timestamp=1000000000000"
        expected_sig = hmac.new(
            key=TEST_API_SECRET.encode(),
            msg=query.encode(),
            digestmod=hashlib.sha256,
        ).hexdigest()

        actual_sig = dict(signed)["signature"]
        assert actual_sig == expected_sig


# =====================================================================
# Endpoints privados por mercado
# =====================================================================

class TestPrivateEndpoints:
    """Resolucion de endpoints privados en BinanceClient."""

    def test_spot_endpoints(self) -> None:
        from panzer.exchanges.binance.client import _PRIVATE_ENDPOINTS

        spot = _PRIVATE_ENDPOINTS["spot"]
        assert spot["account"] == "/api/v3/account"
        assert spot["order"] == "/api/v3/order"
        assert spot["my_trades"] == "/api/v3/myTrades"
        assert spot["open_orders"] == "/api/v3/openOrders"
        assert spot["all_orders"] == "/api/v3/allOrders"

    def test_um_endpoints(self) -> None:
        from panzer.exchanges.binance.client import _PRIVATE_ENDPOINTS

        um = _PRIVATE_ENDPOINTS["um"]
        assert um["account"] == "/fapi/v2/account"
        assert um["order"] == "/fapi/v1/order"

    def test_cm_endpoints(self) -> None:
        from panzer.exchanges.binance.client import _PRIVATE_ENDPOINTS

        cm = _PRIVATE_ENDPOINTS["cm"]
        assert cm["account"] == "/dapi/v1/account"
        assert cm["order"] == "/dapi/v1/order"

    def test_all_markets_have_same_keys(self) -> None:
        from panzer.exchanges.binance.client import _PRIVATE_ENDPOINTS

        keys = None
        for market in ("spot", "um", "cm"):
            market_keys = set(_PRIVATE_ENDPOINTS[market].keys())
            if keys is None:
                keys = market_keys
            else:
                assert market_keys == keys, f"{market} tiene claves distintas"
