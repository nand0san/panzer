# panzer/time_sync.py
"""
Estimador ligero de desfase de reloj entre el host local y Binance.

Idea:
- Cada vez que llamamos a /time añadimos una muestra:
    offset = server_time_ms / 1000.0 - local_now
- Mantenemos una ventana deslizante de las últimas N muestras recientes.
- El offset actual es la mediana de la ventana (robusto frente a outliers).
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field
from time import time


@dataclass
class TimeOffsetEstimator:
    """
    Estima el desfase de reloj entre el host local y el servidor.

    - max_samples: nº máximo de muestras almacenadas.
    - max_age_seconds: edad máxima de las muestras consideradas.
    """

    max_samples: int = 20
    max_age_seconds: float = 60.0

    _samples: deque[tuple[float, float]] = field(
        default_factory=deque,
        init=False,
        repr=False,
    )

    def _drop_old(self, now: float) -> None:
        """
        Elimina muestras demasiado antiguas respecto a 'now'.
        """
        while self._samples and now - self._samples[0][0] > self.max_age_seconds:
            self._samples.popleft()

    def add_sample(self, server_time_ms: int, local_now: float | None = None) -> float:
        """
        Añade una muestra nueva y devuelve el offset estimado actual.

        :param server_time_ms: Tiempo de servidor en milisegundos (Binance).
        :param local_now: Epoch local en segundos. Si es None, se usa time().
        :return: Offset estimado en segundos (mediana de las muestras).
        """
        if local_now is None:
            local_now = time()

        offset_sec = server_time_ms / 1000.0 - local_now
        self._samples.append((local_now, offset_sec))

        # Mantener tamaño máximo
        while len(self._samples) > self.max_samples:
            self._samples.popleft()

        # Limpiar muestras antiguas
        self._drop_old(local_now)

        return self.current_offset()

    def is_ready(self) -> bool:
        """
        Indica si hay suficientes muestras recientes como para fiarse del offset.
        """
        if not self._samples:
            return False
        now = time()
        self._drop_old(now)
        return len(self._samples) >= 3

    def current_offset(self) -> float:
        """
        Devuelve el offset estimado actual (segundos).

        Si no hay muestras, devuelve 0.0.
        """
        if not self._samples:
            return 0.0

        offsets: list[float] = sorted(o for _, o in self._samples)
        n = len(offsets)
        mid = n // 2

        if n % 2 == 1:
            return offsets[mid]
        return 0.5 * (offsets[mid - 1] + offsets[mid])

    def to_server_ms(self, local_now: float | None = None) -> int:
        """
        Convierte un 'ahora local' a 'ahora servidor' en milisegundos,
        usando el offset estimado.

        :param local_now: Epoch local en segundos. Si es None, se usa time().
        :return: Epoch server-side estimado en milisegundos.
        """
        if local_now is None:
            local_now = time()

        offset = self.current_offset()
        server_ts_ms = (local_now + offset) * 1000.0
        return int(server_ts_ms)
