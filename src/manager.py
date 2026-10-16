from .ingesting import Ingest
from .helpers import ParseError
from .models import ChunkData
from .chunking import Chunk


class Manager:
    def __init__(self, raw_path="data/raw", processed_path="data/processed"):
        self.raw_path = raw_path
        self.processed_path = processed_path

    def pipeline(self):
        ...

    def index(self, max_chunk_size: int) -> None:
        try:
            max_chunk_size = int(max_chunk_size)
        except ValueError:
            raise ParseError("'max_chunk_size' "
                             f"({max_chunk_size}) "
                             "must be an integer")

        if max_chunk_size < 1:
            raise ParseError("'max_chunk_size' needs to be >= 1")
        if max_chunk_size > 2000:
            raise ParseError("'max_chunk_size' needs to be <= 2000")

        ingest = Ingest(self.raw_path)
        chunks: list[ChunkData] = []

        for path in ingest.collect_files():
            chunker = Chunk.selection(path, max_chunk_size)
            if chunker is None:
                continue

            text = ingest.read_file(path)
            if text is None:
                continue

            chunks += chunker.chunk(path, text)

        print(f"Indexed {len(chunks)} chunks -> {self.processed_path}")

    def search(self, query: str, k: int):
        try:
            k = int(k)
        except ValueError:
            raise ParseError(f"'k'({k}) must be an integer")

        if k <= 0:
            raise ParseError("'k' needs to be > 0")

        if query is None:
            raise ParseError("'query' cannot be empty")

    def search_dataset(self, dataset_path: str, k: int,
                       save_directory: str):
        return dataset_path, k, save_directory

    def answer(self, query: str, k: int):
        return query, k

    def answer_dataset(self, student_search_results_path: str,
                       save_directory: str):
        return student_search_results_path, save_directory

    def evaluate(self, student_search_results_path: str,
                 dataset_path: str):
        return student_search_results_path, dataset_path
