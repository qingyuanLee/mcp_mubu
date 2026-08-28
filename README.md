# mubu-mcp

**Mubu (幕布) MCP Server** — manage your Mubu outlines via [Model Context Protocol](https://modelcontextprotocol.io/) with pluggable caching.

Built on the [mubu-integration](https://github.com/liuboacean/mubu-integration) API client and the official [MCP Python SDK v2](https://github.com/modelcontextprotocol/python-sdk) (2026-07-28 spec).

## ✨ Features

- **Full Mubu API**: list, create, read, save, delete, move, rename documents and folders
- **Round-trip Markdown**: lossless Markdown import/export (headings, checkboxes, notes)
- **OPML & FreeMind export**: for XMind, Freeplane, and other outliners
- **Content search**: search by name and inside document bodies
- **Folder tree export**: recursively export entire folder structures
- **Pluggable cache**: SQLite built-in; optional Redis, MongoDB, CosmosDB adapters
- **MCP standard**: tools, resources, and prompts — works with Claude, Cursor, and any MCP host

## 🚀 Quick Start

### Install

```bash
# From source
pip install -e .

# With optional cache backends
pip install -e ".[all]"
```

### Set credentials

```bash
export MUBU_PHONE="your-phone"
export MUBU_PASSWORD="your-password"
# Optional: needed for save operations
export MUBU_MEMBER_ID="your-member-id"
```

Or write them to `~/.workbuddy/.env.mubu`:

```
MUBU_PHONE=your-phone
MUBU_PASSWORD=your-password
MUBU_MEMBER_ID=your-member-id
```

### Run

```bash
# stdio (default — for MCP hosts like Claude Desktop)
mubu-mcp

# Streamable HTTP (for remote access)
mubu-mcp --transport http --port 3000

# With debug logging
mubu-mcp -v
```

## 🗄️ Cache Backends

mubu-mcp uses a cache to store auth tokens, user info, and document snapshots. SQLite is built-in and requires zero configuration.

| Backend | Install | Env vars |
|---------|---------|----------|
| **SQLite** (default) | *(built-in)* | `MUBU_CACHE_BACKEND=sqlite` |
| **Redis** | `pip install "mubu-mcp[redis]"` | `MUBU_REDIS_URL`, `MUBU_CACHE_BACKEND=redis` |
| **MongoDB** | `pip install "mubu-mcp[mongo]"` | `MUBU_MONGO_URI`, `MUBU_MONGO_DB`, `MUBU_MONGO_COLLECTION` |
| **CosmosDB** | `pip install "mubu-mcp[cosmos]"` | `MUBU_COSMOS_ENDPOINT`, `MUBU_COSMOS_KEY`, `MUBU_COSMOS_DB`, `MUBU_COSMOS_CONTAINER` |

### Adding a custom cache backend

Implement the `CacheBackend` abstract class from `mubu_mcp.cache.base`:

```python
from mubu_mcp.cache.base import CacheBackend

class MyCache(CacheBackend):
    def get(self, key: str) -> dict | None: ...
    def set(self, key: str, value, ttl: float | None = None) -> None: ...
    def delete(self, key: str) -> bool: ...
    def exists(self, key: str) -> bool: ...
    def clear(self, prefix: str = "") -> int: ...
```

## 🔧 MCP Tools

| Tool | Description |
|------|-------------|
| `mubu_login` | Authenticate with Mubu |
| `mubu_whoami` | Show current auth status |
| `mubu_list` | List folder contents |
| `mubu_create_folder` | Create a folder |
| `mubu_create_doc` | Create an empty document |
| `mubu_create_doc_from_markdown` | Create a document from Markdown |
| `mubu_get_doc` | Get document content (Markdown or JSON) |
| `mubu_save_doc_markdown` | Update a document from Markdown |
| `mubu_move` | Move item to another folder |
| `mubu_rename` | Rename a document or folder |
| `mubu_delete` | Delete a document or folder |
| `mubu_search` | Search by name (optionally with content search) |
| `mubu_export_opml` | Export as OPML 2.0 |
| `mubu_export_freeplane` | Export as FreeMind XML |
| `mubu_export_markdown` | Export as Markdown |
| `mubu_import_markdown` | Parse Markdown to Mubu JSON (dry run) |
| `mubu_export_tree` | Export entire folder tree |
| `mubu_cache_info` | Show cache backend info |
| `mubu_cache_clear` | Clear cached data |

### MCP Resources

| Resource | Description |
|----------|-------------|
| `mubu://status` | Auth and cache status |
| `mubu://doc/{doc_id}` | Fetch a document by ID |

### MCP Prompts

| Prompt | Description |
|--------|-------------|
| `mubu_setup_guide` | Step-by-step configuration guide |
| `mubu_work_with_doc` | Load a document for editing |
| `mubu_sync_markdown` | Import Markdown into Mubu |

## 📦 MCP Host Configuration

### Claude Desktop

Add to your `claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "mubu": {
      "command": "mubu-mcp",
      "env": {
        "MUBU_PHONE": "your-phone",
        "MUBU_PASSWORD": "your-password"
      }
    }
  }
}
```

### Cursor / VS Code

```json
{
  "mcp": {
    "servers": {
      "mubu": {
        "command": "mubu-mcp",
        "env": {
          "MUBU_PHONE": "your-phone",
          "MUBU_PASSWORD": "your-password"
        }
      }
    }
  }
}
```

### HTTP transport (remote server)

```json
{
  "mcp": {
    "servers": {
      "mubu": {
        "url": "http://localhost:3000/mcp"
      }
    }
  }
}
```

## 🏗️ Project Structure

```
mubu-mcp/
├── pyproject.toml
├── README.md
└── src/
    └── mubu_mcp/
        ├── __init__.py          # Package version
        ├── __main__.py          # CLI entrypoint
        ├── server.py            # MCP server (tools, resources, prompts)
        ├── mubu_client.py       # Mubu API client with cache integration
        ├── mubu_config.py       # Config, constants, error types
        ├── mubu_convert.py      # Markdown / OPML / FreeMind conversion
        └── cache/
            ├── __init__.py      # Cache factory
            ├── base.py          # CacheBackend ABC
            ├── sqlite_cache.py  # Built-in SQLite backend
            ├── redis_cache.py   # Redis adapter (optional)
            ├── mongo_cache.py   # MongoDB adapter (optional)
            └── cosmos_cache.py  # CosmosDB adapter (optional)
```

## ⚠️ Known Limitations

- Image and attachment nodes are not supported in Markdown round-trip
- Ordered lists (`1.`) are not part of the current conversion
- `save` operations require `MUBU_MEMBER_ID` (cannot be auto-detected from any API)
- This is an unofficial integration using the same endpoints as the Mubu web app

## 📄 License

MIT
