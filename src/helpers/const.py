from dataclasses import dataclass


@dataclass(frozen=True)
class Const:
    OVERLAP: float = 0.10
    MAX_CHUNK_SIZE: int = 2000
    WORD_ERROR: str = "WORD_ERROR"
    CHUNK_ERROR: str = "CHUNK_ERROR"
    MAX_CONTEXT: int = 32768
    MAX_NEW_TOKENS: int = 512


@dataclass(frozen=True)
class Paths:
    CHUNK_FILE: str = "chunks.json"
    BM25_FOLDER: str = "bm25"
    RAW_PATH: str = "data/raw"
    PROCESSED_PATH: str = "data/processed"
    DATASET_PATH: str = "data/datasets/UnansweredQuestions/"
    DATASET_PATH_CODE: str = ("data/datasets/UnansweredQuestions/"
                              "dataset_code_public.json")
    DATASET_PATH_DOCS: str = ("data/datasets/UnansweredQuestions/"
                              "dataset_docs_public.json")
    SAVE_DIRECTORY_SEARCH: str = ("data/output/search_results/"
                                  "UnansweredQuestions")
    SAVE_DIRECTORY_SEARCH_CODE: str = ("data/output/search_results/"
                                       "UnansweredQuestions/"
                                       "dataset_code_public.json")
    SAVE_DIRECTORY_SEARCH_DOCS: str = ("data/output/search_results/"
                                       "UnansweredQuestions/"
                                       "dataset_docs_public.json")
    SAVE_DIRECTORY_ANSWER: str = ("data/output/search_results_and_answer/"
                                  "UnansweredQuestions")
    SAVE_DIRECTORY_ANSWER_CODE: str = ("data/output/search_results_and_answer/"
                                       "UnansweredQuestions"
                                       "dataset_code_public.json")
    SAVE_DIRECTORY_ANSWER_DOCS: str = ("data/output/search_results_and_answer/"
                                       "UnansweredQuestions"
                                       "dataset_docs_public.json")
    ANSWERED_QUESTIONS_CODE: str = ("data/datasets/AnsweredQuestions/"
                                    "dataset_code_public.json")
    ANSWERED_QUESTIONS_DOCS: str = ("data/datasets/AnsweredQuestions/"
                                    "dataset_docs_public.json")
