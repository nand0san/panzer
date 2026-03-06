"""
Tests empiricos de las propiedades de datos definidas en DATA_PROPERTIES.md.

Verifican invariantes de la API real de Binance sobre datos crudos:
klines, aggTrades, trades recientes y order book (depth).

Todos los datos se obtienen UNA SOLA VEZ por sesion mediante fixtures
en ``conftest.py``.  Los tests reciben datos ya cacheados.

Requieren conexion a internet.  Marcados con ``@pytest.mark.empirical``.
"""

from __future__ import annotations

import pytest

from .conftest import TICK_MS, MarketTestData

pytestmark = pytest.mark.empirical


# =====================================================================
# Helpers
# =====================================================================

def _parse_kline(raw: list[object]) -> dict:
    """Convierte una kline cruda (array de 12 elementos) a dict con tipos."""
    return {
        "open_ts": int(raw[0]),
        "open": float(raw[1]),
        "high": float(raw[2]),
        "low": float(raw[3]),
        "close": float(raw[4]),
        "volume": float(raw[5]),
        "close_ts": int(raw[6]),
        "quote_volume": float(raw[7]),
        "trades": int(raw[8]),
        "taker_buy_base": float(raw[9]),
        "taker_buy_quote": float(raw[10]),
        "ignore": float(raw[11]),
    }


def _label(md: MarketTestData) -> str:
    """Etiqueta breve para mensajes de error."""
    return f"[{md.market}/{md.primary_symbol}]"


# =====================================================================
# 1. Klines -- estructura (seccion 1.1 / 5.1)
# =====================================================================

class TestKlineStructure:
    """Estructura de cada kline, verificada en los 3 mercados."""

    def test_non_empty(self, market_data: MarketTestData) -> None:
        assert len(market_data.klines_15m) > 0, _label(market_data)

    def test_each_kline_has_12_elements(self, market_data: MarketTestData) -> None:
        for i, k in enumerate(market_data.klines_15m):
            assert len(k) == 12, f"{_label(market_data)} kline {i}: {len(k)} elementos"

    def test_open_and_close_time_are_int(self, market_data: MarketTestData) -> None:
        for k in market_data.klines_15m:
            assert isinstance(k[0], int)
            assert isinstance(k[6], int)

    def test_trades_count_is_int(self, market_data: MarketTestData) -> None:
        for k in market_data.klines_15m:
            assert isinstance(k[8], int)

    def test_price_fields_are_str(self, market_data: MarketTestData) -> None:
        """Precio/volumen llegan como strings desde la API."""
        str_indices = [1, 2, 3, 4, 5, 7, 9, 10, 11]
        for k in market_data.klines_15m:
            for idx in str_indices:
                assert isinstance(k[idx], str), f"{_label(market_data)} [{idx}]: {type(k[idx])}"

    def test_alt_symbol_also_has_12_elements(self, market_data: MarketTestData) -> None:
        """El simbolo aleatorio cumple la misma estructura."""
        for i, k in enumerate(market_data.klines_15m_alt):
            assert len(k) == 12, (
                f"{_label(market_data)} alt={market_data.alt_symbol} kline {i}"
            )


# =====================================================================
# 1. Klines -- invariantes OHLCV (seccion 1.5)
# =====================================================================

class TestKlineOHLCVInvariants:
    """Restricciones de valores OHLCV, verificadas en los 3 mercados."""

    @pytest.fixture()
    def klines(self, market_data: MarketTestData) -> list[dict]:
        return [_parse_kline(k) for k in market_data.klines_15m]

    def test_high_gte_open_and_close(self, klines: list[dict]) -> None:
        for i, k in enumerate(klines):
            assert k["high"] >= k["open"], f"Kline {i}: high < open"
            assert k["high"] >= k["close"], f"Kline {i}: high < close"

    def test_low_lte_open_and_close(self, klines: list[dict]) -> None:
        for i, k in enumerate(klines):
            assert k["low"] <= k["open"], f"Kline {i}: low > open"
            assert k["low"] <= k["close"], f"Kline {i}: low > close"

    def test_high_gte_low(self, klines: list[dict]) -> None:
        for i, k in enumerate(klines):
            assert k["high"] >= k["low"], f"Kline {i}: high < low"

    def test_prices_positive(self, klines: list[dict]) -> None:
        for i, k in enumerate(klines):
            for field in ("open", "high", "low", "close"):
                assert k[field] > 0, f"Kline {i}: {field} <= 0"

    def test_volume_non_negative(self, klines: list[dict]) -> None:
        for i, k in enumerate(klines):
            assert k["volume"] >= 0, f"Kline {i}: volume < 0"

    def test_quote_volume_non_negative(self, klines: list[dict]) -> None:
        for i, k in enumerate(klines):
            assert k["quote_volume"] >= 0, f"Kline {i}: quote_volume < 0"

    def test_trades_non_negative(self, klines: list[dict]) -> None:
        for i, k in enumerate(klines):
            assert k["trades"] >= 0, f"Kline {i}: trades < 0"

    def test_taker_buy_base_lte_volume(self, klines: list[dict]) -> None:
        for i, k in enumerate(klines):
            assert k["taker_buy_base"] <= k["volume"] + 1e-8, (
                f"Kline {i}: taker_buy_base > volume"
            )

    def test_taker_buy_quote_lte_quote_volume(self, klines: list[dict]) -> None:
        for i, k in enumerate(klines):
            assert k["taker_buy_quote"] <= k["quote_volume"] + 1e-8, (
                f"Kline {i}: taker_buy_quote > quote_volume"
            )


