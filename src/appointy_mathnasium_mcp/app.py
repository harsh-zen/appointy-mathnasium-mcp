import logging

from mcp.server.fastmcp import FastMCP

from .config import (
    MCP_HOST,
    MCP_JSON_RESPONSE,
    MCP_LOG_LEVEL,
    MCP_PORT,
    MCP_SSE_PATH,
    MCP_STATELESS_HTTP,
    MCP_STREAMABLE_HTTP_PATH,
)

logging.basicConfig(level=logging.INFO)

mcp = FastMCP(
    "appointy-mathnasium-mcp",
    host=MCP_HOST,
    port=MCP_PORT,
    streamable_http_path=MCP_STREAMABLE_HTTP_PATH,
    sse_path=MCP_SSE_PATH,
    json_response=MCP_JSON_RESPONSE,
    stateless_http=MCP_STATELESS_HTTP,
    log_level=MCP_LOG_LEVEL,
)
