#!/usr/bin/env python3
"""
MattasMCP Remote Server - exposes HTTP endpoint for remote MCP access
Supports both authenticated (path-based) and unauthenticated modes
Designed for Azure Container Apps which handles SSL termination
"""

import os
import sys
import logging
from pathlib import Path
from dotenv import load_dotenv

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

if api_key:
    # Use path-based authentication if API key is set
    logger.info("MCP_API_KEY is set - using path-based authentication")
    
    from fastapi import FastAPI, Request, HTTPException, Response
    from fastapi.responses import JSONResponse, PlainTextResponse
    from fastapi.middleware.cors import CORSMiddleware
    from starlette.middleware.base import BaseHTTPMiddleware
    from contextlib import asynccontextmanager
    import uvicorn
    from server import mcp, get_ical_service, get_todoist_service, get_ha_service, initialize_services
    
    # Get configuration
    port = int(os.getenv("PORT", "8000"))
    host = os.getenv("HOST", "0.0.0.0")
    
    # Check configuration
    if not os.getenv('ICAL_FEED_CONFIGS'):
        logger.warning("No iCalendar feeds configured")
    
    if not os.getenv('TODOIST_API_TOKEN'):
        logger.warning("Todoist API token not configured")
    
    if not os.getenv('HA_URL') or not os.getenv('HA_TOKEN'):
        logger.warning("Home Assistant not configured")
    
    # Validate API key format (prevent path traversal attacks)
    if not api_key.replace("-", "").replace("_", "").isalnum():
        logger.error("API key contains invalid characters. Use only alphanumeric, dash, and underscore.")
        sys.exit(1)
    
    if len(api_key) < 16:
        logger.warning("API key is too short. Consider using a longer key for better security.")
    
    # Initialize services BEFORE creating the MCP HTTP app
    logger.info("Initializing services for authenticated mode...")
    initialize_services()
    logger.info("Services initialized successfully")
    
    # Get the MCP HTTP app without a path since we'll mount it at /mcp
    mcp_app = mcp.http_app()
    
    # Create FastAPI app with security settings and MCP lifespan
    app = FastAPI(
        title="MattasMCP Remote Server",
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
            
            # Remove server identification headers if they exist
            if "server" in response.headers:
                del response.headers["server"]
            if "x-powered-by" in response.headers:
                del response.headers["x-powered-by"]
            
            return response
    
    # Add security middleware
    app.add_middleware(SecurityMiddleware)
    
    # Create a simple health check app
    health_app = FastAPI(
        docs_url=None,
        redoc_url=None,
        openapi_url=None
    )
    
    @health_app.get("/")
    async def health_check():
        """Health check endpoint"""
        services = {
            "ical": get_ical_service() is not None,
            "todoist": get_todoist_service() is not None,
            "homeassistant": get_ha_service() is not None
        }
        
        return {
            "status": "healthy",
            "services": services,
            "authenticated": True,
            "version": "2.0.0"
        }
    
    # Create an info app for the root path
    info_app = FastAPI(
        docs_url=None,
        redoc_url=None,
        openapi_url=None
    )
    
    @info_app.get("/")
    async def server_info(request: Request):
        """Server information endpoint"""
        # Get the tools that are available (all are tools now, Claude can't use resources)
        tools = []
        
        if get_ical_service():
            # All converted to tools (Claude can't use resources)
            tools.extend(["add_calendar_feed", "remove_calendar_feed", "refresh_calendar_feeds",
                         "get_events_on_date", "get_events_between_dates", "get_events_after_date",
                         "search_calendar_events",
                         "get_calendar_info", "get_today_events", "get_upcoming_events",
                         "get_calendar_feeds", "get_week_events", "get_month_events",
                         "get_tomorrow_events", "get_calendar_conflicts"])
            
        if get_todoist_service():
            # All converted to tools (Claude can't use resources)
            tools.extend(["create_todoist_task", "update_todoist_task", 
                         "complete_todoist_task", "reopen_todoist_task", "delete_todoist_task",
                         "create_todoist_project", "create_todoist_label",
                         "get_tasks_by_project", "get_tasks_by_label", "get_tasks_by_priority",
                         "get_tasks_by_filter", "get_project_details",
                         "get_todoist_projects", "get_todoist_labels", "get_todoist_tasks_today",
                         "get_todoist_tasks_overdue", "get_todoist_inbox_tasks",
                         "get_todoist_all_due_today", "get_todoist_week_tasks",
                         "get_todoist_high_priority_tasks", "get_todoist_no_date_tasks",
                         "get_todoist_stats", "get_todoist_priorities", "get_todoist_colors",
                         "get_todoist_filters"])
            
        if get_ha_service():
            # All converted to tools (Claude can't use resources)
            tools.extend(["turn_on_device", "turn_off_device", "toggle_device", 
                         "set_climate_control", "control_cover", "control_lock",
                         "activate_scene", "run_script", "trigger_automation",
                         "control_media_player", "control_area_devices", "send_notification",
                         "call_home_assistant_service",
                         "get_states_by_domain", "get_states_by_area", "get_entity_state",
                         "get_entity_history", "get_sensors_by_type",
                         "get_ha_states", "get_ha_areas", "get_ha_devices",
                         "get_ha_entities", "get_ha_services", "get_ha_scenes",
                         "get_ha_automations", "get_ha_scripts", "get_ha_unavailable_entities",
                         "get_ha_lights_on", "get_ha_devices_on", "get_ha_temperature_sensors",
                         "get_ha_motion_sensors", "get_ha_door_window_sensors",
                         "get_ha_security_status", "get_ha_climate_status", "get_ha_battery_status",
                         "get_ha_domains", "get_ha_device_classes", "get_ha_service_names"])
        
        # Always available server tools
        tools.extend(["get_server_status", "get_server_config"])
        
        # Get host from request headers for proper URL construction
        host_header = request.headers.get("host", f"{host}:{port}")
        scheme = "https" if request.headers.get("x-forwarded-proto") == "https" else "http"
        
        return {
            "name": "MattasMCP Remote Server (Refactored)",
            "version": "2.0.0",
            "protocol": scheme,
            "mcp_endpoint": f"{scheme}://{host_header}/{api_key}/mcp",
            "health_endpoint": f"{scheme}://{host_header}/{api_key}/health/",
            "authentication": "path-based",
            "tools_available": len(tools),
            "tools": tools,
            "prompts_available": 19,  # We have 19 prompts registered
            "note": "All resources converted to tools as Claude cannot use MCP resources",
            "services": {
                "ical": {
                    "enabled": get_ical_service() is not None,
                    "feeds": len(get_ical_service().feeds) if get_ical_service() else 0
                },
                "todoist": {
                    "enabled": get_todoist_service() is not None
                },
                "homeassistant": {
                    "enabled": get_ha_service() is not None
                }
            }
        }
    
    # Mount apps in order - more specific paths first
    app.mount(f"/{api_key}/health", health_app)
    app.mount(f"/{api_key}/info", info_app)
    # Mount the MCP app at /{api_key} - it will handle /mcp internally
    app.mount(f"/{api_key}", mcp_app)
    
    # Add a custom 404 handler instead of catch-all route
    @app.exception_handler(404)
    async def not_found_handler(request: Request, exc: HTTPException):
        logger.warning("Access attempt to undefined route")
        return JSONResponse(
            status_code=404,
            content={"detail": "Not Found"}
        )
    
    if __name__ == "__main__":
        # Run HTTP server with authentication
        logger.info("Starting MattasMCP remote server with path-based authentication")
        logger.info(f"MCP endpoint: http://{host}:{port}/{api_key}/mcp")
        logger.info(f"Health check: http://{host}:{port}/{api_key}/health")
        logger.info(f"Server info: http://{host}:{port}/{api_key}/info")
        logger.warning("Keep your API key secret and use HTTPS in production!")
        
        uvicorn.run(
            app,
            host=host,
            port=port,
            log_level="warning",  # Reduce log verbosity
            access_log=False,  # Disable access logs to prevent API key leakage
            server_header=False,  # Don't send server header
            date_header=False  # Don't send date header
        )

else:
    # Use simple unauthenticated mode if no API key is set
    logger.warning("MCP_API_KEY not set - running in UNAUTHENTICATED mode")
    logger.warning("This is not recommended for production use!")
    
    from server import mcp, get_ical_service, get_todoist_service, get_ha_service, initialize_services
    
    if __name__ == "__main__":
        # Get configuration
        port = int(os.getenv("PORT", "8000"))
        host = os.getenv("HOST", "0.0.0.0")
        
        # Check configuration
        if not os.getenv('ICAL_FEED_CONFIGS'):
            logger.warning("No iCalendar feeds configured")
        
        if not os.getenv('TODOIST_API_TOKEN'):
            logger.warning("Todoist API token not configured")
        
        if not os.getenv('HA_URL') or not os.getenv('HA_TOKEN'):
            logger.warning("Home Assistant not configured")
        
        # Initialize services before starting the server
        logger.info("Initializing services...")
        initialize_services()
        logger.info("Services initialized successfully")
        
        # Run HTTP server without authentication
        logger.info("Starting MattasMCP remote server (UNAUTHENTICATED)")
        logger.info(f"MCP endpoint: http://{host}:{port}/mcp")
        logger.info("Note: Set MCP_API_KEY environment variable to enable authentication")
        
        # Start the server with HTTP transport
        mcp.run(transport="http", host=host, port=port)