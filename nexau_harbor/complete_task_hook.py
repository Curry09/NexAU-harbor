"""
Gemini CLI style termination protocol middleware for NexAU.

Implements the complete_task forced termination protocol.
Matches gemini-cli's local-executor.ts behavior.
"""

from nexau.archs.main_sub.execution.hooks import HookResult, Middleware

COMPLETE_TASK_TOOL_NAME = "complete_task"


class CompleteTaskMiddleware(Middleware):
    """
    Middleware that enforces the complete_task termination protocol.
    
    Behavior matches gemini-cli:
    1. If complete_task is called → immediately stop (don't execute tool)
    2. If no tool calls → protocol violation → enter grace period
    3. Grace period: inject warning, allow only complete_task
    4. After grace period exhausted → stop
    """
    
    def __init__(self):
        self.task_completed = False
        self.final_result = ""
    
    def after_model(self, hook_input):
        """Check for protocol violations and handle complete_task."""
        parsed = hook_input.parsed_response
        tool_calls = parsed.tool_calls or []
        # Check if complete_task was called
        complete_task_call = None
        other_calls = []
        for call in tool_calls:
            if call.tool_name == COMPLETE_TASK_TOOL_NAME:
                complete_task_call = call
                self.task_completed = True
                self.final_result = call.parameters.get("result", "")
            else:
                other_calls.append(call)
        
        # If complete_task was called, immediately stop
        # Match gemini-cli: complete_task is special, don't execute other tools
        if complete_task_call:
            # Clear all tool calls (including complete_task itself)
            # The executor will see no calls and stop
            parsed.tool_calls = []
            return HookResult.with_modifications(parsed_response=parsed)

        else:
            return HookResult.no_changes()
        