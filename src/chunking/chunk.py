from abc import ABC
from pydantic import BaseModel


class ChunkData(BaseModel):
    ...


class Chunk (ABC):
    def chunk(path, text) -> list[ChunkData]:
        ...
