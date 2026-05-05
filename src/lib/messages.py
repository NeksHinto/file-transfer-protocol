"""
Constructores de paquetes.
"""

from lib.flags import (
    FLAG_ACK,
    FLAG_DATA,
    FLAG_ERROR,
    FLAG_FIN,
    FLAG_HANDSHAKE,
)
from lib.wire import build_packet


def create_handshake_packet(
    operation: str,
    filename: str,
    protocol: str = None,
    file_size: int = 0,
) -> bytes:
    """HANDSHAKE: payload = OPERATION|filename|protocol|file_size"""
    parts = [operation, filename, protocol or "", str(int(file_size))]
    payload = "|".join(parts).encode()
    return build_packet(0, 0, FLAG_HANDSHAKE, payload)


def create_data_packet(seq: int, payload: bytes) -> bytes:
    return build_packet(seq, 0, FLAG_DATA, payload)


def create_ack_packet(seq: int) -> bytes:
    return build_packet(0, seq, FLAG_ACK)


def create_fin_packet(next_seq: int = 0) -> bytes:
    return build_packet(next_seq, 0, FLAG_FIN)


def create_error_packet(message: str) -> bytes:
    return build_packet(0, 0, FLAG_ERROR, message.encode())
