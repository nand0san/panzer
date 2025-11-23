# panzer/http/__init__.py
"""
Cliente HTTP de bajo nivel para APIs públicas (Binance, etc.).

Por ahora expone un helper específico para peticiones públicas a Binance.
"""

from .client import binance_public_get

__all__ = ["binance_public_get"]
