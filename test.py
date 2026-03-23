import yaml

data1 = """
documentation:
  - any:
    - '**/*.md'
"""

data2 = """
documentation:
  - any:
      - '**/*.md'
"""

print("1:", yaml.safe_load(data1))
print("2:", yaml.safe_load(data2))
