# panzer/log_manager.py
"""
Utilidad centralizada de logging para Panzer.

Proporciona:
- Logger con salida a pantalla (stdout).
- Logger con fichero rotativo en una carpeta configurable.
- Formato homogéneo para todos los módulos.

Uso típico:

    from panzer.log_manager import LogManager

    log = LogManager(
        name="panzer.binance_rate_limit",
        folder="logs",
        filename="binance_rate_limit.log",
        level="INFO",
    )

    log.info("Mensaje informativo")
    log.debug("Mensaje de debug")

"""

from __future__ import annotations

import logging
import os
from logging.handlers import RotatingFileHandler


class LogManager:
    """
    Wrapper ligero sobre ``logging`` con fichero rotativo y salida a stdout.

    Configura automaticamente un ``RotatingFileHandler`` y un
    ``StreamHandler`` con formato homogeneo. No importa otros modulos
    de Panzer para evitar dependencias circulares.

    Attributes
    ----------
    name : str
        Nombre interno del logger (``logging.getLogger(name)``).
    logger : logging.Logger
        Logger subyacente, accesible para uso directo.

    Examples
    --------
    >>> log = LogManager(name="panzer.mi_modulo", folder="logs", level="DEBUG")
    >>> log.info("Conexion establecida con %s", url)
    """

    def __init__(
        self,
        name: str,
        folder: str = "logs",
        filename: str | None = None,
        level: str = "INFO",
        max_log_size_mb: int = 10,
        backup_count: int = 5,
    ) -> None:
        """
        Parameters
        ----------
        name : str
            Nombre interno del logger (``logging.getLogger(name)``).
        folder : str
            Carpeta donde se guardara el fichero de log.
        filename : str | None
            Nombre del fichero de log. Si es None, se usa ``f"{name}.log"``
            (sustituyendo puntos por guiones bajos).
        level : str
            Nivel de logging inicial: ``"DEBUG"``, ``"INFO"``, etc.
        max_log_size_mb : int
            Tamano maximo del fichero de log antes de rotar.
        backup_count : int
            Numero de ficheros de backup a conservar.
        """
        self.name = name

        # Normalizar ruta de log
        if filename is None:
            safe_name = name.replace(".", "_")
            filename = f"{safe_name}.log"

        # Carpeta base
        log_dir = folder

        try:
            os.makedirs(log_dir, exist_ok=True)
        except PermissionError:
            # Fallback a ~/.panzer/logs
            home = os.path.expanduser("~")
            log_dir = os.path.join(home, ".panzer", "logs")
            os.makedirs(log_dir, exist_ok=True)

        log_path = os.path.join(log_dir, filename)

        # Crear logger
        logger = logging.getLogger(name)

        # Evitar handlers duplicados si el logger ya existe
        if logger.handlers:
            logger.handlers.clear()

        # Nivel
        logger.setLevel(getattr(logging, level.upper(), logging.INFO))

        # Formato
        line_format = "%(asctime)s %(levelname)8s [%(name)s] %(message)s"
        date_format = "%Y-%m-%d %H:%M:%S"

        formatter = logging.Formatter(line_format, datefmt=date_format)

        # Handler a pantalla
        screen_handler = logging.StreamHandler()
        screen_handler.setFormatter(formatter)

        # Handler a fichero rotativo
        file_handler = RotatingFileHandler(
            log_path,
            maxBytes=max_log_size_mb * 1024 * 1024,
            backupCount=backup_count,
            encoding="utf-8",
        )
        file_handler.setFormatter(formatter)

        logger.addHandler(screen_handler)
        logger.addHandler(file_handler)

        # No propagar a root logger para evitar duplicados en otras configs
        logger.propagate = False

        self._logger = logger

    # ============
    # API pública
    # ============
    @property
    def logger(self) -> logging.Logger:
        """Logger subyacente de ``logging``, para uso directo si se necesita."""
        return self._logger

    # ============
    # Atajos estilo logging.Logger
    # ============

    def debug(self, msg: str, *args: object, **kwargs: object) -> None:
        """Emite un mensaje de nivel ``DEBUG``. Acepta formato estilo ``%s``."""
        self._logger.debug(msg, *args, **kwargs)

    def info(self, msg: str, *args: object, **kwargs: object) -> None:
        """Emite un mensaje de nivel ``INFO``."""
        self._logger.info(msg, *args, **kwargs)

    def warning(self, msg: str, *args: object, **kwargs: object) -> None:
        """Emite un mensaje de nivel ``WARNING``."""
        self._logger.warning(msg, *args, **kwargs)

    def error(self, msg: str, *args: object, **kwargs: object) -> None:
        """Emite un mensaje de nivel ``ERROR``."""
        self._logger.error(msg, *args, **kwargs)

    def critical(self, msg: str, *args: object, **kwargs: object) -> None:
        """Emite un mensaje de nivel ``CRITICAL``."""
        self._logger.critical(msg, *args, **kwargs)
