from pathlib import Path
from ..ingesting import read_file
from langchain_text_splitters import (Language,
                                      RecursiveCharacterTextSplitter)
from ..models import MinimalSource
from ..helpers import OVERLAP


class Chunk:
    def __init__(self, max_chunk_size: int):
        self.max_chunk_size = max_chunk_size
        self.overlap = int(max_chunk_size * OVERLAP)

    def chunk_python(self, file: Path) -> list[MinimalSource]:

        text = read_file(file)
        if text is None:
            return []

        result: list[MinimalSource] = []

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

    def chunk_manual(self, text: str, file: Path) -> list[MinimalSource]:
        result: list[MinimalSource] = []
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

    def chunk_markdown(self, file: Path):
        text = read_file(file)
        if text is None:
            return []

        result: list[MinimalSource] = []

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

    def chunk_text(self, file: Path) -> list[MinimalSource]:

        text = read_file(file)
        if text is None:
            return []

        result = self.chunk_manual(text,
                                   file)

        return result

    def build_model(self, path: Path, start: int, end: int,
                    size: int, text: str) -> MinimalSource:
        model = MinimalSource(
            file_path=str(path),
            first_character_index=start,
            last_character_index=end,
            size=size,
            content=text
        )

        return model
