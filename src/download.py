"""
download: Descarga un archivo del servidor usando Stop & Wait.

Uso:
    python download.py [-v | -q] [-H ADDR] [-p PORT] [-d FILEPATH] [-n FILENAME]
"""

import argparse
import logging
import os
import socket
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from lib.packet import (  # noqa: E402
    parse_packet,
    create_handshake_packet,
    is_ack,
    is_error,
    MAX_PACKET_SIZE,
)
from lib.stop_and_wait import StopAndWait  # noqa: E402

logger = logging.getLogger("DOWNLOAD")

HANDSHAKE_RETRIES = 5
HANDSHAKE_TIMEOUT = 2.0


def main():
    parser = argparse.ArgumentParser(
        description="Cliente download Stop & Wait UDP - TP1 Redes 2026"
    )
    verb = parser.add_mutually_exclusive_group()
    verb.add_argument("-v", "--verbose", action="store_true")
    verb.add_argument("-q", "--quiet", action="store_true")
    parser.add_argument(
        "-H", "--host", default="127.0.0.1", help="IP del servidor (default: 127.0.0.1)"
    )
    parser.add_argument(
        "-p", "--port", type=int, default=9000, help="Puerto (default: 9000)"
    )
    parser.add_argument(
        "-d", "--dst", required=True, help="Directorio destino donde guardar el archivo"
    )
    parser.add_argument(
        "-n", "--name", required=True, help="Nombre del archivo a descargar"
    )
    args = parser.parse_args()

    level = (
        logging.DEBUG
        if args.verbose
        else (logging.WARNING if args.quiet else logging.INFO)
    )
    logging.basicConfig(
        level=level,
        format="[%(levelname)s] %(name)s - %(message)s",
        handlers=[logging.StreamHandler(sys.stdout)],
    )

    server = (args.host, args.port)
    os.makedirs(args.dst, exist_ok=True)
    filepath = os.path.join(args.dst, args.name)

    logger.info(f"Iniciando download '{args.name}' <- {args.host}:{args.port}")
    logger.info(f"Destino: {filepath}")

    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        # Handshake
        handshake = create_handshake_packet("DOWNLOAD", args.name)
        ack_received = False
        for attempt in range(1, HANDSHAKE_RETRIES + 1):
            logger.debug(f"HANDSHAKE intento {attempt}/{HANDSHAKE_RETRIES}")
            sock.sendto(handshake, server)
            sock.settimeout(HANDSHAKE_TIMEOUT)
            try:
                data, _ = sock.recvfrom(MAX_PACKET_SIZE)
                pkt = parse_packet(data)
                if pkt and is_error(pkt):
                    logger.error(f"Error del servidor: {pkt['payload'].decode()}")
                    sys.exit(1)
                if pkt and is_ack(pkt):
                    logger.debug("HANDSHAKE exitoso")
                    ack_received = True
                    break
            except OSError:
                logger.debug("HANDSHAKE timeout, reintentando...")

        if not ack_received:
            logger.error("No se pudo conectar al servidor")
            sys.exit(1)

        # Recepción
        start = time.time()
        StopAndWait(verbose=args.verbose).receive_file(filepath, sock, server)
        elapsed = time.time() - start

        size = os.path.getsize(filepath) if os.path.isfile(filepath) else 0
        logger.info(f"Archivo recibido: {filepath} ({size} bytes)")
        logger.info(f"Tiempo: {elapsed:.2f} segundos")

    except KeyboardInterrupt:
        logger.info("Download interrumpido")
    except Exception as e:
        logger.error(f"Error: {e}")
        sys.exit(1)
    finally:
        sock.close()


if __name__ == "__main__":
    main()
