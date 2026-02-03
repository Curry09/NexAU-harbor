"""
Gemini CLI style termination protocol middleware for NexAU.

Implements the complete_task forced termination protocol.
"""

from nexau.archs.main_sub.execution.hooks import HookResult, Middleware

COMPLETE_TASK_TOOL_NAME = "complete_task"


class CompleteTaskMiddleware(Middleware):
    """
    Middleware that enforces the complete_task termination protocol.
    """
    
    def __init__(self):
        self.task_completed = False
        self.final_result = ""
        self.no_tool_call_count = 0  # 连续无工具调用计数
    
    def before_model(self, hook_input):
        """Inject warning if no tool calls for one turn."""
        if self.no_tool_call_count == 1:
            updated = hook_input.messages + [{
                "role": "user",
                "content": (
                    "You have stopped calling tools without finishing. "
                    "You have one final chance. You MUST call `complete_task` immediately "
                    "with your best answer. Do not call any other tools."
                ),
            }]
            return HookResult.with_modifications(messages=updated)
        return HookResult.no_changes()
    
    def after_model(self, hook_input):
        """Check for protocol violations and handle complete_task."""
        parsed = hook_input.parsed_response
        
        # No parsed response
        if not parsed:
            self.no_tool_call_count += 1
            if self.no_tool_call_count >= 2:
                return HookResult.no_changes()  # 退出
            return HookResult.with_modifications(force_continue=True)
        
        tool_calls = parsed.tool_calls or []
        
        # Check if complete_task was called
        complete_task_call = None
        for call in tool_calls:
            if call.tool_name == COMPLETE_TASK_TOOL_NAME:
                complete_task_call = call
                self.task_completed = True
                self.final_result = call.parameters.get("result", "")
                break
        
        # If complete_task was called, task is done - exit
        if complete_task_call:
            parsed.tool_calls = []
            return HookResult.with_modifications(parsed_response=parsed)
        
        # Has other tool calls - reset counter and continue
        if len(tool_calls) > 0:
            self.no_tool_call_count = 0
            return HookResult.no_changes()
        
        # No tool calls
        self.no_tool_call_count += 1
        if self.no_tool_call_count >= 2:
            return HookResult.no_changes()  # 两轮无工具调用，退出
        return HookResult.with_modifications(force_continue=True)
    
    def after_tool(self, hook_input):
        """Track complete_task execution."""
        if hook_input.tool_name == COMPLETE_TASK_TOOL_NAME:
            self.task_completed = True
        return HookResult.no_changes()
