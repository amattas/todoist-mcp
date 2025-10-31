#!/bin/bash
# Run tests with coverage reporting

set -e

echo "Running Todoist MCP tests..."
python -m pytest tests/ -v --cov=src/services --cov-report=term-missing

echo ""
echo "✓ Tests completed successfully"
