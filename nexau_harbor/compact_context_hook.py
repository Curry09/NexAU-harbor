"""
Context compaction middleware for NexAU.

Implements gemini-cli style context compression:
- Triggers at configurable token threshold (default: 50% of max context)
- Preserves recent history (default: 30%)
- Truncates tool outputs to budget (default: 50,000 tokens)
- Optionally generates <state_snapshot> via LLM summarization
"""

from typing import Any, Callable, Optional
from nexau.archs.main_sub.execution.hooks import HookResult, Middleware


def default_token_counter(text: str) -> int:
    """
    Simple token estimation: ~4 characters per token for English.
    Override with actual tokenizer for more accuracy.
    """
    if not text:
        return 0
    return len(text) // 4


# Gemini-CLI style constants
DEFAULT_COMPRESSION_TOKEN_THRESHOLD = 0.5  # Trigger at 50% of max context
COMPRESSION_PRESERVE_THRESHOLD = 0.3       # Preserve newest 30%
COMPRESSION_FUNCTION_RESPONSE_TOKEN_BUDGET = 50_000  # Tool output budget
COMPRESSION_TRUNCATE_LINES = 30            # Truncate to last 30 lines


class CompactContextMiddleware(Middleware):
    """
    Middleware that compacts conversation context using gemini-cli style compression.
    
    Compression flow (matches gemini-cli chatCompressionService.ts):
    1. Check if token count exceeds threshold (default: 50% of max_context_tokens)
    2. Truncate tool outputs to budget
    3. Optionally generate <state_snapshot> via LLM
    4. Preserve newest 30% of history
    5. Return compressed history
    
    Configuration:
    - max_context_tokens: Maximum tokens for context window (default: 200000)
    - compression_threshold: Trigger compression at this ratio (default: 0.5)
    - preserve_ratio: Preserve this ratio of recent history (default: 0.3)
    - tool_output_token_budget: Max tokens for each tool output (default: 50000)
    - truncate_lines: Truncate tool output to last N lines (default: 30)
    - token_counter: Custom function to count tokens
    - enable_state_snapshot: Whether to generate LLM summary (default: False)
    - state_snapshot_generator: Async function to generate state snapshot
    """
    
    def __init__(
        self,
        max_context_tokens: int = 200000,
        compression_threshold: float = DEFAULT_COMPRESSION_TOKEN_THRESHOLD,
        preserve_ratio: float = COMPRESSION_PRESERVE_THRESHOLD,
        tool_output_token_budget: int = COMPRESSION_FUNCTION_RESPONSE_TOKEN_BUDGET,
        truncate_lines: int = COMPRESSION_TRUNCATE_LINES,
        token_counter: Optional[Callable[[str], int]] = None,
        enable_state_snapshot: bool = False,
        state_snapshot_generator: Optional[Callable[[list[dict]], str]] = None,
    ):
        self.max_context_tokens = max_context_tokens
        self.compression_threshold = compression_threshold
        self.preserve_ratio = preserve_ratio
        self.tool_output_token_budget = tool_output_token_budget
        self.truncate_lines = truncate_lines
        self.token_counter = token_counter or default_token_counter
        self.enable_state_snapshot = enable_state_snapshot
        self.state_snapshot_generator = state_snapshot_generator
        self.compaction_count = 0
    
    def _count_message_tokens(self, msg: dict[str, Any]) -> int:
        """Count tokens in a single message."""
        total = 0
        
        # Count content
        content = msg.get('content', '')
        if isinstance(content, str):
            total += self.token_counter(content)
        elif isinstance(content, list):
            for part in content:
                if isinstance(part, dict) and 'text' in part:
                    total += self.token_counter(part['text'])
                elif isinstance(part, str):
                    total += self.token_counter(part)
        
        # Overhead for role, name, etc. (~10 tokens)
        total += 10
        
        # Count tool_calls if present
        tool_calls = msg.get('tool_calls', [])
        for tc in tool_calls:
            if isinstance(tc, dict):
                func = tc.get('function', {})
                total += self.token_counter(func.get('name', ''))
                total += self.token_counter(func.get('arguments', ''))
        
        return total
    
    def _count_messages_tokens(self, messages: list[dict[str, Any]]) -> int:
        """Count total tokens in message list."""
        return sum(self._count_message_tokens(msg) for msg in messages)
    
    def before_model(self, hook_input) -> HookResult:
        """
        Compact context before sending to LLM if token count exceeds threshold.
        
        Matches gemini-cli compression flow:
        1. Check if tokenCount < threshold * 0.5 → return unchanged
        2. Truncate tool outputs
        3. Generate state snapshot (if enabled)
        4. Preserve recent history
        """
        messages = hook_input.messages
        
        if not messages:
            return HookResult.no_changes()
        
        total_tokens = self._count_messages_tokens(messages)
        threshold_tokens = int(self.max_context_tokens * self.compression_threshold)
        
        # Check if compression needed (gemini-cli style)
        if total_tokens < threshold_tokens:
            return HookResult.no_changes()
        
        compacted = self._compress_history(messages, total_tokens)
        
        if compacted != messages:
            self.compaction_count += 1
            new_tokens = self._count_messages_tokens(compacted)
            
            # Store compaction info in agent state
            if hasattr(hook_input, 'agent_state') and hook_input.agent_state:
                storage = getattr(hook_input.agent_state.context, 'storage', None)
                if storage is not None:
                    storage['compact_context_count'] = self.compaction_count
                    storage['compact_context_tokens_before'] = total_tokens
                    storage['compact_context_tokens_after'] = new_tokens
                    storage['compact_context_compression_ratio'] = total_tokens / max(new_tokens, 1)
            
            return HookResult.with_modifications(messages=compacted)
        
        return HookResult.no_changes()
    
    def _compress_history(
        self, 
        messages: list[dict[str, Any]], 
        total_tokens: int
    ) -> list[dict[str, Any]]:
        """
        Compress history following gemini-cli flow:
        1. Truncate tool outputs
        2. Generate state snapshot (optional)
        3. Preserve recent history
        """
        # Separate system messages
        system_messages = []
        conversation = []
        
        for msg in messages:
            if msg.get('role') == 'system':
                system_messages.append(msg)
            else:
                conversation.append(msg)
        
        # Step 1: Truncate tool outputs
        truncated_conversation = self._truncate_tool_outputs(conversation)
        
        # Step 2: Calculate preserve count (30% of conversation by token)
        conv_tokens = self._count_messages_tokens(truncated_conversation)
        preserve_tokens = int(conv_tokens * self.preserve_ratio)
        
        # Preserve newest messages up to preserve_tokens
        preserved = []
        preserved_tokens = 0
        
        for msg in reversed(truncated_conversation):
            msg_tokens = self._count_message_tokens(msg)
            if preserved_tokens + msg_tokens <= preserve_tokens:
                preserved.insert(0, msg)
                preserved_tokens += msg_tokens
            else:
                break
        
        # Step 3: Generate state snapshot (if enabled)
        removed_count = len(truncated_conversation) - len(preserved)
        removed_tokens = conv_tokens - preserved_tokens
        
        if self.enable_state_snapshot and self.state_snapshot_generator:
            # Get messages that will be removed for summarization
            removed_messages = truncated_conversation[:len(truncated_conversation) - len(preserved)]
            try:
                snapshot_content = self.state_snapshot_generator(removed_messages)
                state_snapshot = {
                    'role': 'system',
                    'content': snapshot_content
                }
                return system_messages + [state_snapshot] + preserved
            except Exception:
                # Fall back to simple compaction notice
                pass
        
        # Fallback: Add compaction notice
        compaction_notice = {
            'role': 'system',
            'content': f'[Context compacted: {removed_count} messages (~{removed_tokens} tokens) removed. Preserved newest {len(preserved)} messages.]'
        }
        
        return system_messages + [compaction_notice] + preserved
    
    def _truncate_tool_outputs(self, messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """
        Truncate tool outputs to budget.
        
        Gemini-CLI style: truncate to last N lines (default: 30)
        """
        result = []
        
        for msg in messages:
            if msg.get('role') == 'tool' or msg.get('role') == 'function':
                content = msg.get('content', '')
                if isinstance(content, str):
                    content_tokens = self.token_counter(content)
                    
                    if content_tokens > self.tool_output_token_budget:
                        # Truncate to last N lines (gemini-cli style)
                        lines = content.split('\n')
                        if len(lines) > self.truncate_lines:
                            truncated_lines = lines[-self.truncate_lines:]
                            original_line_count = len(lines)
                            truncated_content = '\n'.join(truncated_lines)
                            truncated_content = f'[... {original_line_count - self.truncate_lines} lines truncated ...]\n' + truncated_content
                            msg = {**msg, 'content': truncated_content}
                        else:
                            # If few lines but many tokens, truncate by chars
                            max_chars = self.tool_output_token_budget * 4
                            truncated_content = content[-max_chars:]
                            truncated_content = f'[... truncated to last ~{self.tool_output_token_budget} tokens ...]\n' + truncated_content
                            msg = {**msg, 'content': truncated_content}
            
            result.append(msg)
        
        return result
    
    def after_agent(self, hook_input) -> HookResult:
        """Log compaction statistics at the end of agent run."""
        return HookResult.no_changes()


class StateSnapshotCompactMiddleware(CompactContextMiddleware):
    """
    Extended middleware that generates <state_snapshot> XML structure.
    
    Requires an LLM client to generate summaries. The state snapshot
    follows gemini-cli's format with structured sections.
    """
    
    STATE_SNAPSHOT_PROMPT = """Based on the following conversation history that is being compressed, generate a structured state snapshot in XML format.

The snapshot should capture:
1. overall_goal: The user's high-level objective
2. active_constraints: Technical constraints and requirements discovered
3. key_knowledge: Important findings and technical knowledge
4. artifact_trail: Files created/modified and why
5. file_system_state: Current working directory and relevant files
6. recent_actions: Summary of recent operations
7. task_state: Progress on tasks (COMPLETED/IN_PROGRESS/PENDING)

Format:
<state_snapshot>
    <overall_goal>...</overall_goal>
    <active_constraints>...</active_constraints>
    <key_knowledge>...</key_knowledge>
    <artifact_trail>...</artifact_trail>
    <file_system_state>...</file_system_state>
    <recent_actions>...</recent_actions>
    <task_state>...</task_state>
</state_snapshot>

Conversation history to summarize:
{history}

Generate the state snapshot:"""

    def __init__(
        self,
        llm_client: Any = None,
        llm_model: str = "gpt-4",
        **kwargs
    ):
        # Create state snapshot generator using LLM
        def generate_snapshot(messages: list[dict]) -> str:
            if not llm_client:
                raise ValueError("LLM client required for state snapshot generation")
            
            # Format messages for prompt
            history_text = self._format_messages_for_summary(messages)
            prompt = self.STATE_SNAPSHOT_PROMPT.format(history=history_text)
            
            # Call LLM (assuming OpenAI-compatible client)
            response = llm_client.chat.completions.create(
                model=llm_model,
                messages=[{"role": "user", "content": prompt}],
                max_tokens=2000,
            )
            return response.choices[0].message.content
        
        super().__init__(
            enable_state_snapshot=True,
            state_snapshot_generator=generate_snapshot,
            **kwargs
        )
        self.llm_client = llm_client
        self.llm_model = llm_model
    
    def _format_messages_for_summary(self, messages: list[dict]) -> str:
        """Format messages into text for LLM summarization."""
        parts = []
        for msg in messages:
            role = msg.get('role', 'unknown')
            content = msg.get('content', '')
            if isinstance(content, str) and content:
                # Truncate very long content
                if len(content) > 500:
                    content = content[:500] + '...'
                parts.append(f"[{role}]: {content}")
        return '\n\n'.join(parts)


class AggressiveCompactContextMiddleware(CompactContextMiddleware):
    """
    More aggressive context compaction for smaller context windows.
    
    Uses tighter thresholds and additional strategies:
    - Lower compression threshold (30%)
    - Smaller preserve ratio (20%)
    - Smaller tool output budget (10,000 tokens)
    - Collapses consecutive duplicate tool calls
    """
    
    def __init__(
        self,
        max_context_tokens: int = 100000,
        compression_threshold: float = 0.3,
        preserve_ratio: float = 0.2,
        tool_output_token_budget: int = 10000,
        truncate_lines: int = 20,
        collapse_duplicate_tools: bool = True,
        **kwargs
    ):
        super().__init__(
            max_context_tokens=max_context_tokens,
            compression_threshold=compression_threshold,
            preserve_ratio=preserve_ratio,
            tool_output_token_budget=tool_output_token_budget,
            truncate_lines=truncate_lines,
            **kwargs
        )
        self.collapse_duplicate_tools = collapse_duplicate_tools
    
    def _compress_history(
        self, 
        messages: list[dict[str, Any]], 
        total_tokens: int
    ) -> list[dict[str, Any]]:
        """Apply aggressive compaction with duplicate tool collapsing."""
        # First collapse duplicate tools
        if self.collapse_duplicate_tools:
            messages = self._collapse_duplicate_tools(messages)
        
        # Then apply base compression
        return super()._compress_history(messages, total_tokens)
    
    def _collapse_duplicate_tools(self, messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """
        Collapse consecutive duplicate tool calls of the same type.
        """
        result = []
        i = 0
        
        while i < len(messages):
            msg = messages[i]
            
            if msg.get('role') == 'tool':
                tool_name = msg.get('name', '')
                
                # Look ahead for consecutive same-tool results
                consecutive = [msg]
                j = i + 1
                while j < len(messages):
                    next_msg = messages[j]
                    if next_msg.get('role') == 'tool' and next_msg.get('name') == tool_name:
                        consecutive.append(next_msg)
                        j += 1
                    else:
                        break
                
                if len(consecutive) > 2:
                    # Collapse into summary
                    first_preview = self._get_content_preview(consecutive[0].get('content', ''))
                    last_preview = self._get_content_preview(consecutive[-1].get('content', ''))
                    
                    summary_content = f"[{len(consecutive)} consecutive {tool_name} calls collapsed]\n"
                    summary_content += f"First: {first_preview}\n"
                    summary_content += f"Last: {last_preview}"
                    
                    result.append({
                        'role': 'tool',
                        'name': tool_name,
                        'content': summary_content,
                        'tool_call_id': consecutive[-1].get('tool_call_id', ''),
                    })
                    i = j
                    continue
            
            result.append(msg)
            i += 1
        
        return result
    
    def _get_content_preview(self, content: str, max_chars: int = 200) -> str:
        """Get a preview of content."""
        if not isinstance(content, str):
            content = str(content)
        if len(content) <= max_chars:
            return content
        return content[:max_chars] + '...'
