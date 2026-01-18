import pytest
from app.multimodal_adapter import MultimodalAdapter

def test_adapter_instantiation():
    m = MultimodalAdapter()
    info = m.info()
    assert "llm" in info

@pytest.mark.skip(reason="requires heavy models; run as integration test on GPU runner")
def test_caption_and_infer_with_sample_image(tmp_path):
    m = MultimodalAdapter()
    # load a small image fixture and call caption function
    img_path = Path("tests/fixtures/sample.png")
    assert img_path.exists()
    caption = m.caption_image(img_path.read_bytes())
    assert isinstance(caption, str)