# Use Python 3.11 slim image for smaller size
FROM python:3.11-slim

# Set working directory
WORKDIR /app

# Install system dependencies if needed
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements file
COPY requirements.txt .

# Install Python dependencies
RUN pip install --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY server.py .
COPY services/ ./services/

# Create a non-root user to run the app
RUN useradd -m -u 1000 mcp && chown -R mcp:mcp /app
USER mcp

# Set environment variables
ENV PYTHONUNBUFFERED=1

# Run the MCP server in stdio mode
CMD ["python", "server.py"]
