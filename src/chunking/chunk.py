from abc import ABC, abstractmethod
from pathlib import Path
from src import ChunkData
from ..ingesting import read_file


class Chunk (ABC):
    def __init__(self, max_chunk_size: int) -> None:
        self.max_chunk_size = max_chunk_size

    @abstractmethod
    def chunk(self, path: Path, text: str) -> list[ChunkData]:
        ...

    @classmethod
    def strategy(cls, path: Path) -> type["Chunk"] | None:
        from .chunk_code import ChunkCode

        file_type: dict[str, type["Chunk"]] = {
            ".py": ChunkCode
        }

        selected = file_type.get(path.suffix.lower())

        return selected


def chunk_python(max_chunk_size: int, path: Path):
    text = read_file(path)



def chunk_markdown(max_chunk_size: int, file: Path):
    print("Sucessfully diverted to chunk_markdown")


def chunk_text(max_chunk_size: int, file: Path):
    print("Sucessfully diverted to chunk_text")
