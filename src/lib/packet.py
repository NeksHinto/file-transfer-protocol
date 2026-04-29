"""
Librería de paquetes - TP1 File Transfer Redes 2026

Header (9 bytes):
  SEQ    : 2 bytes  - numero de secuencia
  ACK    : 2 bytes  - numero de acuse de recibo
  LENGTH : 2 bytes  - tamaño del payload
  FLAGS  : 1 byte   - tipo de paquete
  CKSUM  : 2 bytes  - checksum de integridad

Flags:
  0x01 = DATA
  0x02 = ACK
  0x04 = FIN
  0x08 = HANDSHAKE
  0x10 = ERROR
"""

import struct

HEADER_FORMAT = "!HHHBH"
HEADER_SIZE = struct.calcsize(HEADER_FORMAT)  # 9 bytes
MAX_PAYLOAD = 1400 # bytes (para evitar fragmentación IP)
MAX_PACKET_SIZE = HEADER_SIZE + MAX_PAYLOAD
MAX_SEQ = 1 << 16

FLAG_DATA = 0x01
FLAG_ACK = 0x02
FLAG_FIN = 0x04
FLAG_HANDSHAKE = 0x08
FLAG_ERROR = 0x10


def checksum(data: bytes) -> int:
    if len(data) % 2 != 0:
        data += b"\x00"
    total = 0
    for i in range(0, len(data), 2):
        word = (data[i] << 8) + data[i + 1]
        total += word
        total = (total & 0xFFFF) + (total >> 16)
    return ~total & 0xFFFF


def build_packet(seq: int, ack: int, flags: int, payload: bytes = b"") -> bytes:
    # Campos SEQ/ACK son de 16 bits en el header.
    seq &= 0xFFFF
    ack &= 0xFFFF
    length = len(payload)
    header = struct.pack(HEADER_FORMAT, seq, ack, length, flags, 0)
    ck = checksum(header + payload)
    header = struct.pack(HEADER_FORMAT, seq, ack, length, flags, ck)
    return header + payload


def parse_packet(data: bytes):
    if len(data) < HEADER_SIZE:
        return None
    seq, ack, length, flags, ck = struct.unpack(HEADER_FORMAT, data[:HEADER_SIZE])
    payload = data[HEADER_SIZE : HEADER_SIZE + length]
    header = struct.pack(HEADER_FORMAT, seq, ack, length, flags, 0)
    if checksum(header + payload) != ck:
        return None
    return {
        "seq": seq,
        "ack": ack,
        "length": length,
        "flags": flags,
        "payload": payload,
    }


def create_handshake_packet(operation: str, filename: str, protocol: str = None) -> bytes:
    if protocol:
        payload = f"{operation}|{filename}|{protocol}".encode()
    else:
        payload = f"{operation}|{filename}".encode()
    return build_packet(0, 0, FLAG_HANDSHAKE, payload)


def create_data_packet(seq: int, payload: bytes) -> bytes:
    return build_packet(seq, 0, FLAG_DATA, payload)


def create_ack_packet(seq: int) -> bytes:
    return build_packet(0, seq, FLAG_ACK)


def create_fin_packet() -> bytes:
    return build_packet(0, 0, FLAG_FIN)


def create_error_packet(message: str) -> bytes:
    return build_packet(0, 0, FLAG_ERROR, message.encode())


def is_handshake(p):
    return bool(p["flags"] & FLAG_HANDSHAKE)


def is_data(p):
    return bool(p["flags"] & FLAG_DATA)


def is_ack(p):
    return bool(p["flags"] & FLAG_ACK)


def is_fin(p):
    return bool(p["flags"] & FLAG_FIN)


def is_error(p):
    return bool(p["flags"] & FLAG_ERROR)


def read_file_chunks(filepath: str, chunk_size: int = MAX_PAYLOAD):
    with open(filepath, "rb") as f:
        seq = 0
        while True:
            chunk = f.read(chunk_size)
            if not chunk:
                break
            yield seq, chunk
            seq += 1
