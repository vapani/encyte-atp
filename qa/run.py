#!/usr/bin/env python3
"""Run every QA check. Use it after changing a template, a preset or the code.

    python3 qa/run.py

Takes about a minute. Exits 0 only when every check passes.
"""
import os, subprocess, sys, time

HERE = os.path.dirname(os.path.abspath(__file__))
CHECKS = [("Contracts", "check_contracts.py"), ("Guards", "check_guards.py"), ("Form", "check_form.py")]


def main():
    failed = []
    for title, script in CHECKS:
        print(f"\n{title}", flush=True)
        start = time.time()
        r = subprocess.run([sys.executable, os.path.join(HERE, script)])
        print(f"  ({time.time() - start:.0f}s)", flush=True)
        if r.returncode:
            failed.append(title)
    print("\nQA " + ("PASSED" if not failed else "FAILED: " + ", ".join(failed)))
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
