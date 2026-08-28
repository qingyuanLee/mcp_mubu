"""mubu-mcp CLI entrypoint.

Usage:
    mubu-mcp                  # stdio transport (default)
    mubu-mcp --transport http # Streamable HTTP
    mubu-mcp --transport sse  # SSE transport
"""

from __future__ import annotations

import argparse
import logging
import sys


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="mubu-mcp",
        description="Mubu (幕布) MCP Server — manage outlines via Model Context Protocol.",
    )
    parser.add_argument(
        "--transport",
        choices=["stdio", "http", "sse"],
        default="stdio",
        help="Transport to use (default: stdio).",
    )
    parser.add_argument(
        "--host",
        default="0.0.0.0",
        help="Host for HTTP/SSE transport (default: 0.0.0.0).",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=3000,
        help="Port for HTTP/SSE transport (default: 3000).",
    )
    parser.add_argument(
        "--cache-backend",
        choices=["sqlite", "redis", "mongo", "cosmos"],
        default=None,
        help="Cache backend (default: sqlite, or MUBU_CACHE_BACKEND env var).",
    )
    parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="Enable debug logging.",
    )
    args = parser.parse_args()

    # Set cache backend override if specified
    if args.cache_backend:
        import os
        os.environ["MUBU_CACHE_BACKEND"] = args.cache_backend

    # Configure logging
    log_level = logging.DEBUG if args.verbose else logging.WARNING
    logging.basicConfig(
        level=log_level,
        format="%(levelname)s: %(message)s",
        stream=sys.stderr,
    )

    # Import server (triggers tool/resource registration)
    from mubu_mcp.server import mcp  # noqa: E402

    if args.transport == "http":
        mcp.run(transport="http", host=args.host, port=args.port)
    elif args.transport == "sse":
        mcp.run(transport="sse", host=args.host, port=args.port)
    else:
        mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
