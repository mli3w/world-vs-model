"""Test isolation: run each test in a fresh temp working directory.

The board reads its ledger from the RELATIVE path `ledger/wc_core.jsonl` (etc.). Once a real ledger
is committed to the repo, tests run from the repo root would pick it up and exercise the tracked-book
path instead of the deterministic no-ledger path they assert. Chdir-ing to an empty temp dir keeps
the unit tests independent of whatever ledger happens to be committed. (Docs/assets are read via
absolute paths, so they still resolve.)
"""
import pytest


@pytest.fixture(autouse=True)
def _isolate_cwd(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
