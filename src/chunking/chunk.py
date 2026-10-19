from abc import ABC, abstractmethod
from pathlib import Path
from src import ChunkData


class Chunk (ABC):
    def __init__(self, max_chunk_size: int) -> None:
        self.max_chunk_size = max_chunk_size

    @abstractmethod
    def chunk(self, path: Path, text: str) -> list[ChunkData]:
        ...

    @classmethod
    def strategy(cls, path: Path) -> type["Chunk"] | None:
        from .chunk_code import ChunkCode
        from .chunk_markdown import ChunkMarkdown

        file_type: dict[str, type["Chunk"]] = {
            ".py": ChunkCode,
            ".md": ChunkMarkdown,
            ".txt": ChunkMarkdown
        }

        selected = file_type.get(path.suffix.lower())

        return selected
