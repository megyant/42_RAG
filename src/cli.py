from .parser.parse_values import parse_max_chunk_size
from .ingesting import collect_files
from .chunking import chunk_markdown, chunk_text, chunk_python
from .helpers import ParseError

"""
index –max_chunk_size <int>
search <query> –k <int>
search_dataset –dataset_path <path> –k <int> –save_directory <dir>
answer <query> –k <int>
answer_dataset –student_search_results_path <path> –save_directory <dir>
evaluate –student_search_results_path <path> –dataset_path <path>
"""


""" from models import (MinimalSource, UnansweredQuestion,
                    AnsweredQuestion, RagDataset,
                    MinimalSearchResults, MinimalAnswer,
                    StudentSearchResults,
                    StudentSearchResultsAndAnswer) """

""" Each should create a manager with the customized values """


class Cli:
    def index(self, max_chunk_size: int = 2000) -> int:
        max_chunk_size = parse_max_chunk_size(max_chunk_size)

        all_paths = collect_files()

        for path in all_paths:
            suffix = path.suffix.lower()

            if suffix == ".py":
                chunk_python(max_chunk_size, path)

            elif suffix == ".md":
                chunk_markdown(max_chunk_size, path)

            elif suffix == ".txt":
                chunk_text(max_chunk_size, path)

        return max_chunk_size

    def search(self, query: str, k: int = 10) -> None:
        try:
            k = int(k)
        except ValueError:
            raise ParseError(f"'k'({k}) must be an integer")

        if k <= 0:
            raise ParseError("'k' needs to be > 0")

        if query is None:
            raise ParseError("'query' cannot be empty")

    def search_dataset(self, dataset_path: str, save_directory: str,
                       k: int = 10) -> None:
        ...

    def answer(self, query: str, k: int) -> None:
        ...

    def answer_dataset(self, student_search_results_path: str,
                       save_directory: str) -> None:
        ...

    def evaluate(self, student_search_results_path: str,
                 dataset_path: str) -> None:
        ...
