"""Tests for chat session management."""

import os
import pytest

# Use a temp DB for tests
os.environ["SESSION_DB_PATH"] = "/tmp/test_sessions.db"

from src.chat.session_manager import (
    create_session, list_sessions, get_session_history,
    add_message, delete_session, rename_session,
)
from src.chat.history import build_conversation_context, extract_last_topic


class TestSessionManager:
    """Test chat session CRUD operations."""

    def setup_method(self):
        """Clean up test DB before each test."""
        try:
            os.unlink("/tmp/test_sessions.db")
        except FileNotFoundError:
            pass

    def test_create_session(self):
        session_id = create_session("Test Chat")
        assert session_id is not None
        assert len(session_id) == 8

    def test_list_sessions(self):
        create_session("Chat 1")
        create_session("Chat 2")
        sessions = list_sessions()
        assert len(sessions) >= 2

    def test_add_and_get_messages(self):
        session_id = create_session("Test")
        add_message(session_id, "user", "Hello")
        add_message(session_id, "assistant", "Hi there!")

        history = get_session_history(session_id)
        assert len(history) == 2
        assert history[0]["role"] == "user"
        assert history[0]["content"] == "Hello"
        assert history[1]["role"] == "assistant"

    def test_auto_title(self):
        session_id = create_session()
        add_message(session_id, "user", "What are the total sales for this quarter?")

        sessions = list_sessions()
        current = [s for s in sessions if s["id"] == session_id][0]
        assert "total sales" in current["title"].lower()

    def test_delete_session(self):
        session_id = create_session("To Delete")
        add_message(session_id, "user", "test")
        delete_session(session_id)

        sessions = list_sessions()
        assert not any(s["id"] == session_id for s in sessions)

    def test_rename_session(self):
        session_id = create_session("Old Name")
        rename_session(session_id, "New Name")

        sessions = list_sessions()
        current = [s for s in sessions if s["id"] == session_id][0]
        assert current["title"] == "New Name"


class TestConversationHistory:
    """Test conversation context building."""

    def test_build_context_empty(self):
        result = build_conversation_context([])
        assert result == []

    def test_build_context_trims(self):
        messages = [{"role": "user", "content": f"message {i}"} for i in range(20)]
        result = build_conversation_context(messages, max_messages=5)
        assert len(result) == 5

    def test_build_context_truncates_long_messages(self):
        messages = [{"role": "user", "content": "x" * 1000}]
        result = build_conversation_context(messages)
        assert len(result[0]["content"]) < 1000

    def test_extract_last_topic(self):
        messages = [
            {"role": "user", "content": "Show me revenue by region"},
            {"role": "assistant", "content": "Here is the revenue breakdown by region..."},
        ]
        topic = extract_last_topic(messages)
        assert topic["last_query"] == "Show me revenue by region"
        assert topic["last_response_summary"] is not None
