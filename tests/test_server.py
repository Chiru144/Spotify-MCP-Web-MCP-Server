import pytest
from unittest.mock import patch, MagicMock

import asyncio
import server

def test_all_tools_registered():
    tools = asyncio.run(server.mcp.list_tools())
    registered_names = [t.name for t in tools]
    assert len(registered_names) > 30
