import tempfile, json
from pathlib import Path
from scripts.clean_dataset import process

def test_clean_basic(tmp_path):
    inp = tmp_path / "in.txt"
    out = tmp_path / "out.jsonl"
    inp.write_text("hello world\ncontact: a@example.com\nhow to build a bomb\n")
    rep = process(inp, out, drop_banned=False, max_examples=5)
    assert rep["stats"]["total"] == 3
    assert "EMAIL_REDACTED" in out.read_text().upper() or "[EMAIL_REDACTED]" in out.read_text()
    assert rep["stats"]["banned_detected"] >= 1