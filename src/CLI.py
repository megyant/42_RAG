"""
index –max_chunk_size <int>
search <query> –k <int>
search_dataset –dataset_path <path> –k <int> –save_directory <dir>
answer <query> –k <int>
answer_dataset –student_search_results_path <path> –save_directory <dir>
evaluate –student_search_results_path <path> –dataset_path <path>
"""


from models import (MinimalSource, UnansweredQuestion,
                    AnsweredQuestion, RagDataset,
                    MinimalSearchResults, MinimalAnswer,
                    StudentSearchResults,
                    StudentSearchResultsAndAnswer)


class Cli:
    def index(self, max_chunk_ize: int = 2000):
        pass

    def search(self, query: str, k: int = 10):
        pass

    def search_dataset(self, dataset_path: str, k: int = 10,
                       save_directory: str = "data/output/search_results/"):
        pass

    def answer(self, query: str, k: int = 10):
        pass

    def answer_dataset(student_search_results_path: str, dataset_path: str):
        pass

    def evaluate(student_search_results_path: str, dataset_path: str):
        pass
