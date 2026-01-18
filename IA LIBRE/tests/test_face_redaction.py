import pytest
from pathlib import Path
from scripts.face_redact import redact_faces

def test_redact_no_crash(tmp_path):
    # Skip if no sample image provided
    sample = Path("tests/fixtures/sample_face.jpg")
    if not sample.exists():
        pytest.skip("No sample image for face redaction test")
    img_bytes = sample.read_bytes()
    out = redact_faces(img_bytes, method="pixelate", conf_thresh=0.3)
    assert out is not None
    assert isinstance(out, (bytes, bytearray))