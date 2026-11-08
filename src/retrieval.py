import bm25s
from .models import DataSource
from .helpers import (PROCESSED_PATH, Colors, RetrievalError, BM25_FOLDER,
                      CHUNK_FILE)
import os
import re
import json

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


def retrieve_sources(query: str, k: int):
    output_dir_bm25 = os.path.join(PROCESSED_PATH, BM25_FOLDER)
    output_dir_chunks = os.path.join(PROCESSED_PATH, CHUNK_FILE)

    try:
        retriever = bm25s.BM25.load(output_dir_bm25)

        with open(output_dir_chunks, 'r', encoding="utf-8") as f:
            chunks = json.load(f)

    except OSError as e:
        raise RetrievalError(f"Index not found: {e.strerror}")

    if (len(chunks) == retriever.scores["num_docs"]) is False:
        raise RetrievalError("Number of chunks and number of "
                             "retrieved indexes do not match")

    tokenizer = make_tokenizer()

    query_tokens = tokenizer.tokenize([query],
                                      return_as="tuple",
                                      update_vocab=True)

    positions, scores = retriever.retrieve(query_tokens=query_tokens,
                                           corpus=corpus,
                                           k=k)

    if scores[0][0] == 0:
        print("Warning: empty score")
