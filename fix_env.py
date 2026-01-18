import os
import re

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
    
    with open('.env', 'w') as f:
        f.write(new_content)
    
    print("Fixed .env file: standardized quotes and corrected variable assignments.")

if __name__ == "__main__":
    fix_env()
