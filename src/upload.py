"""
upload: Envía un archivo al servidor usando Stop & Wait.

Uso:
    python upload.py [-v | -q] [-H ADDR] [-p PORT] [-s FILEPATH] [-n FILENAME]
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
    read_file_chunks,
    MAX_PACKET_SIZE,
)
from lib.protocol import get_protocol  # noqa: E402

logger = logging.getLogger("UPLOAD")

HANDSHAKE_RETRIES = 5
HANDSHAKE_TIMEOUT = 2.0


def main():
    parser = argparse.ArgumentParser(
        description="Cliente upload Stop & Wait UDP - TP1 Redes 2026"
    )
    verb = parser.add_mutually_exclusive_group()
    verb.add_argument("-v", "--verbose", action="store_true")
    verb.add_argument("-q", "--quiet", action="store_true")
    parser.add_argument(
        "-r",
        "--protocol",
        default="stop_and_wait",
        help="Protocolo de recuperación: stop_and_wait | selective_repeat (default: stop_and_wait)",
    )
    parser.add_argument(
        "-H", "--host", default="127.0.0.1", help="IP del servidor (default: 127.0.0.1)"
    )
    parser.add_argument(
        "-p", "--port", type=int, default=9000, help="Puerto (default: 9000)"
    )
    parser.add_argument(
        "-s", "--src", required=True, help="Ruta local del archivo a subir"
    )
    parser.add_argument(
        "-n", "--name", required=True, help="Nombre con el que se guarda en el servidor"
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

    if not os.path.isfile(args.src):
        logger.error(f"Archivo no encontrado: {args.src}")
        sys.exit(1)

    server = (args.host, args.port)
    size_mb = os.path.getsize(args.src) / (1024 * 1024)
    logger.info(f"Iniciando upload '{args.name}' -> {args.host}:{args.port}")
    logger.info(f"Archivo: {args.src} ({size_mb:.2f} MB)")

    # Cargamos el archivo antes del handshake para evitar que el servidor
    # trunque la misma ruta cuando cliente y servidor comparten storage.
    source_chunks = list(read_file_chunks(args.src))

    # Obtener instancia del protocolo
    protocol = get_protocol(args.protocol, verbose=args.verbose)

    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        # Handshake (incluye el protocolo)
        handshake = create_handshake_packet("UPLOAD", args.name, args.protocol)
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

        # Transferencia usando el protocolo elegido
        start = time.time()
        protocol.send_file(args.src, args.name, server, sock, chunks=source_chunks)
        elapsed = time.time() - start
        logger.info(f"Transferencia completada: {args.name}")
        logger.info(f"Tiempo: {elapsed:.2f} segundos")

    except KeyboardInterrupt:
        logger.info("Upload interrumpido")
    except Exception as e:
        logger.error(f"Error: {e}")
        sys.exit(1)
    finally:
        sock.close()


if __name__ == "__main__":
    main()
