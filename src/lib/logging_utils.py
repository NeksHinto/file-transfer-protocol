"""
Logging y manejo de errores compartido entre servidor y clientes.
"""

import logging
import os
import sys


class ValidationError(Exception):
    """Precondicion del protocolo o de los argumentos no se cumple."""


def format_addr(addr) -> str:
    """Convierte `(ip, port)` en `"ip:port"`; si es `None` retorna "-"."""
    if addr is None:
        return "-"
    try:
        ip, port = addr
        return f"{ip}:{port}"
    except (TypeError, ValueError):
        return str(addr)


class PeerLoggerAdapter(logging.LoggerAdapter):
    """Inyecta `[peer]` al frente de cada mensaje."""

    def process(self, msg, kwargs):
        peer = (self.extra or {}).get("peer", "-")
        if peer and peer != "-":
            return f"[{peer}] {msg}", kwargs
        return msg, kwargs

    def with_peer(self, peer) -> "PeerLoggerAdapter":
        """Devuelve un adapter nuevo asociado al peer indicado."""
        return PeerLoggerAdapter(self.logger, {"peer": format_addr(peer)})


def get_logger(name: str, peer=None) -> PeerLoggerAdapter:
    """devuelve un `LoggerAdapter` que prefija cada mensaje con `[ip:port]` del peer asociado"""
    return PeerLoggerAdapter(logging.getLogger(name), {"peer": format_addr(peer)})


def setup_logging(level: int = logging.INFO, log_file: str = None) -> None:
    """configura el root logger."""
    handlers = [logging.StreamHandler(sys.stdout)]
    if log_file:
        log_dir = os.path.dirname(log_file)
        if log_dir:
            os.makedirs(log_dir, exist_ok=True)
        handlers.append(logging.FileHandler(log_file, mode="a"))
    logging.basicConfig(
        level=level,
        format="[%(asctime)s] [%(levelname)s] %(name)s - %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
        handlers=handlers,
        force=True,
    )


def log_error(logger, message: str, exc: BaseException = None) -> None:
    """Loggea un error con el tipo y mensaje de la excepción (si existe)."""
    if exc is not None:
        logger.error(f"{message}: {type(exc).__name__}: {exc}")
    else:
        logger.error(message)


def validate(condition: bool, message: str, logger=None) -> None:
    """Levanta `ValidationError` si `condition` es falso, loggeando antes."""
    if not condition:
        if logger is not None:
            logger.error(f"validación fallida: {message}")
        raise ValidationError(message)
