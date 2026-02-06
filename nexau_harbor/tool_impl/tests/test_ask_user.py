# Copyright 2025 Google LLC
# SPDX-License-Identifier: Apache-2.0
"""
Tests for ask_user - aligned with gemini-cli's ask-user.ts implementation.

Test cases verify input/output format matches gemini-cli exactly.
"""

import pytest

from nexau_harbor.tool_impl.ask_user import ask_user


class TestAskUser:
    """Test ask_user tool functionality matching gemini-cli."""

    def test_validate_questions_required(self):
        """Should return error when questions list is empty."""
        result = ask_user(questions=[])
        
        assert result.get("error") is not None
        assert result["error"]["type"] == "INVALID_PARAMETER"

    def test_validate_question_text_required(self):
        """Should return error when question text is missing."""
        result = ask_user(questions=[{"header": "Test"}])
        
        assert result.get("error") is not None
        assert result["error"]["type"] == "INVALID_PARAMETER"
        assert "question" in result["llmContent"].lower()

    def test_validate_header_required(self):
        """Should return error when header is missing."""
        result = ask_user(questions=[{"question": "What is your name?"}])
        
        assert result.get("error") is not None
        assert result["error"]["type"] == "INVALID_PARAMETER"
        assert "header" in result["llmContent"].lower()

    def test_validate_header_max_length(self):
        """Should return error when header exceeds 12 characters."""
        result = ask_user(questions=[{
            "question": "What is your name?",
            "header": "This is a very long header",
        }])
        
        assert result.get("error") is not None
        assert result["error"]["type"] == "INVALID_PARAMETER"
        assert "12" in result["llmContent"]

    def test_validate_max_questions(self):
        """Should return error when more than 4 questions provided."""
        questions = [
            {"question": f"Q{i}", "header": f"H{i}", "type": "text"}
            for i in range(5)
        ]
        result = ask_user(questions=questions)
        
        assert result.get("error") is not None
        assert result["error"]["type"] == "INVALID_PARAMETER"
        assert "4" in result["llmContent"]

    def test_validate_choice_options_required(self):
        """Should return error when choice type has no options."""
        result = ask_user(questions=[{
            "question": "Choose one",
            "header": "Choice",
            "type": "choice",
        }])
        
        assert result.get("error") is not None
        assert result["error"]["type"] == "INVALID_PARAMETER"

    def test_validate_choice_options_min_count(self):
        """Should return error when choice type has less than 2 options."""
        result = ask_user(questions=[{
            "question": "Choose one",
            "header": "Choice",
            "type": "choice",
            "options": [{"label": "Only one", "description": "desc"}],
        }])
        
        assert result.get("error") is not None
        assert result["error"]["type"] == "INVALID_PARAMETER"

    def test_validate_choice_options_max_count(self):
        """Should return error when choice type has more than 4 options."""
        result = ask_user(questions=[{
            "question": "Choose one",
            "header": "Choice",
            "type": "choice",
            "options": [
                {"label": f"Option {i}", "description": f"desc {i}"}
                for i in range(5)
            ],
        }])
        
        assert result.get("error") is not None
        assert result["error"]["type"] == "INVALID_PARAMETER"


class TestAskUserOutputFormat:
    """Test ask_user output format matches gemini-cli."""

    def test_user_cancelled_format(self):
        """Should format correctly when user cancels."""
        result = ask_user(
            questions=[{
                "question": "What is your name?",
                "header": "Name",
                "type": "text",
            }],
            was_cancelled=True,
        )
        
        assert "dismissed" in result["llmContent"].lower()
        assert result.get("error") is None

    def test_user_answers_format(self):
        """Should format user answers correctly."""
        result = ask_user(
            questions=[{
                "question": "What is your name?",
                "header": "Name",
                "type": "text",
            }],
            user_answers={"0": "Alice"},
        )
        
        assert "answers" in result["llmContent"]
        assert "Alice" in result["returnDisplay"]

    def test_error_format(self):
        """Should format error correctly."""
        result = ask_user(questions=[])
        
        assert result.get("error") is not None
        assert "message" in result["error"]
        assert "type" in result["error"]


class TestAskUserTypes:
    """Test different ask_user question types."""

    def test_yes_no_question(self):
        """Should handle yesno type questions."""
        result = ask_user(
            questions=[{
                "question": "Do you agree?",
                "header": "Agreement",
                "type": "yesno",
            }],
            user_answers={"0": "Yes"},
        )
        
        assert result.get("error") is None
        assert "Yes" in result["returnDisplay"]

    def test_choice_question(self):
        """Should handle choice type questions."""
        result = ask_user(
            questions=[{
                "question": "Select your language:",
                "header": "Language",
                "type": "choice",
                "options": [
                    {"label": "Python", "description": "Python programming language"},
                    {"label": "JavaScript", "description": "JavaScript programming language"},
                ],
            }],
            user_answers={"0": "Python"},
        )
        
        assert result.get("error") is None

    def test_text_question(self):
        """Should handle text type questions."""
        result = ask_user(
            questions=[{
                "question": "Describe your project:",
                "header": "Project",
                "type": "text",
            }],
            user_answers={"0": "My awesome project"},
        )
        
        assert result.get("error") is None