# =====================================================================
# 1. Klines -- timestamps (secciones 1.4, 1.5, 1.6)
# =====================================================================

class TestKlineTimestamps:
    """Continuidad temporal y relaciones entre velas, en los 3 mercados."""

    INTERVAL = "15m"

    @pytest.fixture()
    def klines(self, market_data: MarketTestData) -> list[dict]:
        return [_parse_kline(k) for k in market_data.klines_15m]

    @pytest.fixture()
    def tick_ms(self) -> int:
        return TICK_MS[self.INTERVAL]

    def test_close_ts_gt_open_ts(self, klines: list[dict]) -> None:
        for i, k in enumerate(klines):
            assert k["close_ts"] > k["open_ts"], f"Kline {i}: close_ts <= open_ts"

    def test_close_ts_equals_open_ts_plus_tick_minus_1(
        self, klines: list[dict], tick_ms: int
    ) -> None:
        for i, k in enumerate(klines):
            expected = k["open_ts"] + tick_ms - 1
            assert k["close_ts"] == expected, (
                f"Kline {i}: close_ts={k['close_ts']} != {expected}"
            )

    def test_open_timestamps_strictly_increasing(self, klines: list[dict]) -> None:
        for i in range(1, len(klines)):
            assert klines[i]["open_ts"] > klines[i - 1]["open_ts"]

    def test_open_timestamps_unique(self, klines: list[dict]) -> None:
        ts = [k["open_ts"] for k in klines]
        assert len(ts) == len(set(ts))

    def test_continuity_fixed_tick(self, klines: list[dict], tick_ms: int) -> None:
        """Intervalo entre Open timestamps consecutivos = tick_ms."""
        for i in range(1, len(klines)):
            diff = klines[i]["open_ts"] - klines[i - 1]["open_ts"]
            assert diff == tick_ms, f"Kline {i}: diff={diff} != {tick_ms}"

    def test_adjacency_no_overlap(self, klines: list[dict]) -> None:
        """Close[n] + 1 == Open[n+1]."""
        for i in range(1, len(klines)):
            assert klines[i - 1]["close_ts"] + 1 == klines[i]["open_ts"]

    def test_alt_symbol_continuity(self, market_data: MarketTestData) -> None:
        """El simbolo aleatorio tambien cumple continuidad temporal."""
        tick_ms = TICK_MS[self.INTERVAL]
        parsed = [_parse_kline(k) for k in market_data.klines_15m_alt]
        for i in range(1, len(parsed)):
            diff = parsed[i]["open_ts"] - parsed[i - 1]["open_ts"]
            assert diff == tick_ms, (
                f"{market_data.alt_symbol} kline {i}: diff={diff} != {tick_ms}"
            )


# =====================================================================
# 1. Klines -- multiples intervalos (seccion 6.3)
# =====================================================================

