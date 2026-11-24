from pydantic import BaseModel, Field
from typing import List
import uuid


class MinimalSource(BaseModel):
    """
    A minimal reference to a source file containing
    character indices.
    """
    file_path: str
    first_character_index: int
    last_character_index: int


class DataSource(MinimalSource):
    """
    A data source extending MinimalSource with size and
    content attributes.
    """
    size: int = Field(exclude=True)
    content: str


class UnansweredQuestion(BaseModel):
    """Represents a question without an associated answer or sources."""
    question_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    question: str


class AnsweredQuestion(UnansweredQuestion):
    """Represents a question that has been answered with supporting sources."""
    sources: List[MinimalSource]
    answer: str


class RagDataset(BaseModel):
    """
    A collection of RAG questions containing both answered and
    unanswered questions.
    """
    rag_questions: List[AnsweredQuestion | UnansweredQuestion]


class MinimalSearchResults(BaseModel):
    """Minimal search results associated with a specific question ID."""
    question_id: str
    question: str
    retrieved_sources: List[MinimalSource]


class SearchResponse(MinimalSearchResults):
    warning: str | None = None


class MinimalAnswer(MinimalSearchResults):
    """Extends MinimalSearchResults with an answer string."""
    answer: str


class AnswerResponse(MinimalAnswer):
    warning: str | None = None


class StudentSearchResults(BaseModel):
    """Container for student search results and the number of results (k)."""
    search_results: List[MinimalSearchResults]
    k: int


class StudentSearchResultsAndAnswer(BaseModel):
    """
    Container for search results with answers and the number of results
    (k).
    """
    search_results: List[MinimalAnswer]
    k: int
