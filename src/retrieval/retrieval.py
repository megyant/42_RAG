import bm25s
from ..helpers.models import DataSource, MinimalSource
from ..helpers import (Colors, RetrievalError, Const, ParseError,
                       Paths)
import os
import re
import json
from typing import Any

WORD = re.compile(r"\w+")
PARTS = re.compile(r"[A-Z]+(?=[A-Z][a-z])|[A-Z]?[a-z]+|[A-Z]+|\d+")


def code_splitter(text: str) -> list[str]:
    """
    Split text into words and sub-tokens using regex patterns,
    returning lowercase tokens.

    Args:
        text (str): The input text string to split.

    Returns:
        list[str]: A list of lowercase tokens extracted from the text.
    """
    tokens = []
    for word in WORD.findall(text):
        tokens.append(word)
        parts = PARTS.findall(word)
        if len(parts) > 1:
            tokens.extend(parts)

    return [t.lower() for t in tokens]


def make_tokenizer() -> bm25s.tokenization.Tokenizer:
    """
    Create and configure a bm25s Tokenizer using the custom code
    splitter and English stopwords.

    Returns:
        bm25s.tokenization.Tokenizer: The configured tokenizer instance.
    """
    return bm25s.tokenization.Tokenizer(splitter=code_splitter,
                                        lower=False,
                                        stopwords="en")


def create_indexable_data(chunks: list[DataSource]) -> None:
    """
    Create a BM25 index from data chunks and save it to the processed
    output directory.

    Args:
        chunks (list[DataSource]): The list of data chunks to index.

    Raises:
        RetrievalError: If an I/O error occurs while saving the BM25 index.
    """
    texts = [c.file_path.replace(Paths.RAW_PATH, "") + "\n" +
             c.content for c in chunks]

    tokenizer = make_tokenizer()
    tokens = tokenizer.tokenize(texts, return_as="tuple",
                                update_vocab=True)

    retriever = bm25s.BM25()
    retriever.index(tokens)
    output_dir = os.path.join(Paths.PROCESSED_PATH, Paths.BM25_FOLDER)

    try:
        retriever.save(output_dir)
    except OSError as e:
        raise RetrievalError(f"Could not write index: {e.strerror}")

    print(f"{Colors.BOLD}{Colors.GREEN}Success:{Colors.END} Indexing "
          "complete. Saved under "
          f"'{output_dir}'.")


def load_index() -> tuple[Any, list[dict[str, Any]]]:
    """
    Load the BM25 retriever index and chunk data from disk.

    Returns:
        tuple[Any, list[dict[str, Any]]]: A tuple containing the loaded
        retriever and the list of chunk dictionaries.

    Raises:
        RetrievalError: If the index files are missing, corrupted, or have
        a length mismatch.
    """
    output_dir_bm25 = os.path.join(Paths.PROCESSED_PATH, Paths.BM25_FOLDER)
    output_dir_chunks = os.path.join(Paths.PROCESSED_PATH, Paths.CHUNK_FILE)

    try:
        retriever = bm25s.BM25.load(output_dir_bm25)

        with open(output_dir_chunks, 'r', encoding="utf-8") as f:
            chunks = json.load(f)

        chunk_list = chunks["chunks"]

    except OSError as e:
        raise RetrievalError(f"Index not found: {e.strerror}. "
                             "Run 'python -m src index'")
    except (json.JSONDecodeError, KeyError):
        raise RetrievalError(f"'{output_dir_chunks}' is corrupted. "
                             "Run 'python -m src index' again")

    if len(chunk_list) != retriever.scores["num_docs"]:
        raise RetrievalError("Number of chunks and number of "
                             "retrieved indexes do not match")

    return retriever, chunk_list


def prepare_retrieval(k: int) -> tuple[Any, list[dict[str, Any]]]:
    """
    Prepare for retrieval by loading the index and validating that
    k does not exceed the chunk count.

    Args:
        k (int): The number of results to retrieve.

    Returns:
        tuple[Any, list[dict[str, Any]]]: The loaded retriever and chunk list.

    Raises:
        ParseError: If k is greater than the total number of chunks.
    """
    retriever, chunk_list = load_index()

    if k > len(chunk_list):
        raise ParseError(f"k={k} is larger than the "
                         f"{len(chunk_list)} "
                         "chunks in the index")

    return retriever, chunk_list


def retrieve_sources(query: str, k: int,
                     retriever: Any,
                     chunk_list: list[dict[str, Any]]) -> \
                         tuple[list[MinimalSource], str | None]:
    """
    Retrieve top-k matching MinimalSource items for a given search query.

    Args:
        query (str): The search query string.
        k (int): The number of sources to retrieve.
        retriever (Any): The BM25 retriever instance.
        chunk_list (list[dict[str, Any]]): The list of available data chunks.

    Returns:
        tuple[list[MinimalSource], str | None]: A tuple containing the
        list of retrieved sources and an optional warning code.

    Raises:
        RetrievalError: If the tokenizer returns an unexpected type.
    """

    tokenizer = make_tokenizer()

    query_tokens = tokenizer.tokenize([query],
                                      return_as="tuple",
                                      update_vocab=True)

    if not isinstance(query_tokens, bm25s.tokenization.Tokenized):
        raise RetrievalError("Tokenizer returned an unexpected type")

    has_words = any(word != "" for word in query_tokens.vocab)
    if not has_words:
        return [], Const.WORD_ERROR

    documents, scores = retriever.retrieve(query_tokens=query_tokens,
                                           corpus=chunk_list,
                                           k=k)
    has_score = any(score != 0. for score in scores[0])
    if not has_score:
        return [], Const.CHUNK_ERROR

    return build_sources(documents[0]), None


def build_sources(documents_row: list[Any]) -> list[MinimalSource]:
    """
    Convert raw retrieved document rows into validated MinimalSource models.

    Args:
        documents_row (list[Any]): A list of raw document/chunk
        dictionaries from retrieval.

    Returns:
        list[MinimalSource]: A list of validated MinimalSource model instances.
    """
    return [MinimalSource.model_validate(chunk) for
            chunk in documents_row]
