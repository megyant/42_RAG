from .colors import Colors


class CliError(Exception):
    """
    Base exception class for command-line interface errors with
    ANSI color formatting.
    """
    def __init__(self, msg: str) -> None:
        """Initialize the CliError with a formatted error message.

        Args:
            msg (str): The descriptive error message.
        """
        super().__init__(f'{Colors.BOLD}{Colors.RED}'
                         f'Error:{Colors.END} {msg}')


class ParseError(CliError):
    """Exception raised when parsing fails."""
    ...


class IndexingError(CliError):
    """Exception raised when indexing fails."""
    ...


class RetrievalError(CliError):
    """Exception raised when retrieval fails."""
    ...
