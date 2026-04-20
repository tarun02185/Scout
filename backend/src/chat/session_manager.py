"""Chat session manager — handles multiple chat sessions with persistence."""

import json
import sqlite3
import uuid
from datetime import datetime

from src.config import SESSION_DB_PATH


def _get_db():
    """Get a connection to the sessions database."""
    conn = sqlite3.connect(SESSION_DB_PATH)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS sessions (
            id TEXT PRIMARY KEY,
            title TEXT NOT NULL,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id TEXT NOT NULL,
            role TEXT NOT NULL,
            content TEXT NOT NULL,
            metadata TEXT,
            created_at TEXT NOT NULL,
            FOREIGN KEY (session_id) REFERENCES sessions(id)
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS session_files (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id TEXT NOT NULL,
            file_name TEXT NOT NULL,
            file_metadata TEXT,
            FOREIGN KEY (session_id) REFERENCES sessions(id)
        )
    """)
    conn.commit()
    return conn


def create_session(title: str = "New Chat") -> str:
    """Create a new chat session. Returns session ID."""
    conn = _get_db()
    session_id = str(uuid.uuid4())[:8]
    now = datetime.now().isoformat()
    conn.execute(
        "INSERT INTO sessions (id, title, created_at, updated_at) VALUES (?, ?, ?, ?)",
        (session_id, title, now, now),
    )
    conn.commit()
    conn.close()
    return session_id


def list_sessions() -> list[dict]:
    """List all chat sessions, most recent first."""
    conn = _get_db()
    cursor = conn.execute("SELECT id, title, created_at, updated_at FROM sessions ORDER BY updated_at DESC")
    sessions = []
    for row in cursor.fetchall():
        # Get message count
        msg_count = conn.execute(
            "SELECT COUNT(*) FROM messages WHERE session_id = ?", (row[0],)
        ).fetchone()[0]
        sessions.append({
            "id": row[0],
            "title": row[1],
            "created_at": row[2],
            "updated_at": row[3],
            "message_count": msg_count,
        })
    conn.close()
    return sessions


def get_session_history(session_id: str) -> list[dict]:
    """Get all messages for a session."""
    conn = _get_db()
    cursor = conn.execute(
        "SELECT role, content, metadata, created_at FROM messages WHERE session_id = ? ORDER BY created_at",
        (session_id,),
    )
    messages = []
    for row in cursor.fetchall():
        msg = {"role": row[0], "content": row[1], "created_at": row[3]}
        if row[2]:
            try:
                msg["metadata"] = json.loads(row[2])
            except json.JSONDecodeError:
                pass
        messages.append(msg)
    conn.close()
    return messages


def add_message(session_id: str, role: str, content: str, metadata: dict | None = None):
    """Add a message to a session."""
    conn = _get_db()
    now = datetime.now().isoformat()
    meta_str = json.dumps(metadata) if metadata else None
    conn.execute(
        "INSERT INTO messages (session_id, role, content, metadata, created_at) VALUES (?, ?, ?, ?, ?)",
        (session_id, role, content, meta_str, now),
    )
    # Update session timestamp and title (auto-title from first user message)
    conn.execute("UPDATE sessions SET updated_at = ? WHERE id = ?", (now, session_id))

    # Auto-title from first user message
    if role == "user":
        msg_count = conn.execute(
            "SELECT COUNT(*) FROM messages WHERE session_id = ? AND role = 'user'", (session_id,)
        ).fetchone()[0]
        if msg_count == 1:
            title = content[:50] + ("..." if len(content) > 50 else "")
            conn.execute("UPDATE sessions SET title = ? WHERE id = ?", (title, session_id))

    conn.commit()
    conn.close()


def save_session_files(session_id: str, file_name: str, file_metadata: dict):
    """Save file metadata associated with a session."""
    conn = _get_db()
    meta_str = json.dumps(file_metadata)
    conn.execute(
        "INSERT INTO session_files (session_id, file_name, file_metadata) VALUES (?, ?, ?)",
        (session_id, file_name, meta_str),
    )
    conn.commit()
    conn.close()


def get_session_files(session_id: str) -> list[dict]:
    """Get all files associated with a session."""
    conn = _get_db()
    cursor = conn.execute(
        "SELECT file_name, file_metadata FROM session_files WHERE session_id = ?",
        (session_id,),
    )
    files = []
    for row in cursor.fetchall():
        meta = {}
        if row[1]:
            try:
                meta = json.loads(row[1])
            except json.JSONDecodeError:
                pass
        files.append({"file_name": row[0], **meta})
    conn.close()
    return files


def delete_session(session_id: str):
    """Delete a session and all its messages/files."""
    conn = _get_db()
    conn.execute("DELETE FROM messages WHERE session_id = ?", (session_id,))
    conn.execute("DELETE FROM session_files WHERE session_id = ?", (session_id,))
    conn.execute("DELETE FROM sessions WHERE id = ?", (session_id,))
    conn.commit()
    conn.close()


def remove_session_file(session_id: str, file_name: str) -> int:
    """Remove a single persisted source from a session. Returns rows deleted."""
    conn = _get_db()
    cur = conn.execute(
        "DELETE FROM session_files WHERE session_id = ? AND file_name = ?",
        (session_id, file_name),
    )
    n = cur.rowcount
    conn.commit()
    conn.close()
    return n


def rename_session(session_id: str, new_title: str):
    """Rename a session."""
    conn = _get_db()
    conn.execute("UPDATE sessions SET title = ? WHERE id = ?", (new_title, session_id))
    conn.commit()
    conn.close()
