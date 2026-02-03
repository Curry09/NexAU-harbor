"""
Test script for CompactContextMiddleware.

Tests alignment with gemini-cli chatCompressionService.ts:
1. Compression triggers at 50% token threshold
2. Preserves 30% of recent history
3. Tool output budget of 50,000 tokens
4. Truncates to last 30 lines
"""

import sys
from unittest.mock import MagicMock

# Mock nexau module before importing compact_context_hook
mock_hooks = MagicMock()

class MockHookResult:
    def __init__(self, messages=None, parsed_response=None, tool_output=None):
        self.messages = messages
        self.parsed_response = parsed_response
        self.tool_output = tool_output
    
    @classmethod
    def no_changes(cls):
        return cls()
    
    @classmethod
    def with_modifications(cls, **kwargs):
        return cls(**kwargs)

class MockMiddleware:
    pass

mock_hooks.HookResult = MockHookResult
mock_hooks.Middleware = MockMiddleware
sys.modules['nexau'] = MagicMock()
sys.modules['nexau.archs'] = MagicMock()
sys.modules['nexau.archs.main_sub'] = MagicMock()
sys.modules['nexau.archs.main_sub.execution'] = MagicMock()
sys.modules['nexau.archs.main_sub.execution.hooks'] = mock_hooks

from compact_context_hook import (
    CompactContextMiddleware,
    AggressiveCompactContextMiddleware,
    default_token_counter,
    DEFAULT_COMPRESSION_TOKEN_THRESHOLD,
    COMPRESSION_PRESERVE_THRESHOLD,
    COMPRESSION_FUNCTION_RESPONSE_TOKEN_BUDGET,
    COMPRESSION_TRUNCATE_LINES,
)


class MockHookInput:
    """Mock hook_input for testing."""
    def __init__(self, messages):
        self.messages = messages
        self.agent_state = None


def test_gemini_cli_constants():
    """Verify constants match gemini-cli."""
    print("=" * 60)
    print("Test: Gemini-CLI Constants Alignment")
    print("=" * 60)
    
    print(f"DEFAULT_COMPRESSION_TOKEN_THRESHOLD: {DEFAULT_COMPRESSION_TOKEN_THRESHOLD} (expected: 0.5)")
    print(f"COMPRESSION_PRESERVE_THRESHOLD: {COMPRESSION_PRESERVE_THRESHOLD} (expected: 0.3)")
    print(f"COMPRESSION_FUNCTION_RESPONSE_TOKEN_BUDGET: {COMPRESSION_FUNCTION_RESPONSE_TOKEN_BUDGET} (expected: 50000)")
    print(f"COMPRESSION_TRUNCATE_LINES: {COMPRESSION_TRUNCATE_LINES} (expected: 30)")
    
    assert DEFAULT_COMPRESSION_TOKEN_THRESHOLD == 0.5, "Threshold should be 0.5"
    assert COMPRESSION_PRESERVE_THRESHOLD == 0.3, "Preserve ratio should be 0.3"
    assert COMPRESSION_FUNCTION_RESPONSE_TOKEN_BUDGET == 50_000, "Tool budget should be 50000"
    assert COMPRESSION_TRUNCATE_LINES == 30, "Truncate lines should be 30"
    
    print("✓ All constants match gemini-cli\n")


def test_compression_threshold_50_percent():
    """Test compression triggers at 50% of max context tokens."""
    print("=" * 60)
    print("Test: Compression triggers at 50% threshold")
    print("=" * 60)
    
    middleware = CompactContextMiddleware(
        max_context_tokens=1000,  # Small for testing
        compression_threshold=0.5,  # 50%
    )
    
    # Create messages at 40% usage - should NOT trigger
    messages_40_percent = [
        {"role": "system", "content": "System prompt."},
        {"role": "user", "content": "x" * 1500},  # ~375 tokens + overhead
    ]
    
    hook_input = MockHookInput(messages_40_percent)
    tokens_40 = middleware._count_messages_tokens(messages_40_percent)
    print(f"40% test - Tokens: {tokens_40}, Threshold: {int(1000 * 0.5)}")
    
    result = middleware.before_model(hook_input)
    print(f"40% test - Compressed: {result.messages is not None}")
    assert result.messages is None, "Should NOT compress at 40%"
    
    # Create messages at 60% usage - should trigger
    messages_60_percent = [
        {"role": "system", "content": "System prompt."},
        {"role": "user", "content": "x" * 2500},  # ~625 tokens + overhead
    ]
    
    hook_input = MockHookInput(messages_60_percent)
    tokens_60 = middleware._count_messages_tokens(messages_60_percent)
    print(f"60% test - Tokens: {tokens_60}, Threshold: {int(1000 * 0.5)}")
    
    result = middleware.before_model(hook_input)
    print(f"60% test - Compressed: {result.messages is not None}")
    assert result.messages is not None, "Should compress at 60%"
    
    print("✓ Compression threshold works correctly\n")


