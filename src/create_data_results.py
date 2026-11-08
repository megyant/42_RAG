from pydantic import BaseModel, ValidationError
from .models import DataSource
from .helpers import (PROCESSED_PATH, Colors, CHUNK_FILE,
                      IndexingError)
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

        path = os.path.join(PROCESSED_PATH, CHUNK_FILE)

        with open(path, "w",
                  encoding="utf-8") as f:
            f.write(data.model_dump_json(indent=4))
    except OSError as e:
        raise IndexingError(f"Could not write index: {e.strerror}")

    print(f"{Colors.BOLD}{Colors.GREEN}Success:{Colors.END} Ingestion "
          "complete. Saved under "
          f"'{output_dir}'.")
