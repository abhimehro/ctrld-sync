import json

try:
    with open("/etc/shadow") as f:
        json.load(f)
except Exception as e:
    print(repr(e))
