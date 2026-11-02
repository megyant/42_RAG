from pydantic import BaseModel, ValidationError
from .models import MinimalSource
from .helpers import CliError, PROCESSED_PATH
from pathlib import Path


class ChunkIndex(BaseModel):
    chunks: list[MinimalSource]


def load_json(chunks: list[MinimalSource],
              output_path: str = PROCESSED_PATH):

    output_dir = Path(output_path)

    try:
        data = ChunkIndex(chunks=chunks)
    except ValidationError as e:
        raise CliError(f"Could not write index: {e.errors()[0]['type']}")

    try:
        output_dir.mkdir(parents=True, exist_ok=True)

        with open(output_dir / "chunks.json", "w",
                  encoding="utf-8") as f:
            f.write(data.model_dump_json(indent=4))
    except OSError as e:
        raise CliError(f"Could not write index: {e.strerror}")

    print(f"Ingestion complete. Indices saved under {output_dir}.")
