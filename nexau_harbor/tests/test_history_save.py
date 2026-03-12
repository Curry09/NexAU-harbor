"""
Tests for history saving logic in cli.py

Verifies that _dump_tracer_to_disk correctly serializes agent.history
to nexau_history.json using atomic tmp+rename writes.
"""

import json
import os
import shutil
import tempfile
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from nexau_harbor.cli import (
    _dump_tracer_to_disk,
    _save_tracer_on_exit,
    _tracer_save_state,
)


class _FakeMessage:
    """Minimal stand-in for nexau Message with model_dump support."""

    def __init__(self, role: str, text: str):
        self._role = role
        self._text = text

    def model_dump(self, *, mode: str = "python") -> dict:
        return {"role": self._role, "content": self._text}


class _FakeHistoryList(list):
    """list subclass that behaves like HistoryList for iteration."""
    pass


def _make_agent(history_messages: list[_FakeMessage], *, has_tracer: bool = True):
    """Build a minimal mock agent with .history and .config.tracers."""
    agent = MagicMock()
    history = _FakeHistoryList(history_messages)
    agent.history = history

    if has_tracer:
        tracer = MagicMock()
        tracer.dump_traces.return_value = {"spans": []}
        # Make isinstance check pass for InMemoryTracer
        tracer.__class__ = type("InMemoryTracer", (), {})
        agent.config.tracers = [tracer]
    else:
        agent.config.tracers = []

    return agent


@pytest.fixture(autouse=True)
def _reset_tracer_state():
    """Reset global _tracer_save_state before/after each test."""
    original = dict(_tracer_save_state)
    _tracer_save_state.update({"agent": None, "log_dir": None, "saved": False})
    yield
    _tracer_save_state.update(original)


@pytest.fixture()
def log_dir():
    d = tempfile.mkdtemp(prefix="test-history-save-")
    yield d
    shutil.rmtree(d, ignore_errors=True)


