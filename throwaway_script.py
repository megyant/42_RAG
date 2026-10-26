from collections import Counter
from src.ingesting import read_file, collect_files
import ast
import sys


def throwaway_script() -> None:
    all_paths = [p for p in collect_files() if p.suffix.lower() == ".py"]

    success = 0
    unreadable = 0
    errors: Counter[str] = Counter()
    failed: list[str] = []

    for path in all_paths:
        text = read_file(path)
        if text is None:
            unreadable += 1
            continue

        try:
            ast.parse(text)
            success += 1
        except (SyntaxError, ValueError, RecursionError) as e:
            msg = getattr(e, "msg", str(e))
            line = getattr(e, "lineno", "?")
            errors[f"{type(e).__name__}: {msg}"] += 1
            failed.append(f"{path}:{line}  {type(e).__name__}: {msg}")

    print(f"Python {sys.version.split()[0]}")
    print(f"Total = {len(all_paths)}\n"
          f"Success = {success}\n"
          f"Unreadable = {unreadable}\n"
          f"Failed = {len(failed)}")
    for msg, count in errors.most_common():
        print(f"  {count:4d} x {msg}")
    for f in failed:
        print(f"  {f}")


if __name__ == "__main__":
    throwaway_script()
