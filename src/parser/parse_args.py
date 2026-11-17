from src.helpers import Const
from pydantic import BaseModel, Field


class CliArgs(BaseModel):
    """Base Pydantic model for command-line interface arguments."""
    ...


class IndexArgs(CliArgs):
    """
    Arguments for indexing operations, including constraints on
    maximum chunk size.
    """
    max_chunk_size: int = Field(Const.MAX_CHUNK_SIZE,
                                ge=100, le=Const.MAX_CHUNK_SIZE)


class SearchArgs(CliArgs):
    """
    Arguments for running a single search query with a specified
    result count (k).
    """
    query: str = Field(min_length=1)
    k: int = Field(10, ge=1, strict=True)


class SearchDataArgs(CliArgs):
    """
    Arguments for batch processing search datasets across specified paths
    and directories.
    """
    dataset_path: str
    save_directory: str
    k: int = Field(10, ge=1, strict=True)


class AnswerArgs(CliArgs):
    """
    Arguments for generating an answer for a single query with a specified
    result count (k).
    """
    query: str = Field(min_length=1)
    k: int = Field(10, ge=1, strict=True)


class AnswerDataArgs(CliArgs):
    """
    Arguments for batch processing answers using student
    search results.
    """
    student_search_results_path: str
    save_directory: str


class EvaluateArgs(CliArgs):
    """
    Arguments for evaluating student search results against a reference
    dataset path.
    """
    student_search_results_path: str
    dataset_path: str
