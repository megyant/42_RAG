from pathlib import Path
from src.helpers import RAW_PATH


def collect_files(RAW_PATH) -> list[Path]:
    root = Path(RAW_PATH)
    suffixes = [".py", ".md", ".txt"]

    files: list[Path] = []

    for p in root.rglob("*"):
        if p.is_file() and p.suffix in suffixes:
            files.append(p)

    return sorted(files)


def read_file(Path: Path) -> str | None:
    try:
        with open(RAW_PATH, encoding="utf-8", newline="") as f:
            text = f.read()
        return text
    except OSError as e:
        print(f'Could not read "{RAW_PATH}": {e.strerror}.')
        return None

    except UnicodeDecodeError as e:
        print(f'Could not decode "{RAW_PATH}": '
              f'{e.reason.capitalize()}.')
        return None
