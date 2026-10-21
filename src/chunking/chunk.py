from pathlib import Path
from ..ingesting import read_file


def chunk_python(max_chunk_size: int, path: Path):
    text = read_file(path)



def chunk_markdown(max_chunk_size: int, file: Path):
    print("Sucessfully diverted to chunk_markdown")


def chunk_text(max_chunk_size: int, file: Path):
    print("Sucessfully diverted to chunk_text")
