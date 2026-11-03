from pydantic import BaseModel, ValidationError
from .models import DataSource
from .helpers import CliError, PROCESSED_PATH, Colors
from pathlib import Path


class ChunkIndex(BaseModel):
    chunks: list[DataSource]


def save_index(chunks: list[DataSource],
               output_path: str = PROCESSED_PATH) -> None:

    output_dir = Path(output_path)

    try:
        data = ChunkIndex(chunks=chunks)
    except ValidationError as e:
        raise CliError(f"Could not write index: {e.errors()[0]['type']}")

    try:
        output_dir.mkdir(parents=True, exist_ok=True)

        file_name = "chunks.json"

        with open(output_dir / file_name, "w",
                  encoding="utf-8") as f:
            f.write(data.model_dump_json(indent=4))
    except OSError as e:
        raise CliError(f"Could not write index: {e.strerror}")

    print(f"\n{Colors.BOLD}{Colors.GREEN}Success:{Colors.END} Ingestion "
          "complete. Saved under "
          f"'{output_dir}'.\n")
