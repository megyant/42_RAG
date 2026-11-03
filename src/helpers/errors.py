from .colors import Colors


class CliError(Exception):
    def __init__(self, msg: str) -> None:
        super().__init__(f'{Colors.BOLD}{Colors.RED}Command Line Interface '
                         f'Error:{Colors.END} {msg}')


class ParseError(CliError):
    ...
