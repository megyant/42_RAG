import fire
import sys
from .helpers import Colors, CliError
from .cli import Cli


def main() -> None:
    try:
        fire.Fire(Cli)

    except CliError as e:
        print(e, file=sys.stderr)
        sys.exit(1)
    except KeyboardInterrupt:
        print(f"\n{Colors.RED}Exiting the program...{Colors.END}")
        sys.exit(1)
    except Exception as e:
        print(f"\n{Colors.RED}Something went wrong...{e}{Colors.END}")
        sys.exit(1)


if __name__ == "__main__":
    main()
