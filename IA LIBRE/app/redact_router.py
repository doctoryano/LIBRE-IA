#!/usr/bin/env python3
"""
app/redact_router.py

FastAPI router that exposes:
 - POST /api/redact  (multipart/form-data)
    fields:
      - image (file, required)
      - method (form, optional: blur|pixelate|blackbox)
      - conf (form, optional: float detection threshold)
      - raw (query param, optional: if set to 1 returns image/jpeg binary instead of JSON)
    Requires Authorization: Bearer <token>

Response:
 - JSON with base64-encoded redacted image and metadata (face_count, rects)
   OR raw image/jpeg when raw=1 (for quick download/inspection).
"""
from __future__ import annotations
import base64
import json
from fastapi import APIRouter, UploadFile, File, Form, Header, HTTPException, Query
from fastapi.responses import JSONResponse, StreamingResponse
from typing import Optional
from pathlib import Path

from app.auth import auth_required
from scripts.face_redact import redact_faces

router = APIRouter()

def token_from_header(authorization: Optional[str] = Header(None)):
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing Authorization header")
    token = authorization.split(" ", 1)[1].strip()
    user = auth_required(token)
    return user

@router.post("/api/redact")
async def api_redact(
    image: UploadFile = File(...),
    method: Optional[str] = Form("blur"),
    conf: Optional[float] = Form(0.35),
    raw: Optional[int] = Query(0),
    authorization: Optional[str] = Header(None),
):
    """
    Redact endpoint for operator QA. Does not call the LLM.
    """
    user = token_from_header(authorization)
    try:
        content = await image.read()
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"failed to read image: {e}")

    # Enforce redaction method choices
    if method not in ("blur", "pixelate", "blackbox"):
        raise HTTPException(status_code=400, detail="invalid method")

    try:
        redacted_bytes, rects = redact_faces(content, method=method, conf_thresh=float(conf))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"redaction_failed: {e}")

    face_count = len(rects)
    metadata = {"face_count": face_count, "rects": [{"x1": r[0], "y1": r[1], "x2": r[2], "y2": r[3], "conf": r[4]} for r in rects]}

    if raw and int(raw) == 1:
        # Return raw JPEG
        return StreamingResponse(iter([redacted_bytes]), media_type="image/jpeg")
    # Return base64 JSON
    b64 = base64.b64encode(redacted_bytes).decode("ascii")
    return JSONResponse({"image_base64": b64, "metadata": metadata})