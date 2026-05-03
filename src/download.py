"""
download: Descarga un archivo del servidor (usando Stop & Wait o Selective Repeat).

Uso:
    python download.py [-v|-q] [-r PROTOCOL] [-H ADDR] [-p PORT] -d DIRPATH -n FILENAME
"""

import argparse
import logging
import os
import socket
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from lib.logging_utils import (  # noqa: E402
    ValidationError,
    get_logger,
    log_error,
    setup_logging,
    validate,
)
from lib.packet import (  # noqa: E402
    parse_packet,
    create_handshake_packet,
    is_ack,
    is_error,
    MAX_PACKET_SIZE,
)
from lib.protocol import get_protocol  # noqa: E402

HANDSHAKE_RETRIES = 5
HANDSHAKE_TIMEOUT = 2.0
VALID_PROTOCOLS = {"stop_and_wait", "snw", "s&w", "sw", "selective_repeat", "sr"}


def main():
    parser = argparse.ArgumentParser(
        description="Cliente download UDP RDT - TP1 Redes 2026"
    )
    verb = parser.add_mutually_exclusive_group()
    verb.add_argument("-v", "--verbose", action="store_true")
    verb.add_argument("-q", "--quiet", action="store_true")
    parser.add_argument(
        "-r",
        "--protocol",
        default="stop_and_wait",
        help="stop_and_wait | selective_repeat (default: stop_and_wait)",
    )
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
    setup_logging(level=level)
    server = (args.host, args.port)
    logger = get_logger("DOWNLOAD", peer=server)

    try:
        validate(
            args.protocol.lower() in VALID_PROTOCOLS,
            f"protocolo inválido: {args.protocol}",
            logger,
        )
        validate(1 <= args.port <= 65535, f"puerto inválido: {args.port}", logger)
        validate(args.name, "nombre origen vacío", logger)
        validate(
            "\x00" not in args.name and len(args.name) <= 255,
            f"nombre origen inválido: {args.name!r}",
            logger,
        )
        os.makedirs(args.dst, exist_ok=True)
        validate(
            os.access(args.dst, os.W_OK),
            f"sin permiso de escritura en {args.dst}",
            logger,
        )
    except ValidationError:
        sys.exit(2)
    except OSError as e:
        log_error(logger, f"no se pudo preparar destino {args.dst}", e)
        sys.exit(1)

    filepath = os.path.join(args.dst, os.path.basename(args.name))
    logger.info(f"download '{args.name}' > '{filepath}'")

    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        protocol = get_protocol(args.protocol, verbose=args.verbose, logger=logger)

        handshake = create_handshake_packet("DOWNLOAD", args.name, args.protocol)
        ack_received = False
        for attempt in range(1, HANDSHAKE_RETRIES + 1):
            logger.debug(f"HANDSHAKE intento {attempt}/{HANDSHAKE_RETRIES}")
            sock.sendto(handshake, server)
            sock.settimeout(HANDSHAKE_TIMEOUT)
            try:
                data, _ = sock.recvfrom(MAX_PACKET_SIZE)
                pkt = parse_packet(data)
                if pkt and is_error(pkt):
                    log_error(
                        logger,
                        f"server rechazo: {pkt['payload'].decode(errors='replace')}",
                    )
                    sys.exit(1)
                if pkt and is_ack(pkt):
                    logger.debug("HANDSHAKE ok")
                    ack_received = True
                    break
            except (socket.timeout, OSError):
                logger.warning(
                    f"HANDSHAKE timeout (intento {attempt}/{HANDSHAKE_RETRIES})"
                )

        if not ack_received:
            log_error(logger, "no se pudo conectar al servidor")
            sys.exit(1)

        start = time.time()
        protocol.receive_file(filepath, sock, server)
        elapsed = time.time() - start

        size = os.path.getsize(filepath) if os.path.isfile(filepath) else 0
        logger.info(f"archivo recibido: {filepath} ({size} bytes) en {elapsed:.2f}s")
    except KeyboardInterrupt:
        logger.info("download interrumpido")
    except Exception as e:
        log_error(logger, "fallo el download", e)
        sys.exit(1)
    finally:
        sock.close()


if __name__ == "__main__":
    main()
