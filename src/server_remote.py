#!/usr/bin/env python3
"""
Todoist MCP Remote Server - exposes HTTP endpoint for remote MCP access
Supports dual-factor path-based authentication
Designed for Azure Container Apps and other cloud platforms with SSL termination
"""

import os
import sys
import logging
import hashlib
import asyncio
from pathlib import Path
from dotenv import load_dotenv
from typing import Optional

# Load environment variables
load_dotenv('.env.local')
load_dotenv('.env')

# Configure logging
logging.basicConfig(
    level=logging.DEBUG if os.getenv('DEBUG', 'false').lower() == 'true' else logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Get API key from environment (optional)
api_key = os.getenv("MCP_API_KEY")
md5_salt = os.getenv("MD5_SALT", "")

if api_key:
    # Use dual-factor path-based authentication if API key is set
    logger.info("MCP_API_KEY is set - using dual-factor path-based authentication")

    from fastapi import FastAPI, Request, HTTPException
    from fastapi.responses import JSONResponse
    from starlette.middleware.base import BaseHTTPMiddleware
    from contextlib import asynccontextmanager
    import uvicorn
    from .server import mcp, get_todoist_service, get_cache_service, initialize_services

    # Get configuration
    port = int(os.getenv("PORT", "8080"))
    host = os.getenv("HOST", "0.0.0.0")

    # Validate API key format (prevent path traversal attacks)
    if not api_key.replace("-", "").replace("_", "").isalnum():
        logger.error("API key contains invalid characters. Use only alphanumeric, dash, and underscore.")
        sys.exit(1)

    if len(api_key) < 16:
        logger.warning("API key is too short. Consider using a longer key for better security.")

    # Calculate MD5 hash of API key with optional salt for additional security layer
    if md5_salt:
        logger.info(f"Using MD5 salt from MD5_SALT environment variable")
        hash_input = f"{md5_salt}{api_key}"
    else:
        logger.warning("No MD5_SALT configured - using unsalted hash")
        hash_input = api_key

    api_key_hash = hashlib.md5(hash_input.encode()).hexdigest()
    logger.info(f"API key hash calculated: {api_key_hash[:8]}... (showing first 8 chars)")

    # Flag to track if services are initialized
    _services_initialized = False

    def ensure_services_initialized():
        """Initialize services on first request (lazy initialization)"""
        global _services_initialized
        if not _services_initialized:
            logger.info("First request received - initializing services...")
            initialize_services()
            _services_initialized = True
            logger.info("Services initialized successfully")

    # Get the MCP HTTP app without a path since we'll mount it at /mcp
    mcp_app = mcp.http_app()

    # Create FastAPI app with security settings and MCP lifespan
    app = FastAPI(
        title="Todoist MCP Remote Server",
        docs_url=None,  # Disable Swagger UI
        redoc_url=None,  # Disable ReDoc
        openapi_url=None,  # Disable OpenAPI schema
        lifespan=mcp_app.lifespan  # REQUIRED: Connect MCP app's lifespan
    )

    # Security middleware to add headers
    class SecurityMiddleware(BaseHTTPMiddleware):
        async def dispatch(self, request: Request, call_next):
            response = await call_next(request)

            # Add security headers
            response.headers["X-Content-Type-Options"] = "nosniff"
            response.headers["X-Frame-Options"] = "DENY"
            response.headers["X-XSS-Protection"] = "1; mode=block"
            response.headers["Referrer-Policy"] = "no-referrer"
            response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, private"
            response.headers["Content-Security-Policy"] = "default-src 'none'"

            # Remove server identification headers if they exist
            if "server" in response.headers:
                del response.headers["server"]
            if "x-powered-by" in response.headers:
                del response.headers["x-powered-by"]

            return response

    # Add security middleware
    app.add_middleware(SecurityMiddleware)

    # Fast health check endpoint (no authentication, no service initialization)
    @app.get("/app/health")
    async def health_check():
        """Fast health check endpoint - does not initialize services"""
        return {
            "status": "healthy",
            "version": "1.0.0",
            "server": "TodoistMCP"
        }

    # Authenticated MCP endpoint with dual-factor path authentication
    # Services are initialized on first authenticated request
    @app.api_route(f"/app/{api_key}/{api_key_hash}/mcp", methods=["GET", "POST", "PUT", "DELETE", "PATCH", "OPTIONS", "HEAD"])
    @app.api_route(f"/app/{api_key}/{api_key_hash}/mcp/{{path:path}}", methods=["GET", "POST", "PUT", "DELETE", "PATCH", "OPTIONS", "HEAD"])
    async def mcp_endpoint(request: Request, path: str = ""):
        """MCP endpoint with lazy service initialization"""
        # Initialize services on first request
        ensure_services_initialized()

        # Forward to MCP app
        # Create a new request with the /mcp path
        scope = request.scope.copy()
        scope["path"] = f"/mcp/{path}" if path else "/mcp"
        scope["root_path"] = ""

        from starlette.requests import Request as StarletteRequest
        modified_request = StarletteRequest(scope, request.receive)

        # Call the MCP app
        return await mcp_app(modified_request.scope, modified_request.receive, request._send)

    # Add a custom 404 handler with anti-brute-force delay
    @app.exception_handler(404)
    async def not_found_handler(request: Request, exc: HTTPException):
        # Add 30-second delay for failed authentication attempts to prevent brute forcing
        # Only delay for /app/ paths that look like authentication attempts
        if request.url.path.startswith("/app/") and request.url.path != "/app/health":
            logger.warning(f"Invalid authentication path attempted: {request.url.path} from {request.client.host if request.client else 'unknown'}")
            await asyncio.sleep(30)

        return JSONResponse(
            status_code=404,
            content={"detail": "Not Found"}
        )

    if __name__ == "__main__":
        # Check configuration
        if not os.getenv('TODOIST_API_TOKEN'):
            logger.warning("Todoist API token not configured. Set TODOIST_API_TOKEN in .env.local or .env")

        # Run HTTP server with authentication
        logger.info("Starting Todoist MCP remote server with dual-factor authentication")
        logger.info(f"MCP endpoint: http://{host}:{port}/app/{api_key}/{api_key_hash}/mcp")
        logger.info(f"Health check: http://{host}:{port}/app/health")
        logger.warning("Keep your API key secret and use HTTPS in production!")
        logger.info("Use scripts/verify_auth.py to calculate the correct endpoint URL")

        # Use uvloop and httptools for performance if available
        uvicorn.run(
            app,
            host=host,
            port=port,
            loop="uvloop",  # Faster event loop
            http="httptools",  # Faster HTTP parser
            log_level="warning",  # Reduce log verbosity
            access_log=False,  # Disable access logs to prevent API key leakage
            server_header=False,  # Don't send server header
            date_header=False  # Don't send date header
        )

else:
    # Use simple unauthenticated mode if no API key is set
    logger.warning("MCP_API_KEY not set - running in UNAUTHENTICATED mode")
    logger.warning("This is not recommended for production use!")

    from .server import mcp, initialize_services

    if __name__ == "__main__":
        # Get configuration
        port = int(os.getenv("PORT", "8080"))
        host = os.getenv("HOST", "0.0.0.0")

        # Check configuration
        if not os.getenv('TODOIST_API_TOKEN'):
            logger.warning("Todoist API token not configured. Set TODOIST_API_TOKEN in .env.local or .env")

        # Initialize services before starting the server
        logger.info("Initializing services...")
        initialize_services()
        logger.info("Services initialized successfully")

        # Run HTTP server without authentication
        logger.info("Starting Todoist MCP remote server (UNAUTHENTICATED)")
        logger.info(f"MCP endpoint: http://{host}:{port}/mcp")
        logger.info("Note: Set MCP_API_KEY environment variable to enable authentication")

        # Start the server with HTTP transport
        mcp.run(transport="http", host=host, port=port)
