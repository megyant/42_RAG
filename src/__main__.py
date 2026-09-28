import fire
from .helpers import Colors

def main() -> None:
    try:
        fire.Fire()

    except KeyboardInterrupt:
        print(f"\n{Colors.RED}Exiting the program...{Colors.END}")

if __name__ == "__main__":
    main()