"""
Tests empiricos de endpoints de opciones europeas (EAPI).

Verifican estructura e invariantes de: exchangeInfo de opciones, mark
(precio marcado + volatilidad implicita + griegas) e index (precio indice
del subyacente).

Datos obtenidos UNA SOLA VEZ por sesion via la fixture ``options_data`` en
``conftest.py``. Los simbolos se descubren en runtime (status TRADING) porque
los contratos de opciones caducan.

Requieren conexion a internet.  Marcados con ``@pytest.mark.empirical``.

Invariantes relevantes para analisis documentados aqui:
- ``markIV`` >= 0, pero ``bidIV``/``askIV`` pueden valer ``-1`` (centinela "sin cotizacion").
- delta de un CALL en ``[0, 1]``; delta de un PUT en ``[-1, 0]``.
- ``gamma`` >= 0 y ``vega`` >= 0 para CALL y PUT.
"""

from __future__ import annotations

import pytest

from panzer import BinanceOptionsClient

from .conftest import OptionsTestData

pytestmark = pytest.mark.empirical


# Rango razonable en ms: 2017-01-01 a 2035-01-01 (las opciones expiran lejos)
TS_MIN = 1_483_228_800_000
TS_MAX = 2_051_222_400_000

# Tolerancia para comparaciones de griegas (rounding de Binance)
EPS = 1e-6

MARK_KEYS = (
    "symbol",
    "markPrice",
    "bidIV",
    "askIV",
    "markIV",
    "delta",
    "gamma",
    "theta",
    "vega",
    "highPriceLimit",
    "lowPriceLimit",
    "riskFreeInterest",
)


# =====================================================================
# 0. Configuracion del cliente
# =====================================================================

class TestOptionsClientConfig:

    def test_market_is_eapi(self, options_data: OptionsTestData) -> None:
        assert options_data.client.market == "eapi"

    def test_base_url(self, options_data: OptionsTestData) -> None:
        assert options_data.client.base_url == "https://eapi.binance.com"

    def test_rejects_non_eapi_market(self) -> None:
        with pytest.raises(ValueError, match="eapi"):
            BinanceOptionsClient(market="spot", auto_sync=False)  # type: ignore[arg-type]

    def test_request_weight_limit_is_400(self, options_data: OptionsTestData) -> None:
        limits = options_data.client._limits  # type: ignore[attr-defined]
        assert limits is not None
        assert limits.request_weight is not None
        assert limits.request_weight.limit == 400


# =====================================================================
# 1. exchangeInfo de opciones
# =====================================================================

class TestOptionsExchangeInfo:

    def test_is_dict(self, options_data: OptionsTestData) -> None:
        assert isinstance(options_data.info, dict)

    def test_has_required_keys(self, options_data: OptionsTestData) -> None:
        for key in ("timezone", "serverTime", "optionSymbols", "rateLimits"):
            assert key in options_data.info, f"missing key {key!r}"

    def test_server_time_is_valid_ms(self, options_data: OptionsTestData) -> None:
        ts = options_data.info["serverTime"]
        assert TS_MIN <= ts <= TS_MAX, f"serverTime={ts}"

    def test_option_symbols_non_empty(self, options_data: OptionsTestData) -> None:
        assert len(options_data.info["optionSymbols"]) > 0

    def test_each_symbol_has_required_keys(self, options_data: OptionsTestData) -> None:
        for s in options_data.info["optionSymbols"]:
            for key in ("symbol", "side", "strikePrice", "underlying", "expiryDate", "status"):
                assert key in s, f"{s.get('symbol')!r} missing {key!r}"

    def test_side_is_call_or_put(self, options_data: OptionsTestData) -> None:
        for s in options_data.info["optionSymbols"]:
            assert s["side"] in ("CALL", "PUT"), f"{s['symbol']} side={s['side']!r}"

    def test_strike_price_positive(self, options_data: OptionsTestData) -> None:
        for s in options_data.info["optionSymbols"]:
            assert float(s["strikePrice"]) > 0, s["symbol"]

    def test_expiry_dates_valid_ms(self, options_data: OptionsTestData) -> None:
        for s in options_data.info["optionSymbols"]:
            exp = s["expiryDate"]
            assert TS_MIN <= exp <= TS_MAX, f"{s['symbol']} expiryDate={exp}"

    def test_symbol_suffix_matches_side(self, options_data: OptionsTestData) -> None:
        """El sufijo del simbolo (-C/-P) es coherente con el campo ``side``."""
        for s in options_data.info["optionSymbols"]:
            suffix = s["symbol"].rsplit("-", 1)[-1]
            expected = "C" if s["side"] == "CALL" else "P"
            assert suffix == expected, f"{s['symbol']} side={s['side']}"