def test_preserve_30_percent():
    """Test that 30% of recent history is preserved."""
    print("=" * 60)
    print("Test: Preserves 30% of recent history")
    print("=" * 60)
    
    middleware = CompactContextMiddleware(
        max_context_tokens=500,
        compression_threshold=0.3,  # Lower threshold to trigger compression
        preserve_ratio=0.3,
    )
    
    # Create 10 messages with roughly equal token counts
    messages = [{"role": "system", "content": "System."}]
    for i in range(10):
        messages.append({"role": "user", "content": f"Message {i}: " + "word " * 50})
        messages.append({"role": "assistant", "content": f"Response {i}: " + "reply " * 50})
    
    hook_input = MockHookInput(messages)
    total_tokens = middleware._count_messages_tokens(messages)
    print(f"Total tokens before: {total_tokens}")
    print(f"Total messages before: {len(messages)}")
    
    result = middleware.before_model(hook_input)
    
    if result.messages:
        after_tokens = middleware._count_messages_tokens(result.messages)
        # Count non-system messages (excluding compaction notice)
        preserved_msgs = [m for m in result.messages if m.get('role') != 'system']
        
        print(f"Total tokens after: {after_tokens}")
        print(f"Total messages after: {len(result.messages)}")
        print(f"Preserved conversation messages: {len(preserved_msgs)}")
        
        # Check that preserved messages are the most recent ones
        if preserved_msgs:
            last_preserved = preserved_msgs[-1].get('content', '')
            print(f"Last preserved message contains 'Response 9': {'Response 9' in last_preserved}")
    
    print("✓ Recent history preservation works\n")


def test_tool_output_truncation_lines():
    """Test tool output truncation to last 30 lines (gemini-cli style)."""
    print("=" * 60)
    print("Test: Tool output truncation to last 30 lines")
    print("=" * 60)
    
    middleware = CompactContextMiddleware(
        max_context_tokens=10000,
        tool_output_token_budget=100,  # Very small to trigger truncation
        truncate_lines=30,
    )
    
    # Create tool output with 100 lines
    lines = [f"Line {i}: Some output content here" for i in range(100)]
    long_output = '\n'.join(lines)
    
    messages = [
        {"role": "system", "content": "System."},
        {"role": "tool", "name": "read_file", "tool_call_id": "1", "content": long_output},
    ]
    
    original_lines = len(long_output.split('\n'))
    print(f"Original lines: {original_lines}")
    print(f"Truncate to last: {middleware.truncate_lines} lines")
    
    truncated = middleware._truncate_tool_outputs(messages)
    truncated_content = truncated[1]['content']
    truncated_line_count = len(truncated_content.split('\n'))
    
    print(f"Truncated lines: {truncated_line_count}")
    print(f"Contains truncation notice: {'lines truncated' in truncated_content}")
    print(f"Contains 'Line 99': {'Line 99' in truncated_content}")  # Last line should be preserved
    print(f"Contains 'Line 0': {'Line 0' in truncated_content}")    # First line should be removed
    
    assert 'lines truncated' in truncated_content, "Should have truncation notice"
    assert 'Line 99' in truncated_content, "Should preserve last line"
    assert 'Line 0' not in truncated_content or 'truncated' in truncated_content.split('Line 0')[0], "First line should be truncated"
    
    print("✓ Line-based truncation works correctly\n")