class TestDumpHistoryToDisk:
    """Tests for _dump_tracer_to_disk history saving."""

    def test_saves_history_json(self, log_dir: str):
        msgs = [_FakeMessage("user", "hello"), _FakeMessage("assistant", "hi")]
        agent = _make_agent(msgs, has_tracer=False)

        _tracer_save_state["agent"] = agent
        _tracer_save_state["log_dir"] = log_dir

        _dump_tracer_to_disk()

        path = os.path.join(log_dir, "nexau_history.json")
        assert os.path.exists(path), "nexau_history.json should be created"

        with open(path) as f:
            data = json.load(f)

        assert isinstance(data, list)
        assert len(data) == 2
        assert data[0] == {"role": "user", "content": "hello"}
        assert data[1] == {"role": "assistant", "content": "hi"}

    def test_no_tmp_file_left(self, log_dir: str):
        """Atomic write should not leave .tmp files behind."""
        agent = _make_agent([_FakeMessage("user", "x")], has_tracer=False)
        _tracer_save_state["agent"] = agent
        _tracer_save_state["log_dir"] = log_dir

        _dump_tracer_to_disk()

        tmp_path = os.path.join(log_dir, "nexau_history.json.tmp")
        assert not os.path.exists(tmp_path)

    def test_empty_history(self, log_dir: str):
        agent = _make_agent([], has_tracer=False)
        _tracer_save_state["agent"] = agent
        _tracer_save_state["log_dir"] = log_dir

        _dump_tracer_to_disk()

        path = os.path.join(log_dir, "nexau_history.json")
        with open(path) as f:
            data = json.load(f)
        assert data == []

    def test_overwrites_previous_file(self, log_dir: str):
        """Second dump should overwrite the first."""
        agent = _make_agent([_FakeMessage("user", "v1")], has_tracer=False)
        _tracer_save_state["agent"] = agent
        _tracer_save_state["log_dir"] = log_dir

        _dump_tracer_to_disk()

        agent.history = _FakeHistoryList([_FakeMessage("user", "v2")])
        _dump_tracer_to_disk()

        path = os.path.join(log_dir, "nexau_history.json")
        with open(path) as f:
            data = json.load(f)
        assert len(data) == 1
        assert data[0]["content"] == "v2"

    def test_unicode_content(self, log_dir: str):
        agent = _make_agent(
            [_FakeMessage("user", "你好世界 🌍")], has_tracer=False
        )
        _tracer_save_state["agent"] = agent
        _tracer_save_state["log_dir"] = log_dir

        _dump_tracer_to_disk()

        path = os.path.join(log_dir, "nexau_history.json")
        with open(path, encoding="utf-8") as f:
            raw = f.read()
        assert "你好世界" in raw
        assert "\\u" not in raw, "ensure_ascii=False should preserve unicode"

    def test_skips_when_agent_is_none(self, log_dir: str):
        _tracer_save_state["agent"] = None
        _tracer_save_state["log_dir"] = log_dir

        _dump_tracer_to_disk()

        path = os.path.join(log_dir, "nexau_history.json")
        assert not os.path.exists(path)

    def test_skips_when_log_dir_is_none(self):
        agent = _make_agent([_FakeMessage("user", "x")], has_tracer=False)
        _tracer_save_state["agent"] = agent
        _tracer_save_state["log_dir"] = None

        _dump_tracer_to_disk()
        # no crash, no file written

    def test_model_dump_error_does_not_crash(self, log_dir: str, capsys):
        """If model_dump raises, history save should fail gracefully."""
        bad_msg = MagicMock()
        bad_msg.model_dump.side_effect = TypeError("serialize error")

        agent = _make_agent([], has_tracer=False)
        agent.history = _FakeHistoryList([bad_msg])
        _tracer_save_state["agent"] = agent
        _tracer_save_state["log_dir"] = log_dir

        _dump_tracer_to_disk()

        path = os.path.join(log_dir, "nexau_history.json")
        assert not os.path.exists(path), "should not write partial file on error"

    def test_history_independent_of_tracer_failure(self, log_dir: str):
        """History should still be saved even if tracer dump fails."""
        agent = _make_agent([_FakeMessage("user", "ok")], has_tracer=False)
        # Inject a tracer that raises on dump_traces
        bad_tracer = MagicMock()
        bad_tracer.dump_traces.side_effect = RuntimeError("tracer boom")

        from nexau.archs.tracer.adapters.in_memory import InMemoryTracer
        bad_tracer.__class__ = InMemoryTracer
        agent.config.tracers = [bad_tracer]

        _tracer_save_state["agent"] = agent
        _tracer_save_state["log_dir"] = log_dir

        _dump_tracer_to_disk()

        path = os.path.join(log_dir, "nexau_history.json")
        assert os.path.exists(path), "history should be saved despite tracer failure"
        with open(path) as f:
            data = json.load(f)
        assert len(data) == 1


class TestSaveTracerOnExit:
    """Tests for _save_tracer_on_exit idempotency."""

    def test_saved_flag_prevents_double_write(self, log_dir: str):
        agent = _make_agent([_FakeMessage("user", "once")], has_tracer=False)
        _tracer_save_state["agent"] = agent
        _tracer_save_state["log_dir"] = log_dir
        _tracer_save_state["saved"] = False

        _save_tracer_on_exit()
        path = os.path.join(log_dir, "nexau_history.json")
        assert os.path.exists(path)

        os.remove(path)

        _save_tracer_on_exit()
        assert not os.path.exists(path), "second call should be no-op due to saved flag"

    def test_sets_saved_flag(self, log_dir: str):
        agent = _make_agent([], has_tracer=False)
        _tracer_save_state["agent"] = agent
        _tracer_save_state["log_dir"] = log_dir
        _tracer_save_state["saved"] = False

        _save_tracer_on_exit()
        assert _tracer_save_state["saved"] is True
