"""
Merge redundant entries in NexAU in_memory_tracer data.

In an agent loop without context compression, each successive LLM call's input
messages are a strict superset of the previous call's (the earlier messages
appear as an exact prefix).  This module detects such cases and removes the
redundant entries.
"""

import json


def _msg_key(msg):
    return json.dumps(msg, sort_keys=True, ensure_ascii=False)


def _is_prefix(shorter, longer):
    """Return True if *shorter* is a strict element-wise prefix of *longer*."""
    if not isinstance(shorter, list) or not isinstance(longer, list):
        return False
    if len(shorter) >= len(longer):
        return False
    return all(_msg_key(shorter[i]) == _msg_key(longer[i])
               for i in range(len(shorter)))


def _merge_children(children):
    """Remove LLM entries whose input is a strict prefix of the next LLM entry's
    input, along with intermediate TOOL entries already captured in the surviving
    LLM's input."""
    llm_indices = [i for i, c in enumerate(children) if c.get("type") == "LLM"]
    if len(llm_indices) <= 1:
        return children

    remove = set()
    for k in range(len(llm_indices) - 1):
        cur = llm_indices[k]
        nxt = llm_indices[k + 1]
        cur_input = children[cur].get("inputs", {}).get("input", [])
        nxt_input = children[nxt].get("inputs", {}).get("input", [])
        if _is_prefix(cur_input, nxt_input):
            remove.add(cur)
            for j in range(cur + 1, nxt):
                remove.add(j)

    return [c for i, c in enumerate(children) if i not in remove]


def merge_tracer_data(data):
    """Recursively merge redundant LLM/TOOL spans in tracer data (in-place).

    Returns the (mutated) *data* for convenience.
    """
    def _walk(entries):
        for entry in entries:
            if "children" in entry and isinstance(entry["children"], list):
                entry["children"] = _merge_children(entry["children"])
                _walk(entry["children"])

    if isinstance(data, list):
        _walk(data)
    elif isinstance(data, dict) and "children" in data:
        _walk([data])
    return data
