"""
start-server: Servidor UDP concurrente de transferencia de archivos.
Soporta Stop & Wait y Selective Repeat (elegido por el cliente en el handshake).

Uso:
    python start-server.py [-v | -q] [-H ADDR] [-p PORT] [-s DIRPATH]
"""

import argparse
import logging
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from lib.logging_utils import get_logger, log_error, setup_logging  # noqa: E402
from server import Server  # noqa: E402


def main():
    parser = argparse.ArgumentParser(
        description="Servidor UDP RDT (Stop & Wait / Selective Repeat) - TP1 Redes 2026"
    )
    verb = parser.add_mutually_exclusive_group()
    verb.add_argument(
        "-v", "--verbose", action="store_true", help="Aumentar verbosidad"
    )
    verb.add_argument("-q", "--quiet", action="store_true", help="Reducir verbosidad")
    parser.add_argument(
        "-H", "--host", default="0.0.0.0", help="IP del servidor (default: 0.0.0.0)"
    )
    parser.add_argument(
        "-p", "--port", type=int, default=9000, help="Puerto (default: 9000)"
    )
    parser.add_argument(
        "-s",
        "--storage",
        default="./storage",
        help="Directorio de almacenamiento (default: ./storage)",
    )
    args = parser.parse_args()

    level = (
        logging.DEBUG
        if args.verbose
        else (logging.WARNING if args.quiet else logging.INFO)
    )
    setup_logging(level=level, log_file="logs/server.log")
    logger = get_logger("SERVER")

    if not (1 <= args.port <= 65535):
        log_error(logger, f"puerto fuera de rango: {args.port}")
        sys.exit(2)

    server = Server(args.host, args.port, args.storage, args.verbose)
    try:
        server.start()
    except KeyboardInterrupt:
        logger.info("servidor detenido")
    except Exception as e:
        log_error(logger, "fallo del servidor", e)
        sys.exit(1)


if __name__ == "__main__":
    main()
