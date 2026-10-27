from pathlib import Path
from ..ingesting import read_file, split_endings
import ast


def chunk_python(max_chunk_size: int, file: Path):
    print("Chunking a .py file")
    overlap = int(max_chunk_size * 0.10)

    text = read_file(file)
    if text is None:
        return []

    lines = split_endings(text)
    offsets = [0]
    for line in lines:
        offsets.append(offsets[-1] + len(line))

    try:
        tree = ast.parse(text)
    except (SyntaxError, ValueError, RecursionError):
        print(f'\nAST failed for {file}, falling back to line chunking\n')
        return manual_split(max_chunk_size, overlap, text)


"""     for node in tree.body:
        start = node.lineno
        if getattr(node, "decorator_list", None):
            start = min(start, node.decorator_list[0].lineno)
        end = node.end_lineno
        body = "".join(lines[start - 1: end])
        print(node.__class__.__name__, start, end)
        # Type(class, function, etc), beginning, end """


def manual_split(max_chunk_size: int, overlap: int,
                 text: str) -> list[dict[str, str | int]]:
    result: list[dict[str, str | int]] = []
    start = 0
    count = 0

    while start < len(text):
        end = start + max_chunk_size

        chunk: dict[str, str | int] = {
            "start": start,
            "end": end,
            "text":  text[start:end]
        }
        count += 1
        result.append(chunk)
        start += (max_chunk_size - overlap)

    print(f"Result: {len(result)}")

    return result


def chunk_markdown(max_chunk_size: int, file: Path):
    ...


def chunk_text(max_chunk_size: int,
               file: Path) -> list[dict[str, str | int]]:
    print("Chunking a .txt file")

    overlap = int(max_chunk_size * 0.10)
    text = read_file(file)
    if text is None:
        return []

    result = manual_split(max_chunk_size, overlap, text)

    return result
