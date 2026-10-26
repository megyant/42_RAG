from pathlib import Path
from ..ingesting import read_file, split_endings
import ast


def chunk_python(max_chunk_size: int, path: Path):
    overlap = max_chunk_size // 10
    
    text = read_file(path)
    if text is None:
        return []

    lines = split_endings(text)
    offsets = [0]
    for line in lines:
        offsets.append(offsets[-1] + len(line))

    try:
        tree = ast.parse(text)
    except (SyntaxError, ValueError, RecursionError):
        print(f'"AST failed for {path}, falling back to line chunking')
        return []


"""     for node in tree.body:
        start = node.lineno
        if getattr(node, "decorator_list", None):
            start = min(start, node.decorator_list[0].lineno)
        end = node.end_lineno
        body = "".join(lines[start - 1: end])
        print(node.__class__.__name__, start, end)
        # Type(class, function, etc), beginning, end """


def manual_split(max_chunk_size: int, overlap: int, text: str) -> dict[int, int, str]:
    ...


def chunk_markdown(max_chunk_size: int, file: Path):
    print("Sucessfully diverted to chunk_markdown")


def chunk_text(max_chunk_size: int, file: Path):
    print("Sucessfully diverted to chunk_text")


"""
How to divide a python file

1. class

2. methods
"""
