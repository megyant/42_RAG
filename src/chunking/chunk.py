from pathlib import Path
from ..ingesting import read_file
import ast
from warnings import warn


def chunk_python(max_chunk_size: int, path: Path):
    text = read_file(path)
    if text is None:
        return []
    try:
        tree = ast.parse(text)
    except (SyntaxError, ValueError, RecursionError):
        warn(f'"AST failed for {path}, falling back to line chunking')


def chunk_markdown(max_chunk_size: int, file: Path):
    print("Sucessfully diverted to chunk_markdown")


def chunk_text(max_chunk_size: int, file: Path):
    print("Sucessfully diverted to chunk_text")


"""
How to divide a python file

1. class

2. methods
"""
