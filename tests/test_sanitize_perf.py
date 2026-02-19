
import time
import sys
import os

# Ensure we can import main from parent directory
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import main

def test_sanitize_perf():
    print("Running performance benchmark for sanitize_for_log...")

    # 1. Simple text (common case: folder names, status messages)
    text_simple = "Just a normal log message with some folder name"
    start = time.perf_counter()
    for _ in range(50000):
        main.sanitize_for_log(text_simple)
    end = time.perf_counter()
    simple_time = end - start
    print(f"50k sanitize_for_log (simple): {simple_time:.4f}s")

    # 2. Complex text (URLs with potential secrets)
    text_complex = "https://user:pass@example.com/path?token=secret&other=value"
    start = time.perf_counter()
    for _ in range(50000):
        main.sanitize_for_log(text_complex)
    end = time.perf_counter()
    complex_time = end - start
    print(f"50k sanitize_for_log (complex): {complex_time:.4f}s")

if __name__ == "__main__":
    test_sanitize_perf()
