import fire
from .helpers import Colors
from .cli import Cli

def main() -> None:
    try:
        fire.Fire(Cli)

    except KeyboardInterrupt:
        print(f"\n{Colors.RED}Exiting the program...{Colors.END}")

if __name__ == "__main__":
    main()