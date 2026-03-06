# panzer/rate_limit/binance_fixed.py
"""
Rate limiter específico para Binance basado en ventanas fijas de un minuto.

Características:
- Utiliza como límite el REQUEST_WEIGHT por minuto obtenido dinámicamente
  desde /exchangeInfo (ver panzer.exchanges.binance.config).
- Trabaja con ventanas fijas de 60 segundos (bucket = floor(epoch / 60)).
- Mantiene un contador local de peso usado en la ventana actual.
- Se sincroniza opcionalmente con el contador real del servidor mediante
  la cabecera HTTP `X-MBX-USED-WEIGHT-1M`.
- Aplica un factor de seguridad (safety_ratio) para no apurar el límite
  al 100 % y evitar baneos por pequeños desfases de tiempo.

Este módulo no depende de ningún endpoint concreto; sólo de los límites
ya parseados en ExchangeRateLimits.
"""

from __future__ import annotations

import threading
import time
from collections.abc import Mapping

from panzer.exchanges.binance.config import ExchangeRateLimits
from panzer.log_manager import LogManager


class BinanceFixedWindowLimiter:
    """
    Rate limiter para Binance usando ventanas fijas de un minuto.

    Lógica:
    - Se inicializa con un límite máximo de REQUEST_WEIGHT por minuto.
    - Cada llamada a `acquire(weight)`:
        - Actualiza la ventana (bucket) si ha cambiado el minuto.
        - Si el uso local + weight supera un umbral (max_per_minute * safety_ratio),
          duerme hasta el inicio del siguiente minuto.
        - Incrementa el contador local.
    - `update_from_headers(headers)`:
        - Si encuentra `X-MBX-USED-WEIGHT-1M`, sincroniza el contador local
          con el valor del servidor (tomando el máximo).

    Este diseño permite:
    - Alinear el control local con el contador real de Binance.
    - Ajustar dinámicamente el límite global vía /exchangeInfo.
    """

    def __init__(
        self,
        max_per_minute: int,
        safety_ratio: float = 0.9,
    ) -> None:
        """
        Inicializa el limitador.

        Parameters
        ----------
        max_per_minute : int
            Limite maximo de REQUEST_WEIGHT por minuto para la IP. Debe
            venir de ``ExchangeRateLimits.request_weight.limit``.
        safety_ratio : float
            Factor de seguridad en (0, 1]. Un valor de 0.9 implica que
            Panzer intentara no sobrepasar el 90%% del limite teorico
            antes de dormir hasta la siguiente ventana.
        """
        if max_per_minute <= 0:
            raise ValueError("max_per_minute debe ser mayor que cero")

        if not (0.0 < safety_ratio <= 1.0):
            raise ValueError("safety_ratio debe estar en el rango (0, 1]")

        self._now_func = time.time

        self.max_per_minute: int = max_per_minute
        self.safety_ratio: float = safety_ratio

        # Identificador de la ventana actual (bucket = epoch // 60)
        self._bucket_id: int | None = None

        # Contador local de peso usado en la ventana actual
        self._used_local: int = 0

        # Último valor observado del contador del servidor (cabecera)
        self._last_server_used: int | None = None

        # Logger propio del rate limiter
        self._logger = LogManager(
            name="panzer.binance_rate_limit",
            folder="logs",
            filename="binance_rate_limit.log",
            level="INFO",
        )

        # Lock para uso concurrente seguro
        self._lock = threading.Lock()

    # ==========================
    # Métodos auxiliares internos
    # ==========================

    @staticmethod
    def _current_bucket(now: float | None = None) -> int:
        """
        Calcula el identificador de la ventana actual en minutos
        (floor(epoch_seconds / 60)).

        Parameters
        ----------
        now : float | None
            Epoch actual en segundos. Si es None, se usa ``time.time()``.

        Returns
        -------
        int
            Identificador de la ventana actual de un minuto.
        """
        if now is None:
            now = time.time()
        return int(now) // 60

    def _rollover_if_needed(self, now: float | None = None) -> None:
        """
        Comprueba si hemos cambiado de ventana (minuto). Si es asi, resetea
        el contador local y el valor de servidor observado.

        Parameters
        ----------
        now : float | None
            Epoch actual en segundos. Si es None, se usa ``time.time()``.
        """
        bucket = self._current_bucket(now)
        if self._bucket_id is None or bucket != self._bucket_id:
            self._logger.debug(
                "Cambio de ventana: bucket %s -> %s, reseteando contador local",
                self._bucket_id,
                bucket,
            )
            self._bucket_id = bucket
            self._used_local = 0
            self._last_server_used = None

    # ==========================
    # API pública
    # ==========================

    @property
    def used_local(self) -> int:
        """
        Devuelve el peso local acumulado en la ventana actual.
        """
        return self._used_local

    @property
    def last_server_used(self) -> int | None:
        """
        Devuelve el último valor observado de X-MBX-USED-WEIGHT-1M.
        """
        return self._last_server_used

    @property
    def effective_limit(self) -> int:
        """
        Limite efectivo tras aplicar el factor de seguridad.
        """
        return max(1, int(self.max_per_minute * self.safety_ratio))

    @property
    def remaining(self) -> int:
        """
        Peso disponible en la ventana actual antes de dormir.

        Tiene en cuenta el rollover de ventana: si ha cambiado el minuto,
        devuelve el limite efectivo completo.
        """
        with self._lock:
            self._rollover_if_needed()
            return max(0, self.effective_limit - self._used_local)

    def set_now_func(self, func):
        self._now_func = func

    def acquire(self, weight: int = 1, now: float | None = None) -> None:
        """
        Reserva capacidad de peso en la ventana actual.

        Si el consumo local + weight supera el umbral de seguridad
        (``max_per_minute * safety_ratio``), este metodo duerme hasta el
        inicio del siguiente minuto antes de continuar.

        Parameters
        ----------
        weight : int
            Peso a consumir en esta operacion (REQUEST_WEIGHT).
        now : float | None
            Epoch actual en segundos. Solo se usa en tests; en
            produccion se deja en None para usar ``time.time()``.
        """
        if weight <= 0:
            raise ValueError("weight debe ser mayor que cero")

        while True:
            if now is None:
                now = self._now_func()

            with self._lock:
                # Actualizar ventana si ha cambiado
                self._rollover_if_needed(now=now)

                # Límite efectivo con factor de seguridad, al menos 1
                effective_limit = max(1, int(self.max_per_minute * self.safety_ratio))
                projected = self._used_local + weight

                if projected <= effective_limit:
                    # Hay capacidad en esta ventana
                    self._used_local = projected
                    self._logger.debug(
                        "Acquire: weight=%s, used_local=%s, max_per_minute=%s, effective_limit=%s",
                        weight,
                        self._used_local,
                        self.max_per_minute,
                        effective_limit,
                    )
                    return

                # No hay capacidad → calcular cuánto dormir
                current_window_start = (self._bucket_id or self._current_bucket(now)) * 60
                next_window_start = current_window_start + 60
                sleep_for = max(0.0, next_window_start - now)

                self._logger.warning(
                    "Límite de seguridad alcanzado (used_local=%s, weight=%s, "
                    "effective_limit=%s). Durmiendo %.2f segundos.",
                    self._used_local,
                    weight,
                    effective_limit,
                    sleep_for,
                )

            # Fuera del lock: dormimos y volvemos a intentar
            time.sleep(sleep_for)
            now = None  # fuerza recálculo de time.time() en la siguiente iteración

    def update_from_headers(self, headers: Mapping[str, str]) -> None:
        """
        Sincroniza el contador local con X-MBX-USED-WEIGHT-1M (si está presente).
        """
        server_used: int | None = None

        for key, value in headers.items():
            if key.lower() == "x-mbx-used-weight-1m":
                try:
                    server_used = int(value)
                except (TypeError, ValueError):
                    self._logger.debug("No se ha podido parsear X-MBX-USED-WEIGHT-1M=%r", value)
                    server_used = None
                break

        if server_used is None:
            return

        with self._lock:
            # Actualizamos siempre last_server_used
            self._last_server_used = server_used

            # Sólo subimos used_local, nunca lo bajamos (comportamiento conservador)
            if server_used > self._used_local:
                self._logger.debug(
                    "Sincronizando used_local con valor de servidor: %s -> %s",
                    self._used_local,
                    server_used,
                )
                self._used_local = server_used

    # ==========================
    # Constructores de conveniencia
    # ==========================

    @classmethod
    def from_exchange_limits(
        cls,
        limits: ExchangeRateLimits,
        safety_ratio: float = 0.9,
    ) -> BinanceFixedWindowLimiter:
        if limits.request_weight is None:
            raise ValueError("ExchangeRateLimits.request_weight no está definido; no se puede construir el limitador.")
        return cls(
            max_per_minute=limits.request_weight.limit,
            safety_ratio=safety_ratio,
        )


# ==========================
# Test manual rápido
# ==========================

if __name__ == "__main__":
    import requests

    from panzer.exchanges.binance.config import get_spot_rate_limits

    spot_limits = get_spot_rate_limits()
    limiter = BinanceFixedWindowLimiter.from_exchange_limits(
        spot_limits,
        safety_ratio=0.9,
    )

    for i in range(5):
        limiter.acquire(weight=1)
        resp = requests.get("https://api.binance.com/api/v3/time", timeout=5)
        limiter.update_from_headers(resp.headers)

        print(
            f"Iter={i} status={resp.status_code} used_local={limiter.used_local} server_used={limiter.last_server_used}"
        )