class TestKlineMultipleIntervals:
    """Formula close_ts y validez de intervalos, solo spot para ahorrar."""

    def test_close_ts_formula_1m(self, spot_interval_klines: dict) -> None:
        self._check_formula(spot_interval_klines["1m"], TICK_MS["1m"])

    def test_close_ts_formula_1h(self, spot_interval_klines: dict) -> None:
        self._check_formula(spot_interval_klines["1h"], TICK_MS["1h"])

    def test_close_ts_formula_1d(self, spot_interval_klines: dict) -> None:
        self._check_formula(spot_interval_klines["1d"], TICK_MS["1d"])

    def test_close_ts_formula_1w(self, spot_interval_klines: dict) -> None:
        self._check_formula(spot_interval_klines["1w"], TICK_MS["1w"])

    def test_all_intervals_return_data(
        self, spot_interval_klines: dict
    ) -> None:
        """Cada intervalo devuelve klines no vacias con 12 elementos."""
        for iv, raw in spot_interval_klines.items():
            assert len(raw) > 0, f"Intervalo {iv}: sin datos"
            assert len(raw[0]) == 12, f"Intervalo {iv}: kline no tiene 12 elementos"

    @staticmethod
    def _check_formula(raw: list, tick_ms: int) -> None:
        for k in raw:
            assert int(k[6]) == int(k[0]) + tick_ms - 1


# =====================================================================
# 2. Aggregated Trades (secciones 2.1 -- 2.7)
# =====================================================================

class TestAggTradesInvariants:
    """Invariantes de aggTrades, verificadas en los 3 mercados."""

    def test_non_empty(self, market_data: MarketTestData) -> None:
        assert len(market_data.agg_trades) > 0, _label(market_data)

    def test_ids_unique(self, market_data: MarketTestData) -> None:
        ids = [t["a"] for t in market_data.agg_trades]
        assert len(ids) == len(set(ids)), _label(market_data)

    def test_ids_monotonically_increasing(self, market_data: MarketTestData) -> None:
        trades = market_data.agg_trades
        for i in range(1, len(trades)):
            assert trades[i]["a"] > trades[i - 1]["a"]

    def test_ids_consecutive(self, market_data: MarketTestData) -> None:
        """IDs consecutivos en spot; en futuros puede haber gaps."""
        if market_data.market != "spot":
            pytest.skip("futuros puede tener gaps en aggTrade IDs")
        trades = market_data.agg_trades
        for i in range(1, len(trades)):
            assert trades[i]["a"] == trades[i - 1]["a"] + 1, (
                f"{_label(market_data)} aggTrade {i}: gap en IDs"
            )

    def test_price_positive(self, market_data: MarketTestData) -> None:
        for t in market_data.agg_trades:
            assert float(t["p"]) > 0

    def test_quantity_positive(self, market_data: MarketTestData) -> None:
        for t in market_data.agg_trades:
            assert float(t["q"]) > 0

    def test_ids_positive(self, market_data: MarketTestData) -> None:
        for t in market_data.agg_trades:
            assert t["a"] > 0

    def test_timestamp_monotonically_increasing(self, market_data: MarketTestData) -> None:
        """Timestamp creciente (no estricto: varios trades en el mismo ms)."""
        trades = market_data.agg_trades
        for i in range(1, len(trades)):
            assert trades[i]["T"] >= trades[i - 1]["T"]

    def test_first_lte_last_trade_id(self, market_data: MarketTestData) -> None:
        for i, t in enumerate(market_data.agg_trades):
            assert t["f"] <= t["l"], f"{_label(market_data)} aggTrade {i}: f > l"

    def test_trade_id_ranges_adjacent(self, market_data: MarketTestData) -> None:
        """First[n+1] == Last[n] + 1 en spot; futuros puede tener gaps."""
        if market_data.market != "spot":
            pytest.skip("futuros puede tener gaps entre rangos de trade IDs")
        trades = market_data.agg_trades
        for i in range(1, len(trades)):
            assert trades[i]["f"] == trades[i - 1]["l"] + 1, (
                f"{_label(market_data)} aggTrade {i}: rangos no adyacentes"
            )

    def test_buyer_was_maker_is_bool(self, market_data: MarketTestData) -> None:
        for t in market_data.agg_trades:
            assert isinstance(t["m"], bool)

    def test_ordering_within_same_timestamp(self, market_data: MarketTestData) -> None:
        """Si Timestamp[n] == Timestamp[n+1], ID[n] < ID[n+1]."""
        trades = market_data.agg_trades
        for i in range(1, len(trades)):
            if trades[i]["T"] == trades[i - 1]["T"]:
                assert trades[i]["a"] > trades[i - 1]["a"]


# =====================================================================
# 2. AggTrades -- diferencias entre mercados (seccion 6.2)
# =====================================================================

