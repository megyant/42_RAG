from src.helpers import ParseError


def parse_max_chunk_size(max_chunk_size: int) -> int:
    try:
        max_chunk_size = int(max_chunk_size)
    except ValueError:
        raise ParseError("'max_chunk_size' "
                         f"({max_chunk_size}) "
                         "must be an integer")

    if max_chunk_size < 1:
        raise ParseError("'max_chunk_size' needs to be >= 1")
    if max_chunk_size > 2000:
        raise ParseError("'max_chunk_size' needs to be <= 2000")

    return max_chunk_size
