import re

def _print_hint(hint: str) -> None:
    """Helper to cleanly print input hints while respecting USE_COLORS to reduce cyclomatic complexity."""
    if USE_COLORS:
        print(f"{Colors.DIM}{hint}{Colors.ENDC}")
    else:
        print(hint)
