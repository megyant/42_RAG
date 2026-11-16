from pydantic import BaseModel, ValidationError
from .models import (DataSource, MinimalSearchResults,
                     StudentSearchResults, MinimalAnswer,
                     StudentSearchResultsAndAnswer)
from .helpers import (PROCESSED_PATH, Colors, CHUNK_FILE,
                      IndexingError, RetrievalError)
from pathlib import Path
import os


class ChunkIndex(BaseModel):
    chunks: list[DataSource]


def save_index(chunks: list[DataSource],
               output_path: str = PROCESSED_PATH) -> None:

    output_dir = Path(output_path)

    try:
        data = ChunkIndex(chunks=chunks)
    except ValidationError as e:
        raise IndexingError(f"Could not write index: {e.errors()[0]['type']}")

    try:
        output_dir.mkdir(parents=True, exist_ok=True)

        path = os.path.join(output_dir, CHUNK_FILE)

        with open(path, "w",
                  encoding="utf-8") as f:
            f.write(data.model_dump_json(indent=4))
    except OSError as e:
        raise IndexingError(f"Could not write index: {e.strerror}")

    print(f"{Colors.BOLD}{Colors.GREEN}Success:{Colors.END} Ingestion "
          "complete. Saved under "
          f"'{output_dir}'.")


def save_search_results(search_results: list[MinimalSearchResults],
                        output_path: str,
                        k: int,
                        filename: str) -> None:

    output_dir = Path(output_path)

    try:
        data = StudentSearchResults(search_results=search_results, k=k)
    except ValidationError as e:
        raise RetrievalError("Could not write search results: "
                             f"{e.errors()[0]['type']}")

    try:
        output_dir.mkdir(parents=True, exist_ok=True)

        path = os.path.join(output_dir, filename)

        with open(path, "w",
                  encoding="utf-8") as f:
            f.write(data.model_dump_json(indent=4))
    except OSError as e:
        raise RetrievalError(f"Could not write results: {e.strerror}")

    print(f"{Colors.BOLD}{Colors.GREEN}Success:{Colors.END} Search "
          "complete. Saved under "
          f"'{output_dir}'.")


def save_answer_dataset(answers: list[MinimalAnswer],
                        output_path: str,
                        k: int,
                        filename: str) -> None:

    output_dir = Path(output_path)

    try:
        data = StudentSearchResultsAndAnswer(
            search_results=answers,
            k=k
        )
    except ValidationError as e:
        raise RetrievalError("Could not write search results: "
                             f"{e.errors()[0]['type']}")

    try:
        output_dir.mkdir(parents=True, exist_ok=True)
        path = os.path.join(output_dir, filename)

        with open(path, "w",
                  encoding="utf-8") as f:
            f.write(data.model_dump_json(indent=4))

        print(f"{Colors.BOLD}{Colors.GREEN}Success:{Colors.END} Search "
              "complete. Saved under "
              f"'{output_dir}'.")
    except OSError as e:
        raise RetrievalError(f"Could not write results: {e.strerror}")
