from pathlib import Path


class Ingest:
    def __init__(self, dataset_path: str) -> None:
        self.dataset_path = dataset_path

    def collect_files(self) -> list[Path]:
        root = Path(self.dataset_path)
        suffixes = [".py", ".md", ".txt"]

        files: list[Path] = []

        """ python = 0
        markdown = 0
        text = 0 """

        for p in root.rglob("*"):
            if p.is_file() and p.suffix in suffixes:
                files.append(p)
            """ if p.suffix == ".py":
                python += 1
            if p.suffix == ".md":
                markdown += 1
            if p.suffix == ".txt":
                text += 1 """

        """ print("python:", python)
        print("markdown:", markdown)
        print("text:", text) """

        return sorted(files)

    def read_file(self, path: Path) -> str | None:
        try:
            with open(path, encoding="utf-8", newline="") as f:
                text = f.read()
            return text
        except OSError as e:
            # OSError works as an umbrella for any file related error
            print(f'Could not read "{path}": {e.strerror}.')
            return None

        except UnicodeDecodeError as e:
            print(f'Could not decode "{path}": '
                  f'{e.reason.capitalize()}.')
            return None
