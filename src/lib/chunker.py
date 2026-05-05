from lib.wire import MAX_PAYLOAD


def read_file_chunks(filepath: str, chunk_size: int = MAX_PAYLOAD):
    """lee un archivo y lo particiona en chunks de `MAX_PAYLOAD` bytes."""
    with open(filepath, "rb") as f:
        seq = 0
        while True:
            chunk = f.read(chunk_size)  # b"" en EOF
            if not chunk:
                break
            yield seq, chunk
            seq += 1
