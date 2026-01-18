# Multimodal — IA LIBRE 2026 (Operador)

Resumen
- Soporte para: imágenes y audio (captions, transcripciones).
- Pipeline:
  1) UI / API recibe files (multipart)
  2) Vision encoder (BLIP-2) produce caption(s)
  3) Whisper (opcional) transcribe audio
  4) Moderación textual sobre captions/transcripts
  5) Composición del contexto + prompt => LLM adapter para generación
  6) Result streaming al cliente (SSE)

Requisitos (resumen)
- BLIP-2 (transformers) para captioning (GPU recommended)
- Whisper para audio (optional)
- GPU (vLLM) para good throughput; CPU-only can run ggml for smaller models
- .env: ADAPTER_RUNTIME, VLLM_MODEL_PATH, etc.

Privacidad & PII
- No almacenar imágenes o audio sin consentimiento.
- Captions/transcripts pasan por moderación; redacción automática de PII (emails, keys).
- Para fotos que contienen faces: si el operador requiere redacción facial, instala OpenCV + face detection and enable face redaction pipeline.

Limitaciones
- No se permite procesar imágenes que contienen instrucciones militares o materiales peligrosos (RUP) — se bloquea por moderación textual del caption.
- Esta implementación depende de captioners que no garantizan 100% detección de contenido; añade tests de red-team.

Operación
- Habilita multimodal instalando requirements_multimodal.txt
- Construye sandbox image
- Test flow: Upload an image + prompt in UI or use curl multipart calling /api/multimodal