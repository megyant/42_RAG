""" Separate by function or classes """
from .chunk import Chunk
from pathlib import Path
from src import ChunkData


class ChunkCode(Chunk):
    def chunk(self, path: Path, text: str) -> list[ChunkData]:
        return []
