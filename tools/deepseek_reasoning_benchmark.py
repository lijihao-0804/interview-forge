try:
    from ._compat import expose
except ImportError:
    import sys
    from pathlib import Path
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from _compat import expose

expose(__name__, "scripts.benchmarks.deepseek_reasoning_benchmark")
