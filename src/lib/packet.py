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

# ASK
HEADER_FORMAT = "!HHHBH"
HEADER_SIZE = struct.calcsize(HEADER_FORMAT)  # 9 bytes
MAX_PAYLOAD = 1400  # bytes (para evitar fragmentación IP)
MAX_PACKET_SIZE = HEADER_SIZE + MAX_PAYLOAD
MAX_SEQ = 1 << 16

# TODO: hay espacio maybe para "piggybacking" de ACK+FIN por ejemplo.
FLAG_DATA = 0x01
FLAG_ACK = 0x02
FLAG_FIN = 0x04
FLAG_HANDSHAKE = 0x08
FLAG_ERROR = 0x10


# RFC 1071 (16 bits)
def checksum(data: bytes) -> int:
    if len(data) % 2 != 0:
        data += b"\x00"
    total = 0
    for i in range(0, len(data), 2):
        word = (data[i] << 8) + data[i + 1]
        total += word
        total = (total & 0xFFFF) + (total >> 16)
    return ~total & 0xFFFF


# build [ HEADER | PAYLOAD ]
def build_packet(seq: int, ack: int, flags: int, payload: bytes = b"") -> bytes:
    # Campos SEQ/ACK son de 16 bits en el header.
    seq &= 0xFFFF
    ack &= 0xFFFF
    length = len(payload)
    header = struct.pack(
        HEADER_FORMAT, seq, ack, length, flags, 0
    )  # rturns invariant bytes obj
    ck = checksum(header + payload)
    header = struct.pack(HEADER_FORMAT, seq, ack, length, flags, ck)
    return header + payload


def parse_packet(data: bytes):
    if len(data) < HEADER_SIZE:
        return None
    seq, ack, length, flags, _ck = struct.unpack(HEADER_FORMAT, data[:HEADER_SIZE])
    if len(data) < HEADER_SIZE + length:
        # truncado: declara mas payload del que llego
        return None
    payload = data[HEADER_SIZE : HEADER_SIZE + length]
    # RFC 1071: la suma 1's-complement sobre todos los
    # bytes recibidos debe foldear a all-ones (0xFFFF).
    # `checksum()` devuelve el complemento, así que el
    # caso válido es 0x0000. si no, ignoramos el paquete (RDT 3.0)
    if checksum(data[: HEADER_SIZE + length]) != 0x0000:
        return None
    return {
        "seq": seq,
        "ack": ack,
        "length": length,
        "flags": flags,
        "payload": payload,
    }


def create_handshake_packet(
    operation: str,
    filename: str,
    protocol: str = None,
    file_size: int = 0,
) -> bytes:
    """HANDSHAKE: payload = "OPERATION|filename|protocol|file_size".

    `protocol` y `file_size` son opcionales; si no se conocen se
    envían vacío y 0 respectivamente. `file_size` es informativo
    (uploads): el servidor puede loggear/validar el tamaño final.
    """
    parts = [operation, filename, protocol or "", str(int(file_size))]
    payload = "|".join(parts).encode()
    return build_packet(0, 0, FLAG_HANDSHAKE, payload)


def create_data_packet(seq: int, payload: bytes) -> bytes:
    return build_packet(seq, 0, FLAG_DATA, payload)


def create_ack_packet(seq: int) -> bytes:
    return build_packet(0, seq, FLAG_ACK)


def create_fin_packet(next_seq: int = 0) -> bytes:
    """FIN del sender.

    `next_seq` lleva el número de secuencia que el sender habría
    usado a continuación (en SR: total de chunks; en SW: el alternate
    bit que tocaba). El receptor identifica la terminacion por el flag,
    pero el nro ayuda a correlacionar el ACK(FIN) y a descartar FINs
    rezagados de sesiones previas.
    """
    return build_packet(next_seq, 0, FLAG_FIN)


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
            chunk = f.read(chunk_size)  # b"" = empty bytes = EOF
            if not chunk:
                break
            yield seq, chunk
            seq += 1
