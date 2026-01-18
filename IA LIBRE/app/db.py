from __future__ import annotations
import sqlite3
from pathlib import Path
from typing import Optional, List, Dict

_db_conn: Optional[sqlite3.Connection] = None

def init_db(path: Path):
    global _db_conn
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path))
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()
    # users
    cur.execute("""
    CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY,
        username TEXT UNIQUE NOT NULL,
        password_hash TEXT NOT NULL,
        created_at TEXT DEFAULT CURRENT_TIMESTAMP
    )
    """)
    # conversations
    cur.execute("""
    CREATE TABLE IF NOT EXISTS conversations (
        id INTEGER PRIMARY KEY,
        title TEXT,
        owner TEXT,
        created_at TEXT DEFAULT CURRENT_TIMESTAMP
    )
    """)
    # messages
    cur.execute("""
    CREATE TABLE IF NOT EXISTS messages (
        id INTEGER PRIMARY KEY,
        conv_id INTEGER,
        role TEXT,
        content TEXT,
        author TEXT,
        created_at TEXT DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY(conv_id) REFERENCES conversations(id)
    )
    """)
    conn.commit()
    _db_conn = conn

def get_db():
    global _db_conn
    if not _db_conn:
        raise RuntimeError("DB not initialized. Call init_db(path).")
    return _db_conn

# Users
def create_user(conn, username: str, password_hash: str):
    cur = conn.cursor()
    cur.execute("INSERT INTO users (username, password_hash) VALUES (?, ?)", (username, password_hash))
    conn.commit()
    return cur.lastrowid

def fetch_user_by_username(conn, username: str):
    cur = conn.cursor()
    cur.execute("SELECT id, username, password_hash, created_at FROM users WHERE username = ?", (username,))
    row = cur.fetchone()
    return dict(row) if row else None

# Conversations
def create_conversation(conn, title: str, owner: str):
    cur = conn.cursor()
    cur.execute("INSERT INTO conversations (title, owner) VALUES (?, ?)", (title, owner))
    conn.commit()
    return cur.lastrowid

def list_conversations(conn, owner: str):
    cur = conn.cursor()
    cur.execute("SELECT id, title, owner, created_at FROM conversations WHERE owner = ? ORDER BY created_at DESC", (owner,))
    rows = cur.fetchall()
    return [dict(r) for r in rows]

def save_message(conn, conv_id: int, role: str, content: str, author: str):
    cur = conn.cursor()
    cur.execute("INSERT INTO messages (conv_id, role, content, author) VALUES (?, ?, ?, ?)", (conv_id, role, content, author))
    conn.commit()
    return cur.lastrowid

def get_conversation_messages(conn, conv_id: int, owner: str):
    # ensure conv belongs to owner
    cur = conn.cursor()
    cur.execute("SELECT owner FROM conversations WHERE id = ?", (conv_id,))
    row = cur.fetchone()
    if not row or row["owner"] != owner:
        return []
    cur.execute("SELECT id, role, content, author, created_at FROM messages WHERE conv_id = ? ORDER BY created_at ASC", (conv_id,))
    rows = cur.fetchall()
    return [dict(r) for r in rows]