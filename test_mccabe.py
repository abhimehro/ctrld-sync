import sys
import getpass

def print_hint(hint: str, use_colors: bool) -> None:
    if use_colors:
        print(f"\\033[2m{hint}\\033[0m")
    else:
        print(hint)

def get_validated_input(
    prompt: str,
    validator,
    error_msg: str,
) -> str:
    """Prompts for input until the validator returns True."""
    if not prompt.endswith(" "):
        prompt += " "

    while True:
        try:
            sys.stdout.flush()
            sys.stderr.flush()
            value = input(prompt).strip()
        except (KeyboardInterrupt, EOFError):
            sys.exit(130)

        if not value:
            print_hint("EMPTY_INPUT_HINT", True)
            continue

        if validator(value):
            return value

        print_hint("INVALID_INPUT_HINT", True)
