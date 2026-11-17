from src.helpers import Const
from pydantic import BaseModel, Field


class CliArgs(BaseModel):
    ...


class IndexArgs(CliArgs):
    max_chunk_size: int = Field(Const.MAX_CHUNK_SIZE,
                                ge=100, le=Const.MAX_CHUNK_SIZE)


class SearchArgs(CliArgs):
    query: str = Field(min_length=1)
    k: int = Field(10, ge=1, strict=True)


class SearchDataArgs(CliArgs):
    dataset_path: str
    save_directory: str
    k: int = Field(10, ge=1, strict=True)


class AnswerArgs(CliArgs):
    query: str = Field(min_length=1)
    k: int = Field(10, ge=1, strict=True)


class AnswerDataArgs(CliArgs):
    student_search_results_path: str
    save_directory: str


class EvaluateArgs(CliArgs):
    student_search_results_path: str
    dataset_path: str
