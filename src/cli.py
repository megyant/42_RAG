from .manager import Manager
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
    def index(self, max_chunk_size: int = 2000) -> None:
        Manager().index(max_chunk_size)

    def search(self, query: str, k: int = 10) -> None:
        Manager().search(query, k)

    def search_dataset(self, dataset_path: str, save_directory: str,
                       k: int = 10) -> None:
        Manager().search_dataset(dataset_path, k, save_directory)

    def answer(self, query: str, k: int) -> None:
        Manager().answer(query, k)

    def answer_dataset(self, student_search_results_path: str,
                       save_directory: str) -> None:
        Manager().answer_dataset(student_search_results_path, save_directory)

    def evaluate(self, student_search_results_path: str,
                 dataset_path: str) -> None:
        Manager().evaluate(student_search_results_path, dataset_path)
