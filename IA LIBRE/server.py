#!/usr/bin/env python3
"""
server.py

FastAPI server with:
 - JWT authentication (register/login)
 - /api/chat streaming SSE endpoint (requires JWT)
 - Conversation CRUD endpoints
 - Moderation filters (banned keywords + PII heuristics)
 - Adapter selection (vllm / ggml / hf / echo)
"""
from __future__ import annotations
import os
import re
import json
import time
import asyncio
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional, AsyncGenerator

from fastapi import FastAPI, Request, HTTPException, Depends, Header
from fastapi.responses import StreamingResponse, FileResponse, HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware

from app.auth import create_access_token, verify_password, get_password_hash, decode_token, auth_required
from app.db import init_db, get_db, create_user, fetch_user_by_username, save_message, list_conversations, create_conversation, get_conversation_messages
from app.model_adapter import get_adapter

REPO_ROOT = Path(__file__).resolve().parent
LOG_DIR = REPO_ROOT / "data" / "logs"
LOG_DIR.mkdir(parents=True, exist_ok=True)

# load banned keywords
FILTERS_PATH = REPO_ROOT / "data" / "filters" / "banned_keywords.txt"
def load_banned_keywords(path: Path):
    kws=[]
    try:
        with path.open("r", encoding="utf-8") as fh:
            for ln in fh:
                ln=ln.strip()
                if not ln or ln.startswith("#"): continue
                kws.append(ln)
    except FileNotFoundError:
        kws=["weapon","bomb","explosive","detonate","rifle","gun"]
    return sorted(set(kws), key=lambda s:-len(s))
BANNED_KEYWORDS = load_banned_keywords(FILTERS_PATH)
BANNED_RE = re.compile(r"\b(" + "|".join([re.escape(k) for k in BANNED_KEYWORDS]) + r")\b", re.IGNORECASE)
RE_EMAIL = re.compile(r"[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+")
RE_IPv4 = re.compile(r"\b(?:\d{1,3}\.){3}\d{1,3}\b")

app = FastAPI(title="IA LIBRE 2026 — Chat UI")
app.mount("/static", StaticFiles(directory=REPO_ROOT / "web"), name="static")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

# Initialize DB
init_db(REPO_ROOT / "data" / "ia_liber_db.sqlite3")

# Adapter
ADAPTER = get_adapter()  # selects based on env ADAPTER_RUNTIME and availability

def moderation_check(text: str):
    reasons=[]
    if BANNED_RE.search(text): reasons.append("contains_banned_keyword")
    if RE_EMAIL.search(text): reasons.append("contains_email")
    if RE_IPv4.search(text): reasons.append("contains_ip")
    return (len(reasons)>0, reasons)

async def stream_response_generator(prompt: str, user: str, conv_id: Optional[int] = None) -> AsyncGenerator[bytes, None]:
    """
    Stream tokens from adapter and persist assistant messages into DB as completed.
    Yields SSE events (data: <json>\n\n).
    """
    start = time.time()
    assistant_chunks = []
    try:
        async for chunk in ADAPTER.generate_stream(prompt=prompt, session_id=f"{user}:{conv_id}" if conv_id else user):
            assistant_chunks.append(chunk)
            payload = {"type": "token", "text": chunk}
            yield ("data: " + json.dumps(payload, ensure_ascii=False) + "\n\n").encode("utf-8")
    except Exception as e:
        payload = {"type": "error", "message": str(e)}
        yield ("data: " + json.dumps(payload, ensure_ascii=False) + "\n\n").encode("utf-8")
        return
    # Finished — persist whole assistant message
    assistant_text = "".join(assistant_chunks)
    # save assistant message
    if conv_id:
        try:
            save_message(get_db(), conv_id, "assistant", assistant_text, user)
        except Exception:
            pass
    end = time.time()
    meta = {"type": "end", "meta": {"model": ADAPTER.name(), "duration_s": end - start, "timestamp": datetime.utcnow().isoformat()+"Z"}}
    yield ("data: " + json.dumps(meta, ensure_ascii=False) + "\n\n").encode("utf-8")


@app.get("/", response_class=HTMLResponse)
async def homepage():
    p = REPO_ROOT / "web" / "index.html"
    if p.exists():
        return FileResponse(p)
    return HTMLResponse("<h1>IA LIBRE 2026</h1><p>Frontend missing.</p>")


@app.post("/api/register")
async def api_register(req: Request):
    body = await req.json()
    username = body.get("username")
    password = body.get("password")
    if not username or not password:
        raise HTTPException(status_code=400, detail="username and password required")
    if fetch_user_by_username(get_db(), username):
        raise HTTPException(status_code=400, detail="username exists")
    pw_hash = get_password_hash(password)
    create_user(get_db(), username, pw_hash)
    return JSONResponse({"ok": True, "msg": "user created"})


@app.post("/api/login")
async def api_login(req: Request):
    body = await req.json()
    username = body.get("username")
    password = body.get("password")
    if not username or not password:
        raise HTTPException(status_code=400, detail="username and password required")
    user = fetch_user_by_username(get_db(), username)
    if not user or not verify_password(password, user["password_hash"]):
        raise HTTPException(status_code=401, detail="invalid credentials")
    token = create_access_token({"sub": username}, expires_delta=timedelta(hours=12))
    return JSONResponse({"access_token": token, "token_type": "bearer"})


@app.post("/api/chat")
async def api_chat(request: Request, authorization: Optional[str] = Header(None)):
    """
    Accepts JSON { "message": "...", "conversation_id": optional }
    Requires Authorization: Bearer <token>
    Returns SSE stream of tokens or a blocked message if moderation triggered.
    """
    db = get_db()
    token = None
    if authorization and authorization.startswith("Bearer "):
        token = authorization.split(" ", 1)[1].strip()
    user = auth_required(token)
    body = await request.json()
    message = body.get("message", "")
    conv_id = body.get("conversation_id")
    if not message or not isinstance(message, str):
        raise HTTPException(status_code=400, detail="message required")
    blocked, reasons = moderation_check(message)
    if blocked:
        async def blocked_gen():
            payload = {"type": "blocked", "reasons": reasons, "message": "Solicitud bloqueada por RUP. Edita tu prompt."}
            yield ("data: " + json.dumps(payload, ensure_ascii=False) + "\n\n").encode("utf-8")
        return StreamingResponse(blocked_gen(), media_type="text/event-stream")
    # Save user message
    if conv_id:
        save_message(db, conv_id, "user", message, user)
    else:
        # create conversation
        conv_id = create_conversation(db, f"conv-{user}-{int(time.time())}", user)
        save_message(db, conv_id, "user", message, user)
    # stream response
    return StreamingResponse(stream_response_generator(message, user, conv_id), media_type="text/event-stream")


# Conversation endpoints
@app.get("/api/conversations")
async def api_list_conversations(authorization: Optional[str] = Header(None)):
    token = None
    if authorization and authorization.startswith("Bearer "):
        token = authorization.split(" ",1)[1].strip()
    user = auth_required(token)
    rows = list_conversations(get_db(), user)
    return JSONResponse({"conversations": rows})


@app.get("/api/conversations/{conv_id}/messages")
async def api_conv_messages(conv_id: int, authorization: Optional[str] = Header(None)):
    token = None
    if authorization and authorization.startswith("Bearer "):
        token = authorization.split(" ",1)[1].strip()
    user = auth_required(token)
    msgs = get_conversation_messages(get_db(), conv_id, user)
    return JSONResponse({"messages": msgs})