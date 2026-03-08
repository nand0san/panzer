# panzer/rate_limit/__init__.py
"""
Control de rate limiting para exchanges.

Proporciona ``BinanceFixedWindowLimiter``, un limitador basado en ventanas
fijas de un minuto sincronizado con los limites dinamicos de ``/exchangeInfo``.
"""

from .binance_fixed import BinanceFixedWindowLimiter

__all__ = ["BinanceFixedWindowLimiter"]
