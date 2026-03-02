import json
import main

# Benchmark pre-compiled regex validation (already optimized per discussion #219)
def test_is_valid_rule_benchmark(benchmark):
    result = benchmark(main.is_valid_rule, "example.com")
    assert result is True

# Benchmark rule deduplication (dict.fromkeys pattern)
def test_deduplication_benchmark(benchmark):
    rules = [f"rule-{i % 1000}" for i in range(10000)]
    result = benchmark(lambda: list(dict.fromkeys(rules)))
    assert len(result) == 1000

# Benchmark cache serialization for large rule sets
def test_cache_roundtrip_benchmark(benchmark):
def test_cache_roundtrip_benchmark(benchmark):
    data = {"rules": [f"domain-{i}.com" for i in range(5000)]}
    def roundtrip(d):
        return json.loads(json.dumps(d))
    result = benchmark(roundtrip, data)
    assert result == data
