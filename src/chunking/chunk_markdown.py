""" separate by headings """
from .chunk import Chunk
from pathlib import Path
from src import ChunkData


class ChunkMarkdown(Chunk):
    def chunk(self, path: Path, text: str) -> list[ChunkData]:
        return []
