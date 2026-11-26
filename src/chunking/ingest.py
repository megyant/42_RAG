from pathlib import Path
from src.helpers import Paths, ParseError
import re
import json
from typing import Any


def collect_files(raw_path: str = Paths.RAW_PATH) -> list[Path]:
    """
    Collect all files with specified suffixes (.py, .md, .txt) recursively
    from a root path.

    Args:
        raw_path (str): The root directory path to search within.
        Defaults to Paths.RAW_PATH.

    Returns:
        list[Path]: A sorted list of file paths matching the criteria.
    """
    root = Path(raw_path)
    if not root.is_dir():
        raise ParseError("vLLM repository not found.")
    suffixes = [".py", ".md", ".txt"]

    files: list[Path] = []
    for p in root.rglob("*"):
        if p.is_file() and p.suffix in suffixes:
            files.append(p)

    if not files:
        raise ParseError("No .py/.md/.txt files found in vLLM repository")

    return sorted(files)


def read_file(path: Path) -> str | None:
    """Read and return the text content of a file with UTF-8 encoding.

    Args:
        path (Path): The path to the file to be read.

    Returns:
        str | None: The content of the file as a string, or None if an
        error or decoding failure occurs.
    """
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
    """
    Split a text string into lines while preserving their respective
    line endings.

    Args:
        text (str): The input text string to split.

    Returns:
        list[str]: A list of lines, each including its trailing line ending.
    """
    return re.findall("[^\r\n]*(?:\r\n|\r|\n)|[^\r\n]+$", text)


def load_questions(path: str) -> Any:
    """
    Load and parse JSON data from a file.

    Args:
        path (str): The path to the JSON file to load.

    Returns:
        Any: The parsed JSON data.

    Raises:
        ParseError: If the file cannot be read or contains invalid JSON.
    """
    try:
        with open(path, encoding="utf-8") as f:
            questions = json.load(f)
        return questions

    except OSError:
        raise ParseError(f"File '{path}' could not be loaded.")

    except json.JSONDecodeError:
        raise ParseError(f"File '{path}' could not be processed.")
