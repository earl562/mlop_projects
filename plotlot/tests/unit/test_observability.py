"""Tests for the observability module — prompt registry + structured logging."""

import json
import logging

import pytest

from plotlot.observability.logging import (
    JSONFormatter,
    correlation_id,
    get_correlation_id,
    setup_logging,
)
from plotlot.observability.prompts import (
    get_active_prompt,
    get_prompt_version,
    list_prompts,
)


class TestPromptRegistry:
    def test_get_active_prompt_returns_string(self):
        """The analysis prompt should be a non-empty string."""
        prompt = get_active_prompt("analysis")
        assert isinstance(prompt, str)
        assert len(prompt) > 100
        assert "submit_report" in prompt

    def test_get_prompt_version(self):
        """Prompt version should be a non-empty string."""
        version = get_prompt_version("analysis")
        assert version == "v1"

    def test_list_prompts(self):
        """All registered prompts are listed."""
        prompts = list_prompts()
        assert len(prompts) == 3
        names = [p["name"] for p in prompts]
        assert "analysis" in names
        assert "chat_agent" in names
        assert "direct_analysis" in names

    def test_unknown_prompt_raises(self):
        """Unknown prompt name raises KeyError."""
        with pytest.raises(KeyError, match="Unknown prompt"):
            get_active_prompt("nonexistent")


class TestJSONFormatter:
    def test_json_formatter_output(self):
        """JSONFormatter produces valid JSON with required fields."""
        formatter = JSONFormatter()
        record = logging.LogRecord(
            name="plotlot.test",
            level=logging.INFO,
            pathname="test.py",
            lineno=1,
            msg="test message",
            args=None,
            exc_info=None,
        )
        output = formatter.format(record)
        parsed = json.loads(output)
        assert parsed["level"] == "INFO"
        assert parsed["logger"] == "plotlot.test"
        assert parsed["message"] == "test message"
        assert "timestamp" in parsed

    def test_json_formatter_includes_correlation_id(self):
        """Correlation ID appears in JSON output when set."""
        formatter = JSONFormatter()
        token = correlation_id.set("test-123")
        try:
            record = logging.LogRecord(
                name="test",
                level=logging.INFO,
                pathname="",
                lineno=1,
                msg="hi",
                args=None,
                exc_info=None,
            )
            parsed = json.loads(formatter.format(record))
            assert parsed["correlation_id"] == "test-123"
        finally:
            correlation_id.reset(token)

    async def test_correlation_id_propagation(self):
        """ContextVar propagates correlation ID across async chain."""
        results = []

        async def inner():
            results.append(get_correlation_id())

        token = correlation_id.set("async-456")
        try:
            await inner()
        finally:
            correlation_id.reset(token)

        assert results == ["async-456"]

    def test_setup_logging_json(self):
        """setup_logging with json_format=True installs JSONFormatter."""
        setup_logging(json_format=True, level="WARNING")
        root = logging.getLogger()
        assert len(root.handlers) >= 1
        assert isinstance(root.handlers[0].formatter, JSONFormatter)
        # Restore default for other tests
        setup_logging(json_format=False, level="INFO")
