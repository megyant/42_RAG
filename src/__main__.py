import fire
from .helpers import Colors, CliError
from .cli import Cli
from .ingesting import Ingest


def main() -> None:
    try:
        try:
            fire.Fire(Cli)

        except CliError:
            print("TEMP")

    except KeyboardInterrupt:
        print(f"\n{Colors.RED}Exiting the program...{Colors.END}")


if __name__ == "__main__":
    main()
