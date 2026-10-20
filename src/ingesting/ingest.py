from pathlib import Path
from src.helpers import RAW_PATH


def collect_files(raw_path: str = RAW_PATH) -> list[Path]:
    root = Path(raw_path)
    suffixes = [".py", ".md", ".txt"]

    files: list[Path] = []

    for p in root.rglob("*"):
        if p.is_file() and p.suffix in suffixes:
            files.append(p)

    return sorted(files)


def read_file(path: Path) -> str | None:
    try:
        with open(path, encoding="utf-8", newline="") as f:
            text = f.read()
        return text
    except OSError as e:
        print(f'Could not read "{path}": {e.strerror}.')
        return None

    except UnicodeDecodeError as e:
        print(f'Could not decode "{path}": '
              f'{e.reason.capitalize()}.')
        return None


"""
index
1. Grabs the path of each file
2. diverts each file to the correct chunker
3. reads the file
4. creates the chunks
"""
