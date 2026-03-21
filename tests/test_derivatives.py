"""
Tests empiricos de endpoints de derivados (solo futuros).

Verifican estructura e invariantes de: open interest, premium index
(mark price), funding rate history, funding info y force orders.

Datos obtenidos UNA SOLA VEZ por sesion via fixtures en ``conftest.py``.
Cada test se ejecuta para ``"um"`` y ``"cm"``.

Requieren conexion a internet.  Marcados con ``@pytest.mark.empirical``.
"""

from __future__ import annotations

import pytest

from panzer import BinancePublicClient

from .conftest import FuturesTestData

pytestmark = pytest.mark.empirical


# Rango razonable en ms: 2017-01-01 a 2030-01-01
TS_MIN = 1_483_228_800_000
TS_MAX = 1_893_456_000_000


def _label(fd: FuturesTestData) -> str:
    return f"[{fd.market}/{fd.primary_symbol}]"


# =====================================================================
# 1. Open Interest
# =====================================================================

class TestOpenInterest:

    def test_is_dict(self, futures_data: FuturesTestData) -> None:
        assert isinstance(futures_data.open_interest, dict), _label(futures_data)

    def test_has_required_keys(self, futures_data: FuturesTestData) -> None:
        oi = futures_data.open_interest
        for key in ("openInterest", "symbol", "time"):
            assert key in oi, f"{_label(futures_data)} missing key {key!r}"

    def test_symbol_matches(self, futures_data: FuturesTestData) -> None:
        assert futures_data.open_interest["symbol"] == futures_data.primary_symbol

    def test_open_interest_is_numeric_str(self, futures_data: FuturesTestData) -> None:
        val = futures_data.open_interest["openInterest"]
        assert isinstance(val, str), _label(futures_data)
        assert float(val) >= 0

    def test_time_is_valid_ms(self, futures_data: FuturesTestData) -> None:
        ts = futures_data.open_interest["time"]
        assert TS_MIN <= ts <= TS_MAX, f"{_label(futures_data)} time={ts}"


# =====================================================================
# 2. Open Interest History
# =====================================================================

class TestOpenInterestHist:

    def test_is_list(self, futures_data: FuturesTestData) -> None:
        assert isinstance(futures_data.open_interest_hist, list), _label(futures_data)

    def test_non_empty(self, futures_data: FuturesTestData) -> None:
        assert len(futures_data.open_interest_hist) > 0, _label(futures_data)

    def test_each_entry_has_required_keys(self, futures_data: FuturesTestData) -> None:
        for entry in futures_data.open_interest_hist:
            for key in ("sumOpenInterest", "sumOpenInterestValue", "timestamp"):
                assert key in entry, f"{_label(futures_data)} missing {key!r}"

    def test_timestamps_are_valid_ms(self, futures_data: FuturesTestData) -> None:
        for entry in futures_data.open_interest_hist:
            ts = entry["timestamp"]
            assert TS_MIN <= ts <= TS_MAX, f"{_label(futures_data)} ts={ts}"

    def test_timestamps_ascending(self, futures_data: FuturesTestData) -> None:
        timestamps = [e["timestamp"] for e in futures_data.open_interest_hist]
        assert timestamps == sorted(timestamps), _label(futures_data)

    def test_values_are_numeric_str(self, futures_data: FuturesTestData) -> None:
        for entry in futures_data.open_interest_hist:
            assert float(entry["sumOpenInterest"]) >= 0
            assert float(entry["sumOpenInterestValue"]) >= 0


# =====================================================================
# 3. Premium Index (mark price)
# =====================================================================

class TestPremiumIndex:

    def _as_dict(self, fd: FuturesTestData) -> dict:
        """UM con symbol devuelve dict, CM puede devolver lista de un elemento."""
        pi = fd.premium_index
        if isinstance(pi, list):
            assert len(pi) > 0, _label(fd)
            return pi[0]
        return pi

    def test_has_mark_price(self, futures_data: FuturesTestData) -> None:
        pi = self._as_dict(futures_data)
        assert "markPrice" in pi, _label(futures_data)
        assert float(pi["markPrice"]) > 0

    def test_has_index_price(self, futures_data: FuturesTestData) -> None:
        pi = self._as_dict(futures_data)
        assert "indexPrice" in pi, _label(futures_data)
        assert float(pi["indexPrice"]) > 0

    def test_has_last_funding_rate(self, futures_data: FuturesTestData) -> None:
        pi = self._as_dict(futures_data)
        assert "lastFundingRate" in pi, _label(futures_data)
        # Funding rate can be negative
        float(pi["lastFundingRate"])

    def test_has_next_funding_time(self, futures_data: FuturesTestData) -> None:
        pi = self._as_dict(futures_data)
        assert "nextFundingTime" in pi, _label(futures_data)
        nft = pi["nextFundingTime"]
        assert isinstance(nft, int), _label(futures_data)

    def test_symbol_matches(self, futures_data: FuturesTestData) -> None:
        pi = self._as_dict(futures_data)
        assert pi["symbol"] == futures_data.primary_symbol

    def test_mark_and_index_same_magnitude(self, futures_data: FuturesTestData) -> None:
        """Mark price y index price no deberian diferir mas de 10%."""
        pi = self._as_dict(futures_data)
        mark = float(pi["markPrice"])
        index = float(pi["indexPrice"])
        if index > 0:
            ratio = abs(mark - index) / index
            assert ratio < 0.10, (
                f"{_label(futures_data)} mark={mark} index={index} ratio={ratio:.4f}"
            )


# =====================================================================
# 4. Funding Rate History
# =====================================================================

