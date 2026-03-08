import os
import re
import stat
import contextlib

__all__ = ["fix_env", "clean_val", "escape_val"]

# Helper to clean quotes (curly or straight)
def clean_val(val):
    if not val:
        return ""
    # Remove surrounding quotes of any kind
    val = val.strip()
    return re.sub(r"^[\"\u201c\u201d\']|[\"\u201c\u201d\']$", "", val)

# Helper to escape value for shell
def escape_val(val):
    if not val:
        return ""
    # Escape backslashes first, then double quotes
    return val.replace("\\", "\\\\").replace('"', '\\"')

def fix_env():
    """Read `.env`, correct swapped TOKEN/PROFILE assignments, and rewrite securely.

    Uses heuristics to detect if TOKEN and PROFILE values have been swapped
    (e.g., the API key ends up in PROFILE and the profile ID in TOKEN).
    Writes the corrected values back using an atomic O_EXCL temp-file replace
    with 0o600 permissions to prevent symlink attacks and privilege escalation.

    Prints a notice and returns early if `.env` is not found.
    """
    try:
        with open(".env") as f:
            content = f.read()
    except FileNotFoundError:
        print("No .env file found.")
        return

    lines = content.splitlines()
    parsed = {}

    for line in lines:
        if "=" in line:
            key, val = line.split("=", 1)
            parsed[key.strip()] = clean_val(val.strip())

    # Detect swapped values
    token_val = parsed.get("TOKEN", "")
    profile_val = parsed.get("PROFILE", "")

    real_token = ""
    real_profiles = ""

    # Heuristic: Token usually starts with 'api.' or is long/alphanumeric
    # Profiles are usually comma-separated lists of ~12 chars

    if "api." in profile_val or len(profile_val) > 40:
        real_token = profile_val
    elif "api." in token_val or len(token_val) > 40:
        real_token = token_val

    if "," in token_val or (
        len(token_val) < 20 and len(token_val) > 0 and "api." not in token_val
    ):
        real_profiles = token_val
    elif "," in profile_val or (
        len(profile_val) < 20 and len(profile_val) > 0 and "api." not in profile_val
    ):
        real_profiles = profile_val

    # If we couldn't resolve clearly, fall back to what was there but cleaned
    if not real_token:
        real_token = token_val
    if not real_profiles:
        real_profiles = profile_val

    # Write back with standard quotes
    new_content = (
        f'TOKEN="{escape_val(real_token)}"\nPROFILE="{escape_val(real_profiles)}"\n'
    )

    # Security: Write using os.open to a temp file, then os.replace to prevent TOCTOU
    # symlink attacks and ensure 0o600 permissions at creation time.
    # Use O_EXCL to prevent writing to an existing symlink or file.
    try:
        flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
        mode = stat.S_IRUSR | stat.S_IWUSR  # 0o600

        # O_NOFOLLOW is not available on all platforms (like Windows)
        if hasattr(os, "O_NOFOLLOW"):
            flags |= os.O_NOFOLLOW

        temp_file = ".env.tmp"
        try:
            fd = os.open(temp_file, flags, mode)
        except FileExistsError:
            # If the temp file exists from a previous aborted run, unlink and retry.
            with contextlib.suppress(OSError):
                os.unlink(temp_file)
            fd = os.open(temp_file, flags, mode)

        with os.fdopen(fd, "w") as f:
            f.write(new_content)
            # Enforce permissions on the file descriptor directly (safe against race conditions)
            if os.name != "nt":
                os.chmod(fd, mode)

        # Atomic replace
        os.replace(temp_file, ".env")

    except OSError as e:
        print(f"Error writing .env: {e}")
        # Clean up temp file on error
        if os.path.exists(".env.tmp"):
            with contextlib.suppress(OSError):
                os.unlink(".env.tmp")
        return

    print("Fixed .env file: standardized quotes and corrected variable assignments.")
    print("Security: .env permissions set to 600 (read/write only by owner).")

if __name__ == "__main__":
    fix_env()
