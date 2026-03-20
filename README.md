# WhatsApp MCP Server

A Model Context Protocol (MCP) server for WhatsApp. Search and read your personal WhatsApp messages (including images, videos, documents, and audio), search contacts, and send messages to individuals or groups.

Connects to your **personal WhatsApp account** via the WhatsApp Web multidevice API using [whatsmeow](https://github.com/tulir/whatsmeow). All messages are stored locally in SQLite and only sent to an LLM when tools are invoked.

![WhatsApp MCP](./example-use.png)

> *Caution:* as with many MCP servers, this project is subject to [the lethal trifecta](https://simonwillison.net/2025/Jun/16/the-lethal-trifecta/). Prompt injection could lead to private data exfiltration.

---

## Installation

Two ways to run the Go bridge: **Docker/Podman** (recommended — no Go required on host) or **local Go**.

---

### Option A — Docker / Podman (recommended)

**Prerequisites**
- Docker or Podman with Compose
- Python 3.11+
- `uv` — `curl -LsSf https://astral.sh/uv/install.sh | sh`

**1. Clone the repo**

```bash
git clone https://github.com/pesnik/whatsapp-mcp.git
cd whatsapp-mcp
```

**2. First run — scan the QR code**

The bridge needs an interactive terminal on the very first run to display the QR code.

```bash
# Docker
docker compose run --rm -it bridge

# Podman
podman compose run --rm -it bridge
```

Scan the QR code with WhatsApp on your phone: **Settings → Linked Devices → Link a Device**.

The session is saved to `./store/whatsapp.db`. You won't need to scan again unless you explicitly log out.

**3. Start the bridge as a daemon**

```bash
# Docker
docker compose up -d

# Podman
podman compose up -d
```

The bridge runs in the background, survives reboots (`restart: unless-stopped`), and exposes the REST API at `http://localhost:8080`.

**4. Configure Claude Desktop**

Add to `~/Library/Application Support/Claude/claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "whatsapp": {
      "command": "uv",
      "args": [
        "--directory",
        "/path/to/whatsapp-mcp/whatsapp-mcp-server",
        "run",
        "main.py"
      ],
      "env": {
        "WHATSAPP_DB_PATH": "/path/to/whatsapp-mcp/store/messages.db"
      }
    }
  }
}
```

Replace `/path/to/whatsapp-mcp` with wherever you cloned the repo.
`WHATSAPP_DB_PATH` points to `store/` which is bind-mounted from the container to the host.
`WHATSAPP_API_BASE_URL` defaults to `http://localhost:8080/api` — no need to set it.

**5. Restart Claude Desktop**

The WhatsApp tools will appear in Claude Desktop automatically.

**Useful commands**

```bash
docker compose logs -f bridge     # tail bridge logs
docker compose stop bridge        # stop daemon
docker compose start bridge       # start again (no QR needed)
docker compose down               # stop and remove container (store/ kept)

# Reset session (forces QR re-scan)
rm store/whatsapp.db store/messages.db
docker compose run --rm -it bridge
```

---

### Option B — Local Go

**Prerequisites**
- Go 1.21+
- Python 3.6+
- `uv` — `curl -LsSf https://astral.sh/uv/install.sh | sh`
- FFmpeg *(optional)* — only needed to auto-convert audio to WhatsApp voice messages

**1. Clone the repo**

```bash
git clone https://github.com/pesnik/whatsapp-mcp.git
cd whatsapp-mcp
```

**2. Run the bridge**

```bash
cd whatsapp-bridge
go run main.go
```

Scan the QR code on first run. To keep it running in the background:

```bash
nohup go run main.go > bridge.log 2>&1 &
```

**3. Configure Claude Desktop**

```json
{
  "mcpServers": {
    "whatsapp": {
      "command": "uv",
      "args": [
        "--directory",
        "/path/to/whatsapp-mcp/whatsapp-mcp-server",
        "run",
        "main.py"
      ]
    }
  }
}
```

Replace `/path/to/whatsapp-mcp` with your clone path. No `env` block needed — the MCP server resolves the DB path relative to itself automatically.

Save to `~/Library/Application Support/Claude/claude_desktop_config.json` (Claude Desktop) or `~/.cursor/mcp.json` (Cursor).

**4. Restart Claude Desktop / Cursor**

---

### Windows (local Go only)

`go-sqlite3` requires CGO, which is disabled by default on Windows. Fix:

1. Install [MSYS2](https://www.msys2.org/) and add `ucrt64\bin` to PATH ([guide](https://code.visualstudio.com/docs/cpp/config-mingw))
2. Then run:
   ```bash
   cd whatsapp-bridge
   go env -w CGO_ENABLED=1
   go run main.go
   ```

---

## Architecture

```
Claude Desktop
     │ stdio (MCP)
     ▼
Python MCP server          reads SQLite directly
(whatsapp-mcp-server/)  ──────────────────────────► store/messages.db
     │ HTTP REST                                           ▲
     ▼                                                     │ writes
Go bridge                  ────────────────────────────────┘
(whatsapp-bridge/)
     │ WhatsApp Web (whatsmeow)
     ▼
WhatsApp
```

- **Go bridge** — connects to WhatsApp, keeps SQLite up to date, exposes REST API on `:8080`
- **Python MCP server** — implements MCP protocol, reads SQLite directly and calls REST API
- **store/** — bind-mounted to host; contains `whatsapp.db` (session) and `messages.db` (history)

---

## MCP Tools

| Tool | Description |
|------|-------------|
| `search_contacts` | Search contacts by name or phone number |
| `list_chats` | List chats with metadata |
| `get_chat` | Get info about a specific chat |
| `get_direct_chat_by_contact` | Find a direct chat with a contact |
| `get_contact_chats` | All chats involving a contact |
| `get_last_interaction` | Most recent message with a contact |
| `list_messages` | Retrieve messages with filters |
| `get_message_context` | Context around a specific message |
| `send_message` | Send a message to a number or group JID |
| `send_file` | Send image, video, document, or raw audio |
| `send_audio_message` | Send audio as a WhatsApp voice message (ogg/opus; FFmpeg auto-converts other formats) |
| `download_media` | Download media from a message, returns local path |

---

## Troubleshooting

**QR code not showing**
Run with `-it` flag: `docker compose run --rm -it bridge`

**Already logged in**
The bridge reconnects automatically — no QR needed.

**Device limit reached**
Remove a linked device in WhatsApp: Settings → Linked Devices.

**No messages loading**
After first auth, allow a few minutes for history to sync.

**Out of sync / corrupted state**
```bash
rm store/messages.db store/whatsapp.db
docker compose run --rm -it bridge   # re-scan QR
```

**uv not found**
Use the full path from `which uv` in the Claude Desktop config.

For MCP-specific issues see the [MCP troubleshooting docs](https://modelcontextprotocol.io/quickstart/server#claude-for-desktop-integration-issues).
