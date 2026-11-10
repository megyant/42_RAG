import bm25s
from .models import DataSource, MinimalSource
from .helpers import (PROCESSED_PATH, Colors, RetrievalError, BM25_FOLDER,
                      CHUNK_FILE, WORD_ERROR, CHUNK_ERROR, ParseError)
import os
import re
import json
from typing import Any

WORD = re.compile(r"\w+")
PARTS = re.compile(r"[A-Z]+(?=[A-Z][a-z])|[A-Z]?[a-z]+|[A-Z]+|\d+")


def code_splitter(text: str) -> list[str]:
    tokens = []
    for word in WORD.findall(text):
        tokens.append(word)
        parts = PARTS.findall(word)
        if len(parts) > 1:
            tokens.extend(parts)

    return [t.lower() for t in tokens]


def make_tokenizer() -> bm25s.tokenization.Tokenizer:
    return bm25s.tokenization.Tokenizer(splitter=code_splitter,
                                        lower=False,
                                        stopwords="en")


def create_indexable_data(chunks: list[DataSource]) -> None:
    texts = [c.content for c in chunks]

    tokenizer = make_tokenizer()
    tokens = tokenizer.tokenize(texts, return_as="tuple",
                                update_vocab=True)

    retriever = bm25s.BM25()
    retriever.index(tokens)
    output_dir = os.path.join(PROCESSED_PATH, BM25_FOLDER)

    try:
        retriever.save(output_dir)
    except OSError as e:
        raise RetrievalError(f"Could not write index: {e.strerror}")

    print(f"{Colors.BOLD}{Colors.GREEN}Success:{Colors.END} Indexing "
          "complete. Saved under "
          f"'{output_dir}'.")


def load_index() -> tuple[Any, list[dict[str, Any]]]:
    output_dir_bm25 = os.path.join(PROCESSED_PATH, BM25_FOLDER)
    output_dir_chunks = os.path.join(PROCESSED_PATH, CHUNK_FILE)

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

    tokenizer = make_tokenizer()

    query_tokens = tokenizer.tokenize([query],
                                      return_as="tuple",
                                      update_vocab=True)

    if not isinstance(query_tokens, bm25s.tokenization.Tokenized):
        raise RetrievalError("Tokenizer returned an unexpected type")

    has_words = any(word != "" for word in query_tokens.vocab)
    if not has_words:
        return [], WORD_ERROR

    documents, scores = retriever.retrieve(query_tokens=query_tokens,
                                           corpus=chunk_list,
                                           k=k)
    has_score = any(score != 0. for score in scores[0])
    if not has_score:
        return [], CHUNK_ERROR

    return build_sources(documents[0]), None


def build_sources(documents_row: list) -> list[MinimalSource]:
    return [MinimalSource.model_validate(chunk) for
            chunk in documents_row]
