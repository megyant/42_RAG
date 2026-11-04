import bm25s
from .models import DataSource
from .helpers import PROCESSED_PATH, Colors, CliError
import os
import re

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
    output_dir = os.path.join(PROCESSED_PATH, "bm25")

    try:
        retriever.save(output_dir)
    except OSError as e:
        raise CliError(f"Could not write index: {e.strerror}")

    print(f"{Colors.BOLD}{Colors.GREEN}Success:{Colors.END} Indexing "
          "complete. Saved under "
          f"'{output_dir}'.")