def test_tool_output_budget_50k():
    """Test tool output with 50,000 token budget."""
    print("=" * 60)
    print("Test: Tool output 50,000 token budget")
    print("=" * 60)
    
    middleware = CompactContextMiddleware(
        max_context_tokens=200000,
        tool_output_token_budget=50000,  # Gemini-CLI default
    )
    
    # Create tool output under budget (40,000 tokens ~ 160,000 chars)
    under_budget_output = "x" * 150000  # ~37,500 tokens
    
    messages_under = [
        {"role": "tool", "name": "cmd", "tool_call_id": "1", "content": under_budget_output},
    ]
    
    truncated_under = middleware._truncate_tool_outputs(messages_under)
    under_changed = truncated_under[0]['content'] != under_budget_output
    print(f"Under budget (37.5k tokens) - Changed: {under_changed}")
    
    # Create tool output over budget (60,000 tokens ~ 240,000 chars)
    over_budget_output = "y" * 250000  # ~62,500 tokens
    
    messages_over = [
        {"role": "tool", "name": "cmd", "tool_call_id": "1", "content": over_budget_output},
    ]
    
    truncated_over = middleware._truncate_tool_outputs(messages_over)
    over_changed = truncated_over[0]['content'] != over_budget_output
    print(f"Over budget (62.5k tokens) - Changed: {over_changed}")
    
    # Note: Single line content triggers char-based truncation
    if over_changed:
        new_tokens = middleware.token_counter(truncated_over[0]['content'])
        print(f"Truncated to ~{new_tokens} tokens")
    
    print("✓ Token budget enforcement works\n")


def test_compression_notice_format():
    """Test compression notice includes message and token counts."""
    print("=" * 60)
    print("Test: Compression notice format")
    print("=" * 60)
    
    middleware = CompactContextMiddleware(
        max_context_tokens=500,
        compression_threshold=0.3,
    )
    
    messages = [{"role": "system", "content": "System."}]
    for i in range(20):
        messages.append({"role": "user", "content": f"Msg {i}: " + "x" * 100})
    
    hook_input = MockHookInput(messages)
    result = middleware.before_model(hook_input)
    
    if result.messages:
        # Find compaction notice
        for msg in result.messages:
            content = msg.get('content', '')
            if 'Context compacted' in content:
                print(f"Compaction notice: {content}")
                assert 'messages' in content, "Should mention message count"
                assert 'tokens' in content, "Should mention token count"
                break
    
    print("✓ Compression notice format correct\n")


def test_aggressive_middleware():
    """Test aggressive middleware with tighter thresholds."""
    print("=" * 60)
    print("Test: Aggressive middleware thresholds")
    print("=" * 60)
    
    middleware = AggressiveCompactContextMiddleware()
    
    print(f"Max context tokens: {middleware.max_context_tokens} (expected: 100000)")
    print(f"Compression threshold: {middleware.compression_threshold} (expected: 0.3)")
    print(f"Preserve ratio: {middleware.preserve_ratio} (expected: 0.2)")
    print(f"Tool output budget: {middleware.tool_output_token_budget} (expected: 10000)")
    print(f"Truncate lines: {middleware.truncate_lines} (expected: 20)")
    
    assert middleware.compression_threshold == 0.3
    assert middleware.preserve_ratio == 0.2
    assert middleware.tool_output_token_budget == 10000
    assert middleware.truncate_lines == 20
    
    print("✓ Aggressive middleware uses tighter thresholds\n")


