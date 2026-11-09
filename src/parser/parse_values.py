from src.helpers import MAX_CHUNK_SIZE
from pydantic import BaseModel, Field


class CliArgs(BaseModel):
    ...


class IndexArgs(CliArgs):
    max_chunk_size: int = Field(MAX_CHUNK_SIZE, ge=100, le=MAX_CHUNK_SIZE)


class SearchArgs(CliArgs):
    query: str = Field(min_length=1)
    k: int = Field(10, ge=1, strict=True)


class SearchDataArgs(CliArgs):
    dataset_path: str
    save_directory: str
    k: int = Field(10, ge=1, strict=True)
