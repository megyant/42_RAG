class Colors:
    """
    ANSI escape codes used to colorize terminal output.

    Attributes:
        GREEN: Escape code that switches subsequent text to green.
        YELLOW: Escape code that switches subsequent text to yellow.
        RED: Escape code that switches subsequent text to red.
        BLUE: Escape code that switches subsequent text to blue.
        END: Escape code that resets text formatting to default.
    """
    GREEN = '\033[92m'
    YELLOW = '\033[93m'
    RED = '\033[91m'
    BLUE = "\033[94m"
    END = '\033[0m'