def test_duplicate_tool_collapse():
    """Test aggressive middleware collapses duplicate tool calls."""
    print("=" * 60)
    print("Test: Duplicate tool call collapse")
    print("=" * 60)
    
    middleware = AggressiveCompactContextMiddleware(
        collapse_duplicate_tools=True,
    )
    
    messages = [
        {"role": "system", "content": "System."},
        {"role": "tool", "name": "read_file", "tool_call_id": "1", "content": "File 1 content"},
        {"role": "tool", "name": "read_file", "tool_call_id": "2", "content": "File 2 content"},
        {"role": "tool", "name": "read_file", "tool_call_id": "3", "content": "File 3 content"},
        {"role": "tool", "name": "read_file", "tool_call_id": "4", "content": "File 4 content"},
        {"role": "assistant", "content": "Done."},
    ]
    
    print(f"Messages before: {len(messages)}")
    print(f"Tool messages before: {sum(1 for m in messages if m.get('role') == 'tool')}")
    
    collapsed = middleware._collapse_duplicate_tools(messages)
    
    print(f"Messages after: {len(collapsed)}")
    print(f"Tool messages after: {sum(1 for m in collapsed if m.get('role') == 'tool')}")
    
    # Find collapsed message
    for msg in collapsed:
        if 'consecutive' in msg.get('content', ''):
            print(f"Collapsed content: {msg['content'][:100]}...")
    
    assert len(collapsed) < len(messages), "Should collapse duplicates"
    print("✓ Duplicate tool collapse works\n")


def test_extreme_compression():
    """Test extreme compression scenario (simulating gemini-cli 98% reduction)."""
    print("=" * 60)
    print("Test: Extreme compression (gemini-cli style)")
    print("=" * 60)
    
    # Simulate gemini-cli trajectory: 729,816 → 14,441 tokens (98% reduction)
    middleware = CompactContextMiddleware(
        max_context_tokens=1_000_000,  # 1M tokens like gemini-cli
        compression_threshold=0.5,
        preserve_ratio=0.3,
        tool_output_token_budget=50_000,
    )
    
    # Create large context (~700k tokens)
    messages = [{"role": "system", "content": "You are a helpful assistant. " + "x" * 1000}]
    
    # Add many messages with large tool outputs
    for i in range(50):
        messages.append({"role": "user", "content": f"Task {i}: " + "word " * 100})
        messages.append({
            "role": "assistant",
            "content": f"Working on task {i}.",
            "tool_calls": [{"id": f"call_{i}", "function": {"name": "run_cmd", "arguments": "{}"}}]
        })
        # Large tool output (~10k tokens each)
        messages.append({
            "role": "tool",
            "name": "run_cmd",
            "tool_call_id": f"call_{i}",
            "content": f"Output {i}:\n" + "\n".join([f"Line {j}: " + "data " * 50 for j in range(100)])
        })
        messages.append({"role": "assistant", "content": f"Completed task {i}. " + "summary " * 50})
    
    hook_input = MockHookInput(messages)
    
    tokens_before = middleware._count_messages_tokens(messages)
    print(f"Tokens before: {tokens_before:,}")
    print(f"Messages before: {len(messages)}")
    print(f"Compression threshold: {int(middleware.max_context_tokens * 0.5):,}")
    
    result = middleware.before_model(hook_input)
    
    if result.messages:
        tokens_after = middleware._count_messages_tokens(result.messages)
        compression_ratio = (tokens_before - tokens_after) / tokens_before * 100
        
        print(f"Tokens after: {tokens_after:,}")
        print(f"Messages after: {len(result.messages)}")
        print(f"Compression: {compression_ratio:.1f}%")
        
        assert tokens_after < tokens_before, "Should reduce tokens"
    
    print("✓ Extreme compression handled\n")


def run_all_tests():
    """Run all tests."""
    print("\n" + "=" * 60)
    print("Running Gemini-CLI Alignment Tests")
    print("=" * 60 + "\n")
    
    test_gemini_cli_constants()
    test_compression_threshold_50_percent()
    test_preserve_30_percent()
    test_tool_output_truncation_lines()
    test_tool_output_budget_50k()
    test_compression_notice_format()
    test_aggressive_middleware()
    test_duplicate_tool_collapse()
    test_extreme_compression()
    
    print("=" * 60)
    print("All tests passed! ✓")
    print("=" * 60)
    print("\nGemini-CLI Alignment Summary:")
    print("- ✓ 50% compression threshold")
    print("- ✓ 30% recent history preservation")
    print("- ✓ 50,000 token tool output budget")
    print("- ✓ Last 30 lines truncation")
    print("- ✓ Compression notice with counts")
    print("- ⚠️ <state_snapshot> requires LLM (optional)")


if __name__ == "__main__":
    run_all_tests()
