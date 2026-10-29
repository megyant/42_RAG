from pydantic import BaseModel
from .models import MinimalSource


class ChunkIndex(BaseModel):
    max_chunk_size: int
    chunks: List[MinimalSource]