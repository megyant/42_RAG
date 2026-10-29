from pathlib import Path
from ..ingesting import read_file
from langchain_text_splitters import (Language,
                                      RecursiveCharacterTextSplitter)
from ..models import MinimalSource


def chunk_python(max_chunk_size: int,
                 file: Path) -> list[MinimalSource]:

    text = read_file(file)
    if text is None:
        return []

    overlap = int(max_chunk_size * 0.10)
    result: list[MinimalSource] = []

    splitter = RecursiveCharacterTextSplitter.from_language(
        language=Language.PYTHON,
        chunk_size=max_chunk_size,
        chunk_overlap=overlap,
        keep_separator=True,
        add_start_index=True
    )

    for document in splitter.create_documents([text]):
        start_index = document.metadata["start_index"]
        end_index = start_index + len(document.page_content)
        size = len(document.page_content)
        model = insert_data(file, start_index, end_index, size,
                            document.page_content)
        result.append(model)
    return result


def manual_split(max_chunk_size: int, overlap: int,
                 text: str, file: Path) -> list[MinimalSource]:
    result: list[MinimalSource] = []
    start_index = 0

    while start_index < len(text):
        end_index = min(start_index + max_chunk_size, len(text))

        model = insert_data(file, start_index,
                            end_index, len(text[start_index:end_index]),
                            text[start_index:end_index])

        result.append(model)

        if end_index == len(text):
            break

        start_index += (max_chunk_size - overlap)

    return result


def chunk_markdown(max_chunk_size: int, file: Path):
    ...


def chunk_text(max_chunk_size: int,
               file: Path) -> list[MinimalSource]:

    overlap = int(max_chunk_size * 0.10)
    text = read_file(file)
    if text is None:
        return []

    result = manual_split(max_chunk_size, overlap, text, file)

    return result


def insert_data(path: Path, start: int, end: int,
                size: int, text: str) -> MinimalSource:
    model = MinimalSource(
        file_path=str(path),
        first_character_index=start,
        last_character_index=end,
        size=size,
        content=text
    )

    return model
