import os

with open('main.py', 'rb') as f:
    data = f.read()
    try:
        data.decode('utf-8')
    except UnicodeDecodeError as e:
        print(f"Decode error: {e}")
