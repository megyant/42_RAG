from abc import ABC, abstractmethod


class Chunk (ABC):
    @abstractmethod
    def chunk(path, text) -> list[ChunkData]:
        ...
