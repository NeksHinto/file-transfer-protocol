"""
Flags del campo FLAGS (1 byte) y predicados de tipo de paquete.
"""

FLAG_DATA = 0x01
FLAG_ACK = 0x02
FLAG_FIN = 0x04
FLAG_HANDSHAKE = 0x08
FLAG_ERROR = 0x10


def is_data(p) -> bool:
    return bool(p["flags"] & FLAG_DATA)


def is_ack(p) -> bool:
    return bool(p["flags"] & FLAG_ACK)


def is_fin(p) -> bool:
    return bool(p["flags"] & FLAG_FIN)


def is_handshake(p) -> bool:
    return bool(p["flags"] & FLAG_HANDSHAKE)


def is_error(p) -> bool:
    return bool(p["flags"] & FLAG_ERROR)
