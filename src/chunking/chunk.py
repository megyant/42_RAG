from pathlib import Path
from . import read_file
from langchain_text_splitters import (Language,
                                      RecursiveCharacterTextSplitter)
from ..helpers.models import DataSource
from ..helpers import Const


class Chunk:
    """
    A utility class for chunking text files and raw strings into smaller
    DataSource models.
    """
    def __init__(self, max_chunk_size: int):
        """
        Initialize the Chunk instance with a maximum chunk size and
        calculated overlap.
        """
        self.max_chunk_size = max_chunk_size
        self.overlap = int(max_chunk_size * Const.OVERLAP)

    def chunk_python(self, file: Path) -> list[DataSource]:
        """
        Split a Python source file into chunks using a language-aware
        recursive splitter.

        Args:
            file (Path): The path to the Python file to be chunked.

        Returns:
            list[DataSource]: A list of DataSource models representing the
            file chunks.
        """
        text = read_file(file)
        if text is None:
            return []

        result: list[DataSource] = []

        splitter = RecursiveCharacterTextSplitter.from_language(
            language=Language.PYTHON,
            chunk_size=self.max_chunk_size,
            chunk_overlap=self.overlap,
            keep_separator=True,
            add_start_index=True
        )

        for document in splitter.create_documents([text]):
            start_index = document.metadata["start_index"]
            end_index = start_index + len(document.page_content)
            size = len(document.page_content)
            model = self.build_model(file, start_index,
                                     end_index,
                                     size,
                                     document.page_content)
            result.append(model)
        return result

    def chunk_manual(self, text: str, file: Path) -> list[DataSource]:
        """
        Split raw text into fixed-size chunks manually based on
        max_chunk_size and overlap.

        Args:
            text (str): The raw text string to be chunked.
            file (Path): The path associated with the text source.

        Returns:
            list[DataSource]: A list of DataSource models representing the
            manual chunks.
        """
        result: list[DataSource] = []
        start_index = 0

        while start_index < len(text):
            end_index = min(start_index + self.max_chunk_size, len(text))

            model = self.build_model(file, start_index,
                                     end_index,
                                     len(text[start_index:end_index]),
                                     text[start_index:end_index])

            result.append(model)

            if end_index == len(text):
                break

            start_index += (self.max_chunk_size - self.overlap)

        return result

    def chunk_markdown(self, file: Path) -> list[DataSource]:
        """
        Split a Markdown source file into chunks using a language-aware
        recursive splitter.

        Args:
            file (Path): The path to the Markdown file to be chunked.

        Returns:
            list[DataSource]: A list of DataSource models representing the
            file chunks.
        """
        text = read_file(file)
        if text is None:
            return []

        result: list[DataSource] = []

        splitter = RecursiveCharacterTextSplitter.from_language(
            language=Language.MARKDOWN,
            chunk_size=self.max_chunk_size,
            chunk_overlap=self.overlap,
            keep_separator=True,
            add_start_index=True
        )

        for document in splitter.create_documents([text]):
            start_index = document.metadata["start_index"]
            end_index = start_index + len(document.page_content)
            size = len(document.page_content)
            model = self.build_model(file,
                                     start_index,
                                     end_index,
                                     size,
                                     document.page_content)
            result.append(model)
        return result

    def chunk_text(self, file: Path) -> list[DataSource]:
        """
        Read and split a plain text file into chunks.

        Args:
            file (Path): The path to the text file to be chunked.

        Returns:
            list[DataSource]: A list of DataSource models representing the
            file chunks.
        """

        text = read_file(file)
        if text is None:
            return []

        result = self.chunk_manual(text,
                                   file)

        return result

    def build_model(self, path: Path, start: int, end: int,
                    size: int, text: str) -> DataSource:
        """
        Construct and return a DataSource model from chunk parameters.

        Args:
            path (Path): The file path associated with the chunk.
            start (int): The starting character index of the chunk.
            end (int): The ending character index of the chunk.
            size (int): The character length of the chunk content.
            text (str): The text content of the chunk.

        Returns:
            DataSource: The instantiated DataSource model.
        """
        model = DataSource(
            file_path=str(path),
            first_character_index=start,
            last_character_index=end,
            size=size,
            content=text
        )

        return model