class TestAggTradesMarketDifferences:
    """Claves especificas por mercado, sin llamadas API extra."""

    def test_spot_has_best_price_match(self, spot_data: MarketTestData) -> None:
        """Spot incluye 'M' (Best price match)."""
        for t in spot_data.agg_trades:
            assert "M" in t, "Spot aggTrade sin clave 'M'"
            assert isinstance(t["M"], bool)

    def test_um_lacks_best_price_match(self, um_data: MarketTestData) -> None:
        """UM futures NO incluye 'M'."""
        for t in um_data.agg_trades:
            assert "M" not in t, "UM aggTrade con 'M' inesperado"

    def test_cm_lacks_best_price_match(self, cm_data: MarketTestData) -> None:
        """CM futures NO incluye 'M'."""
        for t in cm_data.agg_trades:
            assert "M" not in t, "CM aggTrade con 'M' inesperado"

    def test_spot_has_8_keys(self, spot_data: MarketTestData) -> None:
        expected = {"a", "p", "q", "f", "l", "T", "m", "M"}
        for t in spot_data.agg_trades[:5]:
            assert expected <= set(t.keys())


# =====================================================================
# 3. Trades recientes (seccion 3)
# =====================================================================

class TestRecentTradesInvariants:
    """Invariantes de trades recientes (/trades), en los 3 mercados."""

    def test_non_empty(self, market_data: MarketTestData) -> None:
        assert len(market_data.trades) > 0, _label(market_data)

    def test_has_core_keys(self, market_data: MarketTestData) -> None:
        """Todos los mercados tienen al menos id, price, qty, time."""
        core = {"id", "price", "qty", "time", "isBuyerMaker"}
        for i, t in enumerate(market_data.trades):
            assert core <= set(t.keys()), (
                f"{_label(market_data)} trade {i}: faltan claves {core - set(t.keys())}"
            )

    def test_ids_unique(self, market_data: MarketTestData) -> None:
        ids = [t["id"] for t in market_data.trades]
        assert len(ids) == len(set(ids)), _label(market_data)

    def test_ids_monotonically_increasing(self, market_data: MarketTestData) -> None:
        trades = market_data.trades
        for i in range(1, len(trades)):
            assert trades[i]["id"] > trades[i - 1]["id"]

    def test_ids_consecutive(self, market_data: MarketTestData) -> None:
        """IDs consecutivos en spot; en futuros puede haber gaps."""
        if market_data.market != "spot":
            pytest.skip("futuros puede tener gaps en trade IDs")
        trades = market_data.trades
        for i in range(1, len(trades)):
            assert trades[i]["id"] == trades[i - 1]["id"] + 1, (
                f"{_label(market_data)} trade {i}: gap en IDs"
            )

    def test_price_positive(self, market_data: MarketTestData) -> None:
        for t in market_data.trades:
            assert float(t["price"]) > 0

    def test_quantity_positive(self, market_data: MarketTestData) -> None:
        for t in market_data.trades:
            assert float(t["qty"]) > 0

    def test_timestamp_monotonically_increasing(self, market_data: MarketTestData) -> None:
        trades = market_data.trades
        for i in range(1, len(trades)):
            assert trades[i]["time"] >= trades[i - 1]["time"]

    def test_ids_positive(self, market_data: MarketTestData) -> None:
        for t in market_data.trades:
            assert t["id"] > 0

    def test_buyer_was_maker_is_bool(self, market_data: MarketTestData) -> None:
        for t in market_data.trades:
            assert isinstance(t["isBuyerMaker"], bool)


class TestRecentTradesSpotSpecific:
    """Propiedades del endpoint /trades exclusivas de spot."""

    def test_expected_keys(self, spot_data: MarketTestData) -> None:
        expected = {"id", "price", "qty", "quoteQty", "time", "isBuyerMaker", "isBestMatch"}
        for i, t in enumerate(spot_data.trades):
            assert expected <= set(t.keys()), f"Trade {i}: claves incompletas"

    def test_quote_quantity_positive(self, spot_data: MarketTestData) -> None:
        for t in spot_data.trades:
            assert float(t["quoteQty"]) > 0

    def test_quote_equals_price_times_qty(self, spot_data: MarketTestData) -> None:
        """Quote quantity ~= Price * Quantity (tolerancia por redondeo)."""
        for i, t in enumerate(spot_data.trades):
            price = float(t["price"])
            qty = float(t["qty"])
            quote = float(t["quoteQty"])
            expected = price * qty
            assert abs(quote - expected) / max(expected, 1e-12) < 1e-4, (
                f"Trade {i}: quoteQty={quote} != price*qty={expected}"
            )


# =====================================================================
# 4. Order Book / depth (seccion 4)
# =====================================================================

