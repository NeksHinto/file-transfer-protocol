"""
Representacion binaria de paquetes sobre la red (capa de wire).
Header (9 bytes):
    +--------+--------+--------+-------+--------+
    |  SEQ   |  ACK   | LENGTH | FLAGS | CKSUM  |
    | 2 B    | 2 B    | 2 B    | 1 B   | 2 B    |
    +--------+--------+--------+-------+--------+
    | PAYLOAD (hasta MAX_PAYLOAD bytes)         |
    +-------------------------------------------+
"""

import struct

# ----------------------------------------------------------------- formato --
# "!" -> network byte order (big-endian, sin padding por alineacion)
# "H" -> uint16 (SEQ, ACK, LENGTH, CKSUM)
# "B" -> uint8 (FLAGS)
HEADER_FORMAT = "!HHHBH"
HEADER_SIZE = struct.calcsize(HEADER_FORMAT)  # 9 bytes

# ------------------------------------------------------------- tamaños MTU --
MAX_PAYLOAD = 1400
MAX_PACKET_SIZE = HEADER_SIZE + MAX_PAYLOAD

# ----------------------------------------------- espacio de secuencias SEQ --
# El campo SEQ es uint16 -> 2^16 valores (0..65535)
SEQ_BITS = 16
MAX_SEQ = 1 << SEQ_BITS


# ------------------------------------------------------- checksum RFC 1071 --
def checksum(data: bytes) -> int:
    """Internet checksum 16-bit one's-complement (RFC 1071)."""
    if len(data) % 2 != 0:
        data += b"\x00"
    total = 0
    for i in range(0, len(data), 2):
        word = (data[i] << 8) + data[i + 1]
        total += word
        total = (total & 0xFFFF) + (total >> 16)  # fold de carries
    return ~total & 0xFFFF


# ---------------------------------------------------------- serializacion --
def build_packet(seq: int, ack: int, flags: int, payload: bytes = b"") -> bytes:
    seq &= 0xFFFF
    ack &= 0xFFFF
    length = len(payload)
    header_no_ck = struct.pack(HEADER_FORMAT, seq, ack, length, flags, 0)
    ck = checksum(header_no_ck + payload)
    header = struct.pack(HEADER_FORMAT, seq, ack, length, flags, ck)
    return header + payload


def parse_packet(data: bytes):
    """Parsea un datagrama recibido. Devuelve dict o None si esta corrupto"""
    if len(data) < HEADER_SIZE:
        return None
    seq, ack, length, flags, ck = struct.unpack(HEADER_FORMAT, data[:HEADER_SIZE])
    if len(data) < HEADER_SIZE + length:
        # truncado: declara mas payload del que llego
        return None
    payload = data[HEADER_SIZE : HEADER_SIZE + length]
    header_no_ck = struct.pack(HEADER_FORMAT, seq, ack, length, flags, 0)
    if checksum(header_no_ck + payload) != ck:
        return None
    return {
        "seq": seq,
        "ack": ack,
        "length": length,
        "flags": flags,
        "payload": payload,
    }