# =====================================================================
# 2. mark: precio marcado + IV + griegas
# =====================================================================

class TestOptionsMark:

    def test_mark_call_is_list(self, options_data: OptionsTestData) -> None:
        assert isinstance(options_data.mark_call, list)

    def test_mark_call_single_entry(self, options_data: OptionsTestData) -> None:
        assert len(options_data.mark_call) == 1

    def test_mark_call_symbol_matches(self, options_data: OptionsTestData) -> None:
        assert options_data.mark_call[0]["symbol"] == options_data.call_symbol

    def test_mark_entry_has_required_keys(self, options_data: OptionsTestData) -> None:
        entry = options_data.mark_call[0]
        for key in MARK_KEYS:
            assert key in entry, f"missing {key!r}"

    def test_mark_all_non_empty(self, options_data: OptionsTestData) -> None:
        assert len(options_data.mark_all) > 0

    def test_mark_price_non_negative(self, options_data: OptionsTestData) -> None:
        for e in options_data.mark_all:
            assert float(e["markPrice"]) >= 0, e["symbol"]

    def test_mark_iv_non_negative(self, options_data: OptionsTestData) -> None:
        """markIV nunca es negativo (a diferencia de bidIV/askIV centinela)."""
        for e in options_data.mark_all:
            assert float(e["markIV"]) >= 0, f"{e['symbol']} markIV={e['markIV']}"

    def test_bid_ask_iv_sentinel_is_minus_one(self, options_data: OptionsTestData) -> None:
        """
        Caveat de analisis: bidIV/askIV usan ``-1`` como centinela de "sin
        cotizacion". Cualquier otro valor debe ser >= 0.
        """
        for e in options_data.mark_all:
            for key in ("bidIV", "askIV"):
                val = float(e[key])
                assert val >= 0 or val == -1.0, f"{e['symbol']} {key}={val}"

    def test_gamma_non_negative(self, options_data: OptionsTestData) -> None:
        for e in options_data.mark_all:
            assert float(e["gamma"]) >= -EPS, f"{e['symbol']} gamma={e['gamma']}"

    def test_vega_non_negative(self, options_data: OptionsTestData) -> None:
        for e in options_data.mark_all:
            assert float(e["vega"]) >= -EPS, f"{e['symbol']} vega={e['vega']}"

    def test_call_delta_in_unit_interval(self, options_data: OptionsTestData) -> None:
        """delta de un CALL en [0, 1]."""
        for e in options_data.mark_all:
            if e["symbol"].endswith("-C"):
                delta = float(e["delta"])
                assert -EPS <= delta <= 1 + EPS, f"{e['symbol']} delta={delta}"

    def test_put_delta_in_negative_unit_interval(self, options_data: OptionsTestData) -> None:
        """delta de un PUT en [-1, 0]."""
        for e in options_data.mark_all:
            if e["symbol"].endswith("-P"):
                delta = float(e["delta"])
                assert -1 - EPS <= delta <= EPS, f"{e['symbol']} delta={delta}"


# =====================================================================
# 3. index: precio indice del subyacente
# =====================================================================

class TestOptionsIndex:

    def test_is_dict(self, options_data: OptionsTestData) -> None:
        assert isinstance(options_data.index, dict)

    def test_has_required_keys(self, options_data: OptionsTestData) -> None:
        for key in ("indexPrice", "time"):
            assert key in options_data.index, f"missing {key!r}"

    def test_index_price_positive(self, options_data: OptionsTestData) -> None:
        assert float(options_data.index["indexPrice"]) > 0

    def test_time_is_valid_ms(self, options_data: OptionsTestData) -> None:
        ts = options_data.index["time"]
        assert TS_MIN <= ts <= TS_MAX, f"time={ts}"


# =====================================================================
# 4. ticker: estadisticas 24 h
# =====================================================================

class TestOptionsTicker:

    def test_is_list(self, options_data: OptionsTestData) -> None:
        assert isinstance(options_data.ticker_call, list)

    def test_symbol_matches(self, options_data: OptionsTestData) -> None:
        assert options_data.ticker_call[0]["symbol"] == options_data.call_symbol

    def test_has_required_keys(self, options_data: OptionsTestData) -> None:
        entry = options_data.ticker_call[0]
        for key in (
            "symbol", "lastPrice", "open", "high", "low", "volume",
            "bidPrice", "askPrice", "openTime", "closeTime", "strikePrice",
        ):
            assert key in entry, f"missing {key!r}"

    def test_high_ge_low(self, options_data: OptionsTestData) -> None:
        e = options_data.ticker_call[0]
        assert float(e["high"]) >= float(e["low"]), e["symbol"]

    def test_volume_non_negative(self, options_data: OptionsTestData) -> None:
        e = options_data.ticker_call[0]
        assert float(e["volume"]) >= 0, e["symbol"]


