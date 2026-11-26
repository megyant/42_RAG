import fire
import sys
from .helpers import Colors, CliError


def main() -> None:
    """
    Execute the command-line interface using Fire, handling custom and
    unexpected exceptions gracefully.

    Raises:
        SystemExit: Exits with code 1 on CLI errors, keyboard interruptions,
        or unexpected exceptions.
    """
    try:
        from .pipeline.cli import Cli
        fire.Fire(Cli)

    except CliError as e:
        print(e, file=sys.stderr)
        sys.exit(0)
    except KeyboardInterrupt:
        print(f"\n{Colors.BOLD}{Colors.RED}Exiting the program...{Colors.END}")
        sys.exit(0)
    except Exception as e:
        print(f"\n{Colors.BOLD}{Colors.RED}Something went wrong...{Colors.END}"
              f"{e}")
        sys.exit(0)


if __name__ == "__main__":
    main()
