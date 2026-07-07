import argparse
import logging

from starlette.requests import Request
from starlette.responses import JSONResponse

from .app import mcp
from .config import (
    DEFAULT_TRANSPORT,
    MCP_HOST,
    MCP_JSON_RESPONSE,
    MCP_LOG_LEVEL,
    MCP_PORT,
    MCP_SSE_PATH,
    MCP_STATELESS_HTTP,
    MCP_STREAMABLE_HTTP_PATH,
    TransportType,
)
from . import tools as _tools  # noqa: F401 - importing registers MCP tools


@mcp.custom_route("/health", methods=["GET"], include_in_schema=False)
async def health_check(_: Request) -> JSONResponse:
    return JSONResponse(
        {
            "status": "ok",
            "service": "appointy-mathnasium-mcp",
            "transport": "mcp",
        }
    )


def _build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Appointy Mathnasium MCP server")
    parser.add_argument(
        "--transport",
        default=DEFAULT_TRANSPORT,
        choices=["stdio", "sse", "streamable-http", "http"],
        help="Transport to run (http is an alias for streamable-http).",
    )
    parser.add_argument("--host", default=MCP_HOST, help="Host for HTTP/SSE transports.")
    parser.add_argument("--port", type=int, default=MCP_PORT, help="Port for HTTP/SSE transports.")
    parser.add_argument(
        "--streamable-http-path",
        default=MCP_STREAMABLE_HTTP_PATH,
        help="Path for streamable HTTP endpoint.",
    )
    parser.add_argument(
        "--sse-path",
        default=MCP_SSE_PATH,
        help="Path for SSE endpoint.",
    )
    parser.add_argument(
        "--json-response",
        action="store_true",
        default=MCP_JSON_RESPONSE,
        help="Enable JSON responses for streamable HTTP transport.",
    )
    parser.add_argument(
        "--stateless-http",
        action="store_true",
        default=MCP_STATELESS_HTTP,
        help="Enable stateless streamable HTTP mode for horizontal scalability.",
    )
    parser.add_argument(
        "--log-level",
        default=MCP_LOG_LEVEL,
        choices=["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"],
        help="Logging level.",
    )
    return parser


def main() -> None:
    parser = _build_arg_parser()
    args = parser.parse_args()
    transport: TransportType = "streamable-http" if args.transport == "http" else args.transport

    mcp.settings.host = args.host
    mcp.settings.port = args.port
    mcp.settings.streamable_http_path = args.streamable_http_path
    mcp.settings.sse_path = args.sse_path
    mcp.settings.json_response = args.json_response
    mcp.settings.stateless_http = args.stateless_http
    mcp.settings.log_level = args.log_level

    logging.info(
        "Starting Appointy Mathnasium MCP server transport=%s host=%s port=%s",
        transport,
        args.host,
        args.port,
    )
    if transport == "streamable-http":
        logging.info("Streamable HTTP endpoint: http://%s:%s%s", args.host, args.port, args.streamable_http_path)
    elif transport == "sse":
        logging.info("SSE endpoint: http://%s:%s%s", args.host, args.port, args.sse_path)

    mcp.run(transport=transport)


if __name__ == "__main__":
    main()
