from pydantic import BaseModel, ValidationError
from ..helpers.models import (DataSource, MinimalSearchResults,
                              StudentSearchResults, MinimalAnswer,
                              StudentSearchResultsAndAnswer)
from ..helpers import (Colors, Paths,
                       IndexingError, RetrievalError)
from pathlib import Path
import os


class ChunkIndex(BaseModel):
    """
    Container model representing an indexed collection of data
    chunks.
    """
    chunks: list[DataSource]


def save_index(chunks: list[DataSource],
               output_path: str = Paths.PROCESSED_PATH) -> None:
    """
    Serialize and save a list of data chunks to a JSON index file in the
    specified output directory.

    Args:
        chunks (list[DataSource]): The list of data chunks to index and save.
        output_path (str): The directory where the index file will be
        stored. Defaults to Paths.PROCESSED_PATH.

    Raises:
        IndexingError: If validation of the chunk index fails or an I/O
        error occurs during saving.
    """

    output_dir = Path(output_path)

    try:
        data = ChunkIndex(chunks=chunks)
    except ValidationError as e:
        raise IndexingError(f"Could not write index: {e.errors()[0]['type']}")

    try:
        output_dir.mkdir(parents=True, exist_ok=True)

        path = os.path.join(output_dir, Paths.CHUNK_FILE)

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
    """
    Serialize and save student search results to a JSON file.

    Args:
        search_results (list[MinimalSearchResults]): The list of search
        result items to save.
        output_path (str): The target output directory path.
        k (int): The number of retrieved sources per query.
        filename (str): The name of the output file.

    Raises:
        RetrievalError: If data validation fails or an I/O error occurs
        while writing the file.
    """

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
    """
    Serialize and save generated student answers and search results to a
    JSON file.

    Args:
        answers (list[MinimalAnswer]): The list of answer items to save.
        output_path (str): The target output directory path.
        k (int): The number of retrieved sources per query.
        filename (str): The name of the output file.

    Raises:
        RetrievalError: If data validation fails or an I/O error occurs
        while writing the file.
    """

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

        print(f"{Colors.BOLD}{Colors.GREEN}Success:{Colors.END} Answer "
              "complete. Saved under "
              f"'{output_dir}'.")
    except OSError as e:
        raise RetrievalError(f"Could not write results: {e.strerror}")
