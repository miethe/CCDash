"""FastMCP server entry point for CCDash intelligence tools."""
from __future__ import annotations

from contextlib import asynccontextmanager

from mcp.server.fastmcp import FastMCP

from backend.mcp.bootstrap import bootstrap_mcp, shutdown_mcp
from backend.mcp.tools import register_tools


@asynccontextmanager
async def mcp_lifespan(_server: FastMCP):
    await bootstrap_mcp()
    try:
        yield
    finally:
        await shutdown_mcp()


mcp = FastMCP("CCDash Intelligence", lifespan=mcp_lifespan)
register_tools(mcp)


def main() -> None:
    mcp.run()


if __name__ == "__main__":
    main()
