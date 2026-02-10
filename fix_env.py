import os
import re
import stat

def fix_env():
    try:
        with open('.env', 'r') as f:
            content = f.read()
    except FileNotFoundError:
        print("No .env file found.")
        return

    # Helper to clean quotes (curly or straight)
    def clean_val(val):
        if not val: return ""
        # Remove surrounding quotes of any kind
        val = val.strip()
        val = re.sub(r'^[\"\u201c\u201d\']|[\"\u201c\u201d\']$', '', val)
        return val

    # Helper to escape value for shell
    def escape_val(val):
        if not val: return ""
        # Escape backslashes first, then double quotes
        return val.replace('\\', '\\\\').replace('"', '\\"')

    lines = content.splitlines()
    parsed = {}
    
    for line in lines:
        if '=' in line:
            key, val = line.split('=', 1)
            parsed[key.strip()] = clean_val(val.strip())

    # Detect swapped values
    token_val = parsed.get('TOKEN', '')
    profile_val = parsed.get('PROFILE', '')

    real_token = ""
    real_profiles = ""

    # Heuristic: Token usually starts with 'api.' or is long/alphanumeric
    # Profiles are usually comma-separated lists of ~12 chars
    
    if 'api.' in profile_val or len(profile_val) > 40:
        real_token = profile_val
    elif 'api.' in token_val or len(token_val) > 40:
        real_token = token_val

    if ',' in token_val or (len(token_val) < 20 and len(token_val) > 0 and 'api.' not in token_val):
        real_profiles = token_val
    elif ',' in profile_val or (len(profile_val) < 20 and len(profile_val) > 0 and 'api.' not in profile_val):
        real_profiles = profile_val
        
    # If we couldn't resolve clearly, fall back to what was there but cleaned
    if not real_token: real_token = token_val
    if not real_profiles: real_profiles = profile_val

    # Write back with standard quotes
    new_content = f'TOKEN="{escape_val(real_token)}"\nPROFILE="{escape_val(real_profiles)}"\n'
    
    # Security: Check for symlinks to prevent overwriting arbitrary files
    if os.path.islink('.env'):
        print("Security Warning: .env is a symlink. Aborting to avoid overwriting target.")
        return

    # Security: Write using os.open to ensure 600 permissions at creation time
    # This prevents a race condition where the file is world-readable before chmod
    try:
        # O_TRUNC to overwrite if exists, O_CREAT to create if not
        flags = os.O_WRONLY | os.O_CREAT | os.O_TRUNC
        mode = stat.S_IRUSR | stat.S_IWUSR  # 0o600

        fd = os.open('.env', flags, mode)
        with os.fdopen(fd, 'w') as f:
            f.write(new_content)
            # Enforce permissions on the file descriptor directly (safe against race conditions)
            if os.name != 'nt':
                os.chmod(fd, mode)

    except OSError as e:
        print(f"Error writing .env: {e}")
        return

    print("Fixed .env file: standardized quotes and corrected variable assignments.")
    print("Security: .env permissions set to 600 (read/write only by owner).")

if __name__ == "__main__":
    fix_env()
