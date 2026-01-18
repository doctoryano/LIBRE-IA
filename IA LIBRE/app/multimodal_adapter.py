#!/usr/bin/env python3
"""
app/multimodal_adapter.py (actualizado)

Ahora integra redacción de rostros obligatoria antes de captioning.
- Lee variables de entorno para controlar método y umbral:
    FACE_REDACT_ENABLE (yes/no)
    FACE_REDACT_METHOD (blur|pixelate|blackbox)
    FACE_REDACT_CONF (float 0..1)

Mantiene lazy loading de BLIP2 y Whisper como antes.
"""
from __future__ import annotations
import os
import re
import io
import asyncio
from typing import Optional, List, AsyncGenerator
from pathlib import Path

from app.model_adapter import get_adapter

# face redact util
from scripts.face_redact import redact_faces

# Optional heavy imports
try:
    from PIL import Image
    HAS_PIL = True
except Exception:
    HAS_PIL = False

try:
    from transformers import Blip2Processor, Blip2ForConditionalGeneration
    HAS_BLIP2 = True
except Exception:
    HAS_BLIP2 = False

try:
    import whisper
    HAS_WHISPER = True
except Exception:
    HAS_WHISPER = False

# Moderation regex reused
RE_EMAIL = re.compile(r"[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+")
RE_IPv4 = re.compile(r"\b(?:\d{1,3}\.){3}\d{1,3}\b")
WEAPON_KEYWORDS = ["weapon","bomb","explosive","detonate","rifle","gun"]
WEAPON_RE = re.compile(r"\b(" + "|".join([re.escape(w) for w in WEAPON_KEYWORDS]) + r")\b", re.IGNORECASE)

def moderate_text(s: str) -> list:
    reasons = []
    if WEAPON_RE.search(s):
        reasons.append("contains_banned_keyword")
    if RE_EMAIL.search(s):
        reasons.append("contains_email")
    if RE_IPv4.search(s):
        reasons.append("contains_ip")
    return reasons

# Face redaction settings from env
FACE_REDACT_ENABLE = os.getenv("FACE_REDACT_ENABLE", "yes").lower() in ("1","yes","true")
FACE_REDACT_METHOD = os.getenv("FACE_REDACT_METHOD", "blur")
try:
    FACE_REDACT_CONF = float(os.getenv("FACE_REDACT_CONF", "0.5"))
except Exception:
    FACE_REDACT_CONF = 0.5

class MultimodalAdapter:
    def __init__(self, blip2_model: Optional[str] = None, whisper_model: Optional[str] = "small"):
        self.llm = get_adapter()
        self.blip2_model = blip2_model or "Salesforce/blip2-flan-t5-xl"
        self.whisper_model = whisper_model
        self._blip_loaded = False
        self._whisper_loaded = False
        self.blip_processor = None
        self.blip_model = None

    def name(self):
        return f"multimodal->({self.llm.name()})"

    def info(self):
        return {"type": "multimodal", "llm": self.llm.name(), "face_redact": FACE_REDACT_ENABLE, "face_method": FACE_REDACT_METHOD}

    def _ensure_blip(self):
        if not HAS_BLIP2:
            raise RuntimeError("BLIP2 not available")
        if not self._blip_loaded:
            self.blip_processor = Blip2Processor.from_pretrained(self.blip2_model)
            self.blip_model = Blip2ForConditionalGeneration.from_pretrained(self.blip2_model)
            self._blip_loaded = True

    def caption_image(self, image_bytes: bytes) -> str:
        # redact faces if enabled
        processed_bytes = image_bytes
        if FACE_REDACT_ENABLE:
            try:
                processed_bytes = redact_faces(image_bytes, method=FACE_REDACT_METHOD, conf_thresh=FACE_REDACT_CONF)
            except Exception as e:
                # On failure of redaction, fail closed: raise to prevent leaking raw image
                raise RuntimeError(f"Face redaction failed: {e}")

        if HAS_BLIP2:
            try:
                self._ensure_blip()
                from PIL import Image
                image = Image.open(io.BytesIO(processed_bytes)).convert("RGB")
                inputs = self.blip_processor(images=image, return_tensors="pt")
                outputs = self.blip_model.generate(**inputs, max_new_tokens=64)
                caption = self.blip_processor.decode(outputs[0], skip_special_tokens=True)
                return caption
            except Exception as e:
                # degrade to a minimal description
                return "<image (caption failed)>"
        else:
            # fallback minimal safe caption (no faces included)
            return "<image (redacted)>"

    def transcribe_audio(self, audio_bytes: bytes) -> str:
        if not HAS_WHISPER:
            raise RuntimeError("Whisper not installed")
        try:
            model = whisper.load_model(self.whisper_model)
            import tempfile
            with tempfile.NamedTemporaryFile(suffix=".wav", delete=True) as tf:
                tf.write(audio_bytes); tf.flush()
                res = model.transcribe(tf.name)
                return res.get("text", "")
        except Exception:
            return "<audio_transcription_failed>"

    async def generate_stream(self, prompt: str, images: Optional[List[bytes]] = None, audios: Optional[List[bytes]] = None, session_id: Optional[str] = None) -> AsyncGenerator[str, None]:
        parts = []
        # Image processing with redaction & captioning
        if images:
            for i, img_bytes in enumerate(images):
                caption = self.caption_image(img_bytes)  # face redaction occurs inside caption_image
                reasons = moderate_text(caption)
                if reasons:
                    raise RuntimeError(f"Image caption moderation blocked: {reasons}")
                parts.append(f"[Image {i+1} caption]: {caption}")

        if audios:
            for i, aud_bytes in enumerate(audios):
                transcript = self.transcribe_audio(aud_bytes)
                reasons = moderate_text(transcript)
                if reasons:
                    raise RuntimeError(f"Audio transcription moderation blocked: {reasons}")
                parts.append(f"[Audio {i+1} transcript]: {transcript}")

        ctx = "\n".join(parts) + "\n\n" if parts else ""
        combined_prompt = ctx + "User: " + prompt + "\nAssistant:"
        async for chunk in self.llm.generate_stream(prompt=combined_prompt, session_id=session_id):
            yield chunk