class TestDepthStructure:
    """Estructura del order book, verificada en los 3 mercados."""

    def test_has_required_keys(self, market_data: MarketTestData) -> None:
        depth = market_data.depth
        assert "lastUpdateId" in depth, _label(market_data)
        assert "bids" in depth
        assert "asks" in depth

    def test_last_update_id_is_int(self, market_data: MarketTestData) -> None:
        assert isinstance(market_data.depth["lastUpdateId"], int)

    def test_non_empty(self, market_data: MarketTestData) -> None:
        assert len(market_data.depth["bids"]) > 0, _label(market_data)
        assert len(market_data.depth["asks"]) > 0, _label(market_data)

    def test_each_level_has_two_str_elements(self, market_data: MarketTestData) -> None:
        for side in ("bids", "asks"):
            for i, level in enumerate(market_data.depth[side]):
                assert len(level) == 2, (
                    f"{_label(market_data)} {side}[{i}]: {len(level)} elementos"
                )
                assert isinstance(level[0], str)
                assert isinstance(level[1], str)


class TestDepthInvariants:
    """Invariantes de valores del order book, en los 3 mercados."""

    @pytest.fixture()
    def bids(self, market_data: MarketTestData) -> list[tuple[float, float]]:
        return [(float(b[0]), float(b[1])) for b in market_data.depth["bids"]]

    @pytest.fixture()
    def asks(self, market_data: MarketTestData) -> list[tuple[float, float]]:
        return [(float(a[0]), float(a[1])) for a in market_data.depth["asks"]]

    def test_prices_positive(self, bids: list, asks: list) -> None:
        for p, _ in bids:
            assert p > 0
        for p, _ in asks:
            assert p > 0

    def test_quantities_positive(self, bids: list, asks: list) -> None:
        for _, q in bids:
            assert q > 0
        for _, q in asks:
            assert q > 0

    def test_bids_descending(self, bids: list) -> None:
        prices = [p for p, _ in bids]
        for i in range(1, len(prices)):
            assert prices[i] <= prices[i - 1], (
                f"Bid {i}: {prices[i]} > {prices[i-1]}"
            )

    def test_asks_ascending(self, asks: list) -> None:
        prices = [p for p, _ in asks]
        for i in range(1, len(prices)):
            assert prices[i] >= prices[i - 1], (
                f"Ask {i}: {prices[i]} < {prices[i-1]}"
            )

    def test_no_duplicate_bid_prices(self, bids: list) -> None:
        prices = [p for p, _ in bids]
        assert len(prices) == len(set(prices))

    def test_no_duplicate_ask_prices(self, asks: list) -> None:
        prices = [p for p, _ in asks]
        assert len(prices) == len(set(prices))

    def test_spread_non_negative(self, bids: list, asks: list) -> None:
        best_bid = bids[0][0]
        best_ask = asks[0][0]
        assert best_ask >= best_bid, f"Spread negativo: ask={best_ask} < bid={best_bid}"

    def test_best_bid_lt_best_ask(self, bids: list, asks: list) -> None:
        assert bids[0][0] < asks[0][0], (
            f"Crossed book: bid={bids[0][0]} >= ask={asks[0][0]}"
        )


# =====================================================================
# 6. Propiedades transversales -- timestamps (seccion 6.4)
# =====================================================================

class TestTimestampsGeneral:
    """Propiedades generales de timestamps, en los 3 mercados."""

    # Rango razonable en ms: 2017-01-01 a 2030-01-01
    TS_MIN = 1_483_228_800_000
    TS_MAX = 1_893_456_000_000

    def test_kline_timestamps_positive_and_ms(self, market_data: MarketTestData) -> None:
        for k in market_data.klines_15m[:10]:
            open_ts = int(k[0])
            close_ts = int(k[6])
            assert self.TS_MIN <= open_ts <= self.TS_MAX, (
                f"{_label(market_data)} open_ts={open_ts} fuera de rango"
            )
            assert self.TS_MIN <= close_ts <= self.TS_MAX

    def test_agg_trade_timestamps_are_milliseconds(
        self, market_data: MarketTestData
    ) -> None:
        for t in market_data.agg_trades[:10]:
            assert self.TS_MIN <= t["T"] <= self.TS_MAX

    def test_trade_timestamps_are_milliseconds(
        self, market_data: MarketTestData
    ) -> None:
        for t in market_data.trades[:10]:
            assert self.TS_MIN <= t["time"] <= self.TS_MAX
