from pathlib import Path
from src.helpers import RAW_PATH, ParseError
import re
import json
from typing import Any


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
            return f.read()
    except OSError as e:
        print(f'Could not read "{path}": {e.strerror}.')
        return None

    except UnicodeDecodeError as e:
        print(f'Could not decode "{path}": '
              f'{e.reason.capitalize()}.')
        return None


def split_endings(text: str) -> list[str]:
    return re.findall("[^\r\n]*(?:\r\n|\r|\n)|[^\r\n]+$", text)


def load_questions(path: str) -> Any:
    try:
        with open(path, encoding="utf-8") as f:
            questions = json.load(f)
        return questions

    except OSError:
        raise ParseError(f"File '{path}' could not be loaded.")

    except json.JSONDecodeError:
        raise ParseError(f"File '{path}' could not be processed.")


"""
index
1. Grabs the path of each file
2. diverts each file to the correct chunker
3. reads the file
4. creates the chunks
"""