# =====================================================================
# 5. depth: order book (heredado)
# =====================================================================

class TestOptionsDepth:

    def test_is_dict(self, options_data: OptionsTestData) -> None:
        assert isinstance(options_data.depth, dict)

    def test_has_bids_and_asks(self, options_data: OptionsTestData) -> None:
        for key in ("bids", "asks"):
            assert key in options_data.depth, f"missing {key!r}"
            assert isinstance(options_data.depth[key], list)

    def test_levels_are_price_qty_pairs(self, options_data: OptionsTestData) -> None:
        for side in ("bids", "asks"):
            for level in options_data.depth[side]:
                assert len(level) == 2, level
                assert float(level[0]) >= 0 and float(level[1]) >= 0

    def test_asks_ascending(self, options_data: OptionsTestData) -> None:
        prices = [float(a[0]) for a in options_data.depth["asks"]]
        assert prices == sorted(prices), prices


# =====================================================================
# 6. klines: velas (heredado)
# =====================================================================

class TestOptionsKlines:

    def test_is_list(self, options_data: OptionsTestData) -> None:
        assert isinstance(options_data.klines_1h, list)

    def test_non_empty(self, options_data: OptionsTestData) -> None:
        assert len(options_data.klines_1h) > 0

    def test_open_time_ascending(self, options_data: OptionsTestData) -> None:
        open_times = [k[0] for k in options_data.klines_1h]
        assert open_times == sorted(open_times)

    def test_ohlc_consistency(self, options_data: OptionsTestData) -> None:
        """high >= max(open, close) y low <= min(open, close) por vela."""
        for k in options_data.klines_1h:
            o, h, low, c = float(k[1]), float(k[2]), float(k[3]), float(k[4])
            assert h >= max(o, c) - EPS, k
            assert low <= min(o, c) + EPS, k


# =====================================================================
# 7. open_interest: OI por subyacente y expiracion
# =====================================================================

class TestOptionsOpenInterest:

    def test_is_list(self, options_data: OptionsTestData) -> None:
        assert isinstance(options_data.open_interest, list)

    def test_non_empty(self, options_data: OptionsTestData) -> None:
        assert len(options_data.open_interest) > 0

    def test_each_entry_has_required_keys(self, options_data: OptionsTestData) -> None:
        for e in options_data.open_interest:
            for key in ("symbol", "sumOpenInterest", "sumOpenInterestUsd", "timestamp"):
                assert key in e, f"missing {key!r}"

    def test_values_non_negative(self, options_data: OptionsTestData) -> None:
        for e in options_data.open_interest:
            assert float(e["sumOpenInterest"]) >= 0, e["symbol"]
            assert float(e["sumOpenInterestUsd"]) >= 0, e["symbol"]

    def test_symbols_match_underlying_and_expiration(self, options_data: OptionsTestData) -> None:
        for e in options_data.open_interest:
            parts = e["symbol"].split("-")
            assert parts[0] == options_data.underlying_asset, e["symbol"]
            assert parts[1] == options_data.expiration, e["symbol"]

    def test_timestamp_is_valid_ms(self, options_data: OptionsTestData) -> None:
        for e in options_data.open_interest:
            ts = int(e["timestamp"])
            assert TS_MIN <= ts <= TS_MAX, f"{e['symbol']} ts={ts}"


# =====================================================================
# 8. exercise_history: ejercicios pasados
# =====================================================================

class TestOptionsExerciseHistory:

    def test_is_list(self, options_data: OptionsTestData) -> None:
        assert isinstance(options_data.exercise_history, list)

    def test_each_entry_has_required_keys(self, options_data: OptionsTestData) -> None:
        for e in options_data.exercise_history:
            for key in ("symbol", "strikePrice", "realStrikePrice", "expiryDate", "strikeResult"):
                assert key in e, f"missing {key!r}"

    def test_strike_prices_positive(self, options_data: OptionsTestData) -> None:
        for e in options_data.exercise_history:
            assert float(e["strikePrice"]) > 0, e["symbol"]
            assert float(e["realStrikePrice"]) > 0, e["symbol"]

    def test_expiry_dates_valid_ms(self, options_data: OptionsTestData) -> None:
        for e in options_data.exercise_history:
            assert TS_MIN <= e["expiryDate"] <= TS_MAX, f"{e['symbol']} exp={e['expiryDate']}"
