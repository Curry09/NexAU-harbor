#!/bin/bash
# Run all unit tests for NexAU tool implementations

set -e

# Change to the project directory
cd "$(dirname "$0")"

echo "=========================================="
echo "Running NexAU Tool Implementation Tests"
echo "=========================================="
echo ""

# Run all tests with verbose output using uv
echo "Running tests in nexau_harbor/tool_impl/tests/"
echo ""

uv run pytest nexau_harbor/tool_impl/tests/ -v --tb=short

echo ""
echo "=========================================="
echo "All tests completed!"
echo "=========================================="
