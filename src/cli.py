from .parser.parse_values import IndexArgs, SearchArgs, SearchDataArgs
from .models import DataSource
from .ingesting import collect_files, load_questions
from .chunking import Chunk
from .helpers import ParseError, Colors
from .create_data_results import save_index
from .retrieval import create_indexable_data, retrieve_sources, load_index
from tqdm import tqdm
from pydantic import ValidationError

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
        try:
            args = IndexArgs(max_chunk_size=max_chunk_size)
        except ValidationError as e:
            msgs = [f"'{err['loc'][0]}' - {err['msg']}" for err in e.errors()]
            raise ParseError("\n".join(msgs)) from None

        all_paths = collect_files()
        chunk = Chunk(args.max_chunk_size)
        chunks: list[DataSource] = []

        for path in tqdm(all_paths, desc="Ingestion", leave=False):
            suffix = path.suffix.lower()

            if suffix == ".py":
                chunks.extend(chunk.chunk_python(path))

            elif suffix == ".md":
                chunks.extend(chunk.chunk_markdown(path))

            elif suffix == ".txt":
                chunks.extend(chunk.chunk_text(path))

        save_index(chunks=chunks)
        create_indexable_data(chunks=chunks)

    def search(self, query: str, k: int = 10) -> None:
        try:
            args = SearchArgs(k=k, query=query)
        except ValidationError as e:
            msgs = [f"'{err['loc'][0]}' - {err['msg']}" for err in e.errors()]
            raise ParseError("\n".join(msgs)) from None

        retriever, chunk_list = load_index()

        if args.k > len(chunk_list):
            raise ParseError(f"k={k} is larger than the {len(chunk_list)} "
                             "chunks in the index")

        sources = retrieve_sources(args.query, args.k, retriever, chunk_list)

        for i, source in enumerate(sources, 1):
            print(f"{Colors.BOLD}{Colors.BLUE}Result {i}:{Colors.END} "
                  f"{source}")

    def search_dataset(self, dataset_path: str, save_directory: str,
                       k: int = 10) -> None:
        try:
            args = SearchDataArgs(dataset_path=dataset_path,
                                  save_directory=save_directory,
                                  k=k)
        except ValidationError as e:
            msgs = [f"'{err['loc'][0]}' - {err['msg']}" for err in e.errors()]
            raise ParseError("\n".join(msgs)) from None

        retriever, chunk_list = load_index()

        if args.k > len(chunk_list):
            raise ParseError(f"k={k} is larger than the {len(chunk_list)} "
                             "chunks in the index")

        questions = load_questions(args.dataset_path)

        for question in tqdm(questions,
                             desc="Searching Datasets",
                             leave=False):
            print(question)

    def answer(self, query: str, k: int) -> None:
        ...

    def answer_dataset(self, student_search_results_path: str,
                       save_directory: str) -> None:
        ...

    def evaluate(self, student_search_results_path: str,
                 dataset_path: str) -> None:
        ...


"""
#TODO
- Call retrieve_sources in the loop
- Build MinimalSearchResults per question
- Build a StudentSeachResults around the list
- Save to the save_directory/nameofdataset.json


- Answer, answer_dataset, evaluate, README

- Reorganize folders, test
"""
