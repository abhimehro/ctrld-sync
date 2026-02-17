#!/usr/bin/env python3
"""
Synthetic benchmark to demonstrate retry jitter behavior.

Run this script to see how jitter randomizes retry delays compared to
deterministic exponential backoff.

Usage: python3 benchmark_retry_jitter.py
"""

import time
import random
from typing import List

def simulate_retries_without_jitter(max_retries: int, base_delay: float) -> List[float]:
    """Simulate retry delays WITHOUT jitter (old behavior)."""
    delays = []
    for attempt in range(max_retries - 1):
        wait_time = base_delay * (2 ** attempt)
        delays.append(wait_time)
    return delays

def simulate_retries_with_jitter(max_retries: int, base_delay: float) -> List[float]:
    """Simulate retry delays WITH jitter (new behavior)."""
    delays = []
    for attempt in range(max_retries - 1):
        base_wait = base_delay * (2 ** attempt)
        jitter_factor = 0.5 + random.random()  # [0.5, 1.5]
        wait_time = base_wait * jitter_factor
        delays.append(wait_time)
    return delays

def main():
    print("=" * 60)
    print("Retry Jitter Performance Demonstration")
    print("=" * 60)
    print()
    
    max_retries = 5
    base_delay = 1.0
    
    print(f"Configuration: max_retries={max_retries}, base_delay={base_delay}s")
    print()
    
    # Without jitter (deterministic)
    print("WITHOUT JITTER (old behavior):")
    print("All clients retry at exactly the same time (thundering herd)")
    print()
    without_jitter = simulate_retries_without_jitter(max_retries, base_delay)
    for i, delay in enumerate(without_jitter):
        print(f"  Attempt {i+1}: {delay:6.2f}s")
    print(f"  Total: {sum(without_jitter):6.2f}s")
    print()
    
    # With jitter (randomized)
    print("WITH JITTER (new behavior):")
    print("Retries spread across time window, reducing server load spikes")
    print()
    
    # Run 3 simulations to show variance
    for run in range(3):
        print(f"  Run {run+1}:")
        with_jitter = simulate_retries_with_jitter(max_retries, base_delay)
        for i, delay in enumerate(with_jitter):
            base = base_delay * (2 ** i)
            print(f"    Attempt {i+1}: {delay:6.2f}s (base: {base:4.1f}s, range: [{base*0.5:.1f}s, {base*1.5:.1f}s])")
        print(f"    Total: {sum(with_jitter):6.2f}s")
        print()
    
    # Statistical analysis
    print("IMPACT ANALYSIS:")
    print()
    
    # Simulate thundering herd scenario
    num_clients = 100
    print(f"Scenario: {num_clients} clients all fail at the same time")
    print()
    
    print("WITHOUT JITTER:")
    print(f"  At t=1s: ALL {num_clients} clients retry simultaneously → server overload")
    print(f"  At t=2s: ALL {num_clients} clients retry simultaneously → server overload")
    print(f"  At t=4s: ALL {num_clients} clients retry simultaneously → server overload")
    print()
    
    print("WITH JITTER:")
    # Simulate retry distribution
    retry_times = []
    for _ in range(num_clients):
        first_retry = (base_delay * (0.5 + random.random()))
        retry_times.append(first_retry)
    
    retry_times.sort()
    min_time = min(retry_times)
    max_time = max(retry_times)
    avg_time = sum(retry_times) / len(retry_times)
    
    print(f"  First retry window: {min_time:.2f}s to {max_time:.2f}s (spread: {max_time - min_time:.2f}s)")
    print(f"  Average first retry: {avg_time:.2f}s")
    print(f"  Retries distributed over time → reduced peak load on server")
    print()
    
    # Calculate theoretical load reduction
    print("THEORETICAL LOAD REDUCTION:")
    window_size = max_time - min_time
    if window_size > 0:
        reduction = (1 - (1 / window_size)) * 100
        print(f"  Peak concurrent retries reduced by approximately {reduction:.0f}%")
    print()
    
    print("✅ Jitter prevents thundering herd and improves system reliability")

if __name__ == "__main__":
    main()
