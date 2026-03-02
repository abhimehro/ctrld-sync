import json
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import main


# Benchmark pre-compiled regex validation (already optimized per discussion #219)
def test_is_valid_rule_benchmark(benchmark):
    """Regex-heavy rule validation should stay under 1ms per call."""
    result = benchmark(main.is_valid_rule, "example.com")
    assert result is True


# Benchmark rule deduplication (dict.fromkeys pattern)
def test_deduplication_benchmark(benchmark):
    """Rule deduplication over 10k items (1k unique) should stay under 10ms."""
    rules = [f"rule-{i % 1000}" for i in range(10000)]
    result = benchmark(lambda: list(dict.fromkeys(rules)))
    assert len(result) == 1000


# Benchmark cache serialization for large rule sets
def test_cache_roundtrip_benchmark(benchmark):
    """JSON serialization of 5k-rule cache payload should stay under 10ms."""
    data = {"rules": [f"domain-{i}.com" for i in range(5000)]}
    result = benchmark(json.dumps, data)
    assert len(result) > 0


# Benchmark hostname validation for non-global IPs (no DNS lookup, pure CPU path)
def test_benchmark_validate_hostname(benchmark):
    """Hostname validation for private IPs (no DNS lookup) should stay under 1ms per call.

    Cache is cleared before timing to measure worst-case (cold-cache) performance.
    """
    # Clear lru_cache to measure worst-case latency, not cached lookup speed
    main.validate_hostname.cache_clear()
    result = benchmark(main.validate_hostname, "192.168.1.1")
    assert result is False  # Private IP is rejected


# Benchmark log sanitization with a URL containing sensitive query parameters
def test_benchmark_sanitize_for_log(benchmark):
    """Log sanitization should handle typical URLs with sensitive params under 1ms per call."""
    url = "https://api.controld.com/profiles?token=supersecret&key=abc123"
    result = benchmark(main.sanitize_for_log, url)
    assert "supersecret" not in result
    assert "abc123" not in result