class TestFundingRateHistory:

    def test_is_list(self, futures_data: FuturesTestData) -> None:
        assert isinstance(futures_data.funding_rate_history, list), _label(futures_data)

    def test_non_empty(self, futures_data: FuturesTestData) -> None:
        assert len(futures_data.funding_rate_history) > 0, _label(futures_data)

    def test_each_entry_has_required_keys(self, futures_data: FuturesTestData) -> None:
        for entry in futures_data.funding_rate_history:
            for key in ("symbol", "fundingRate", "fundingTime"):
                assert key in entry, f"{_label(futures_data)} missing {key!r}"

    def test_symbol_matches(self, futures_data: FuturesTestData) -> None:
        for entry in futures_data.funding_rate_history:
            assert entry["symbol"] == futures_data.primary_symbol

    def test_funding_rate_is_numeric_str(self, futures_data: FuturesTestData) -> None:
        for entry in futures_data.funding_rate_history:
            float(entry["fundingRate"])  # no debe lanzar

    def test_funding_times_are_valid_ms(self, futures_data: FuturesTestData) -> None:
        for entry in futures_data.funding_rate_history:
            ts = entry["fundingTime"]
            assert TS_MIN <= ts <= TS_MAX, f"{_label(futures_data)} ts={ts}"

    def test_funding_times_ascending(self, futures_data: FuturesTestData) -> None:
        times = [e["fundingTime"] for e in futures_data.funding_rate_history]
        assert times == sorted(times), _label(futures_data)


# =====================================================================
# 5. Funding Info
# =====================================================================

class TestFundingInfo:

    def test_is_list(self, futures_data: FuturesTestData) -> None:
        assert isinstance(futures_data.funding_info, list), _label(futures_data)

    def test_non_empty_um(self, futures_data: FuturesTestData) -> None:
        """UM debe tener datos; CM puede devolver lista vacia."""
        if futures_data.market == "cm" and not futures_data.funding_info:
            pytest.skip("CM /fundingInfo returns empty list")
        assert len(futures_data.funding_info) > 0, _label(futures_data)

    def test_contains_primary_symbol(self, futures_data: FuturesTestData) -> None:
        if not futures_data.funding_info:
            pytest.skip("empty funding_info")
        symbols = {e.get("symbol") for e in futures_data.funding_info}
        assert futures_data.primary_symbol in symbols, (
            f"{_label(futures_data)} primary not in funding_info symbols"
        )

    def test_entries_have_funding_interval(self, futures_data: FuturesTestData) -> None:
        if not futures_data.funding_info:
            pytest.skip("empty funding_info")
        for entry in futures_data.funding_info[:5]:
            assert "fundingIntervalHours" in entry, (
                f"{_label(futures_data)} missing fundingIntervalHours in {entry.get('symbol')}"
            )

    def test_funding_interval_is_positive(self, futures_data: FuturesTestData) -> None:
        if not futures_data.funding_info:
            pytest.skip("empty funding_info")
        for entry in futures_data.funding_info[:5]:
            val = entry.get("fundingIntervalHours", 0)
            assert int(val) > 0, (
                f"{_label(futures_data)} fundingIntervalHours={val}"
            )


# =====================================================================
# 6. Force Orders (liquidations)
# =====================================================================

class TestForceOrders:
    """Force orders requiere API key; los tests se saltan si no hay datos."""

    def test_is_list(self, futures_data: FuturesTestData) -> None:
        assert isinstance(futures_data.force_orders, list), _label(futures_data)

    def test_entries_have_expected_keys_if_not_empty(
        self, futures_data: FuturesTestData
    ) -> None:
        if not futures_data.force_orders:
            pytest.skip("no force_orders data (requires API key)")
        for entry in futures_data.force_orders:
            for key in ("symbol", "price", "origQty", "side", "time"):
                assert key in entry, f"{_label(futures_data)} missing {key!r}"

    def test_prices_are_numeric_str(self, futures_data: FuturesTestData) -> None:
        if not futures_data.force_orders:
            pytest.skip("no force_orders data (requires API key)")
        for entry in futures_data.force_orders:
            assert float(entry["price"]) >= 0

    def test_times_are_valid_ms(self, futures_data: FuturesTestData) -> None:
        if not futures_data.force_orders:
            pytest.skip("no force_orders data (requires API key)")
        for entry in futures_data.force_orders:
            ts = entry["time"]
            assert TS_MIN <= ts <= TS_MAX, f"{_label(futures_data)} time={ts}"


# =====================================================================
# 7. Spot market — derivatives endpoints must raise KeyError
# =====================================================================

class TestSpotRaisesKeyError:

    @pytest.fixture(scope="class")
    def spot_client(self) -> BinancePublicClient:
        return BinancePublicClient(market="spot", safety_ratio=0.9)

    def test_open_interest_raises(self, spot_client: BinancePublicClient) -> None:
        with pytest.raises(KeyError):
            spot_client.open_interest("BTCUSDT")

    def test_open_interest_hist_raises(self, spot_client: BinancePublicClient) -> None:
        with pytest.raises(KeyError):
            spot_client.open_interest_hist("BTCUSDT", "5m")

    def test_premium_index_raises(self, spot_client: BinancePublicClient) -> None:
        with pytest.raises(KeyError):
            spot_client.premium_index("BTCUSDT")

    def test_funding_rate_history_raises(self, spot_client: BinancePublicClient) -> None:
        with pytest.raises(KeyError):
            spot_client.funding_rate_history("BTCUSDT")

    def test_funding_info_raises(self, spot_client: BinancePublicClient) -> None:
        with pytest.raises(KeyError):
            spot_client.funding_info()

    def test_force_orders_raises(self, spot_client: BinancePublicClient) -> None:
        with pytest.raises(KeyError):
            spot_client.force_orders("BTCUSDT")
