import re

with open('main.py', 'r') as f:
    content = f.read()

gh_get_code = content[content.find('def _gh_get(url: str) -> dict:'):content.find('def check_api_access(client: httpx.Client, profile_id: str) -> bool:')]
print(gh_get_code)
