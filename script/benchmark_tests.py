import os
import time
from pathlib import Path
import pytest

class DurationCollector:
    def __init__(self):
        self.durations = []

    @pytest.hookimpl(hookwrapper=True)
    def pytest_runtest_call(self, item):
        t0 = time.perf_counter()
        yield
        dt = time.perf_counter() - t0
        self.durations.append((dt, item.nodeid))

if __name__ == "__main__":
    collector = DurationCollector()
    pytest.main(["-q"], plugins=[collector])
    collector.durations.sort(key=lambda x: x[0], reverse=True)
    
    out_path = Path("script/benchmark_results.txt")
    with open(out_path, "w", encoding="utf-8") as f:
        f.write("=" * 80 + "\n")
        f.write("TOP DES TESTS LES PLUS LENTS DANS ANKIFORGE\n")
        f.write("=" * 80 + "\n")
        for dt, nodeid in collector.durations:
            f.write(f"{dt:6.3f}s  {nodeid}\n")
        f.write("=" * 80 + "\n")
    print(f"Results written to {out_path}")
