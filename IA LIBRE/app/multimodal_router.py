"""
app/multimodal_router.py

FastAPI APIRouter que añade un endpoint /api/multimodal accepting:
- multipart/form-data: fields: message (text), images[] (files), audios[] (files)
- Requires Authorization: Bearer <token>

This router uses MultimodalAdapter from app/multimodal_adapter.py
"""
from fastapi import APIRouter, File, UploadFile, Form, Depends, HTTPException, Header
from fastapi.responses import StreamingResponse
from typing import List, Optional
import io

from app.auth import auth_required
from app.multimodal_adapter import MultimodalAdapter, moderate_text

router = APIRouter()
adapter = MultimodalAdapter()

def token_from_header(authorization: Optional[str] = Header(None)):
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing Authorization header")
    token = authorization.split(" ", 1)[1].strip()
    # verify token
    user = auth_required(token)
    return user

@router.post("/api/multimodal")
async def api_multimodal(
    message: str = Form(...),
    images: Optional[List[UploadFile]] = File(None),
    audios: Optional[List[UploadFile]] = File(None),
    authorization: Optional[str] = Header(None)
):
    user = token_from_header(authorization)
    # Read files into bytes
    img_bytes_list = []
    aud_bytes_list = []
    if images:
        for up in images:
            content = await up.read()
            img_bytes_list.append(content)
    if audios:
        for up in audios:
            content = await up.read()
            aud_bytes_list.append(content)

    # Moderation: quick textual check on message
    reasons = moderate_text(message)
    if reasons:
        # return an SSE blocked event
        async def blocked_gen():
            yield ("data: " + json.dumps({"type":"blocked","reasons":reasons,"message":"Blocked by RUP moderation"}) + "\n\n").encode("utf-8")
        return StreamingResponse(blocked_gen(), media_type="text/event-stream")

    # Stream from adapter
    async def gen():
        try:
            async for chunk in adapter.generate_stream(prompt=message, images=img_bytes_list if img_bytes_list else None, audios=aud_bytes_list if aud_bytes_list else None, session_id=user):
                yield ("data: " + json.dumps({"type":"token","text":chunk}, ensure_ascii=False) + "\n\n").encode("utf-8")
        except Exception as e:
            yield ("data: " + json.dumps({"type":"error","message":str(e)}) + "\n\n").encode("utf-8")
            return
        yield ("data: " + json.dumps({"type":"end","meta":{"adapter":adapter.name()}}) + "\n\n").encode("utf-8")
    return StreamingResponse(gen(), media_type="text/event-stream")