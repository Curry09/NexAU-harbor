#!/usr/bin/env python3
"""
Fix JSON-style escape sequences in nexau-gemini-cli-systemprompt.md.
Reads from original (preserved), writes fixed content to a NEW file.
- \\n -> actual newline
- \\u0026 -> &
- \\u003c -> <
- \\u003e -> >
- \\" -> "
"""

import argparse
import re


def decode_unicode_escape(match: re.Match) -> str:
    """Decode \\uXXXX to corresponding Unicode character."""
    return chr(int(match.group(1), 16))


def fix_escapes(content: str) -> str:
    # 1. Replace \\n (double backslash + n) with actual newline
    content = content.replace("\\\\n", "\n")
    # 2. Replace \\uXXXX with actual Unicode chars
    content = re.sub(r"\\u([0-9a-fA-F]{4})", decode_unicode_escape, content)
    # 3. Replace \\" (double backslash + quote) and \" with "
    content = content.replace('\\\\"', '"').replace('\\"', '"')
    # 4. Replace \\t with tab (if any)
    content = content.replace("\\t", "\t")
    # 5. Clean up stray backslashes before newlines (from partial previous fix)
    content = content.replace("\\\n", "\n")
    return content


def main():
    base = __file__.replace("fix_systemprompt_escape.py", "")
    parser = argparse.ArgumentParser(description="Fix JSON-style escapes, keep original intact")
    parser.add_argument("-i", "--input", default=f"{base}nexau-gemini-cli-systemprompt.md", help="Original file (preserved)")
    parser.add_argument("-o", "--output", default=f"{base}nexau-gemini-cli-systemprompt-unescaped.md", help="Output file")
    args = parser.parse_args()
    with open(args.input, "r", encoding="utf-8") as f:
        content = f.read()
    fixed = fix_escapes(content)
    with open(args.output, "w", encoding="utf-8") as f:
        f.write(fixed)
    print(f"Read:  {args.input}")
    print(f"Wrote: {args.output}")


if __name__ == "__main__":
    main()
