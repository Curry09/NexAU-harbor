# Copyright 2025 Google LLC (adapted from gemini-cli)
# SPDX-License-Identifier: Apache-2.0
"""
ask_user tool - Asks the user questions to gather preferences.

Based on gemini-cli's ask-user.ts implementation.
Note: In a CLI context, this returns the questions for the user to answer.
"""

import json
from typing import Any


def ask_user(questions: list[dict[str, Any]]) -> str:
    """
    Asks the user one or more questions.
    
    Supports three question types:
    - 'choice': Multiple choice with options (2-4 options)
    - 'text': Free-form text input
    - 'yesno': Yes/No confirmation
    
    Args:
        questions: Array of question objects with:
            - question: The question text
            - header: Short label (max 12 chars)
            - type: 'choice', 'text', or 'yesno' (default: 'choice')
            - options: For 'choice' type, array of {label, description}
            - multiSelect: For 'choice' type, allow multiple selections
            - placeholder: For 'text' type, hint text
            
    Returns:
        JSON string with the questions formatted for user response
    """
    try:
        # Validate input
        if not questions or not isinstance(questions, list):
            return json.dumps({
                "error": "At least one question is required.",
                "type": "INVALID_INPUT",
            })
        
        if len(questions) > 4:
            return json.dumps({
                "error": "Maximum 4 questions allowed.",
                "type": "TOO_MANY_QUESTIONS",
            })
        
        # Validate each question
        validated_questions = []
        for i, q in enumerate(questions):
            if not isinstance(q, dict):
                return json.dumps({
                    "error": f"Question {i + 1}: Must be an object.",
                    "type": "INVALID_QUESTION",
                })
            
            question_text = q.get("question", "")
            header = q.get("header", "")
            q_type = q.get("type", "choice")
            options = q.get("options", [])
            
            if not question_text:
                return json.dumps({
                    "error": f"Question {i + 1}: 'question' is required.",
                    "type": "MISSING_QUESTION",
                })
            
            if not header:
                return json.dumps({
                    "error": f"Question {i + 1}: 'header' is required.",
                    "type": "MISSING_HEADER",
                })
            
            # Validate options for choice type
            if q_type == "choice":
                if not options or len(options) < 2:
                    return json.dumps({
                        "error": f"Question {i + 1}: 'choice' type requires 2-4 options.",
                        "type": "INVALID_OPTIONS",
                    })
                if len(options) > 4:
                    return json.dumps({
                        "error": f"Question {i + 1}: Maximum 4 options allowed.",
                        "type": "TOO_MANY_OPTIONS",
                    })
                
                # Validate option structure
                for j, opt in enumerate(options):
                    if not isinstance(opt, dict):
                        return json.dumps({
                            "error": f"Question {i + 1}, option {j + 1}: Must be an object.",
                            "type": "INVALID_OPTION",
                        })
                    if not opt.get("label"):
                        return json.dumps({
                            "error": f"Question {i + 1}, option {j + 1}: 'label' is required.",
                            "type": "MISSING_LABEL",
                        })
            
            validated_questions.append({
                "index": i,
                "question": question_text,
                "header": header,
                "type": q_type,
                "options": options if q_type == "choice" else None,
                "multiSelect": q.get("multiSelect", False) if q_type == "choice" else None,
                "placeholder": q.get("placeholder") if q_type == "text" else None,
            })
        
        # Format questions for display
        formatted = []
        for q in validated_questions:
            q_formatted = f"\n**[{q['header']}]** {q['question']}"
            
            if q["type"] == "choice" and q["options"]:
                q_formatted += "\nOptions:"
                for j, opt in enumerate(q["options"], 1):
                    label = opt.get("label", "")
                    desc = opt.get("description", "")
                    q_formatted += f"\n  {j}. {label}"
                    if desc:
                        q_formatted += f" - {desc}"
                if q["multiSelect"]:
                    q_formatted += "\n  (Multiple selections allowed)"
            elif q["type"] == "yesno":
                q_formatted += "\n  [Yes / No]"
            elif q["type"] == "text":
                if q["placeholder"]:
                    q_formatted += f"\n  (Hint: {q['placeholder']})"
            
            formatted.append(q_formatted)
        
        # Return the formatted questions
        return json.dumps({
            "type": "ask_user",
            "questions": validated_questions,
            "formatted_display": "\n".join(formatted),
            "message": "Please answer the following question(s):",
            "awaiting_response": True,
        }, ensure_ascii=False)
        
    except Exception as e:
        return json.dumps({
            "error": f"Error processing questions: {str(e)}",
            "type": "ASK_USER_ERROR",
        })
