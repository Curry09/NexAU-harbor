"""
Example: How to use CompleteTaskMiddleware with NexAU agent.

This demonstrates the complete_task termination protocol integration.
"""

# Example 1: Basic usage with middleware
"""
from nexau.archs.main_sub.agent import Agent
from after_model_hook import CompleteTaskMiddleware, create_complete_task_middleware

# Create the middleware
complete_task_middleware = create_complete_task_middleware(grace_period_enabled=True)

# Create agent with the middleware
agent = Agent(
    system_prompt="You are a helpful assistant. When you finish a task, you MUST call complete_task with your result.",
    middlewares=[complete_task_middleware],
    # ... other config
)

# Run the agent
result = agent.run("What is 2+2?")

# Check termination status
status = complete_task_middleware.get_status()
print(f"Task completed: {status['task_completed']}")
print(f"Terminate reason: {status['terminate_reason']}")
print(f"Result: {status['task_result']}")
"""

# Example 2: System prompt that enforces complete_task protocol
COMPLETE_TASK_SYSTEM_PROMPT_SUFFIX = """

## Task Completion Protocol

CRITICAL: You MUST follow this protocol to complete any task:

1. When you have finished your work and have a final answer, you MUST call the `complete_task` tool.
2. The `complete_task` tool requires a `result` argument containing your comprehensive findings.
3. This is the ONLY way to properly finish a task. Failure to call `complete_task` is a protocol violation.
4. Do NOT stop responding without calling `complete_task`.
5. After calling `complete_task`, do NOT call any other tools.

Example:
```
complete_task(result="The answer to your question is X. Here's my detailed explanation: ...")
```
"""

# Example 3: Tool definition for complete_task
COMPLETE_TASK_TOOL_DEFINITION = {
    "type": "function",
    "function": {
        "name": "complete_task",
        "description": (
            "Call this tool to submit your final answer and complete the task. "
            "This is the ONLY way to finish. You MUST call this tool when your "
            "task is done. Provide comprehensive results in the 'result' argument."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "result": {
                    "type": "string",
                    "description": (
                        "Your final results or findings to return. "
                        "Ensure this is comprehensive and follows any formatting "
                        "requested in your instructions."
                    ),
                },
            },
            "required": ["result"],
        },
    },
}


# Example 4: How termination reasons map to outcomes
"""
Termination Reason Mapping:

| Reason                      | Description                                    | Recovery? |
|-----------------------------|------------------------------------------------|-----------|
| GOAL                        | Normal completion via complete_task            | N/A       |
| MAX_TURNS                   | Hit iteration limit                            | Yes       |
| TIMEOUT                     | Timed out                                      | Yes       |
| ERROR_NO_COMPLETE_TASK_CALL | Model stopped without calling complete_task    | Yes       |
| ERROR                       | Other error                                    | No        |
| CANCELLED                   | User cancelled                                 | No        |

For recoverable errors (MAX_TURNS, TIMEOUT, ERROR_NO_COMPLETE_TASK_CALL):
1. Enter grace period
2. Send warning message to model
3. Only allow complete_task calls
4. If model calls complete_task with valid result -> GOAL
5. If grace period exhausted -> ERROR_NO_COMPLETE_TASK_CALL
"""


if __name__ == "__main__":
    # Quick test of the middleware logic
    from after_model_hook import CompleteTaskMiddleware, TerminateReason
    
    middleware = CompleteTaskMiddleware(grace_period_enabled=True)
    
    print("Initial status:", middleware.get_status())
    
    # Simulate protocol violation (would be triggered by after_model hook)
    middleware.in_grace_period = True
    middleware.terminate_reason = TerminateReason.ERROR_NO_COMPLETE_TASK_CALL
    
    print("After violation:", middleware.get_status())
    
    # Simulate successful recovery
    middleware.task_completed = True
    middleware.task_result = {"answer": "42"}
    middleware.terminate_reason = TerminateReason.GOAL
    middleware.in_grace_period = False
    
    print("After recovery:", middleware.get_status())

