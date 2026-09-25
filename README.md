# WhatsApp MCP Server

A Model Context Protocol (MCP) server for WhatsApp. Search and read your personal WhatsApp messages (including images, videos, documents, and audio), search contacts, and send messages to individuals or groups.

Connects to your **personal WhatsApp account** via the WhatsApp Web multidevice API using [whatsmeow](https://github.com/tulir/whatsmeow). All messages are stored locally in SQLite and only sent to an LLM when tools are invoked.

> **Fork of [lharries/whatsapp-mcp](https://github.com/lharries/whatsapp-mcp)** — customized for [opencode-hub](https://github.com/pesnik/opencode-hub) integration with bot mention detection, reply-to-bot conversation continuity, and progressive disclosure context.

![WhatsApp MCP](./example-use.png)

> *Caution:* as with many MCP servers, this project is subject to [the lethal trifecta](https://simonwillison.net/2025/Jun/16/the-lethal-trifecta/). Prompt injection could lead to private data exfiltration.

---

## Features

### Core (upstream)
- MCP tools for searching contacts, chats, and messages
- Send messages, files, and audio to individuals or groups
- Download media from messages
- Local SQLite storage — no cloud dependency

### opencode-hub Integration (this fork)
- **Bot mention detection** — protocol-level JID mentions + LID-based detection for contact-name mentions
- **Reply-to-bot detection** — when a human replies to the bot's message (even without `@`), the bot understands the context via quoted message content
- **In-memory message cache** — last 50 messages per chat cached for instant reply lookup (no DB hit)
- **Structured bot events** — `OPENSENSE_BOT_EVENT` JSON emitted to stdout for hub listener consumption
- **Progressive disclosure** — quoted message body included in agent prompt for conversation continuity
- **Alias-based mention detection** — hub listener matches `@alias` patterns in message text

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

Two ways to authenticate on first run:

**Option 1 — Terminal QR (interactive)**

```bash
# Docker
docker compose run --rm -it bridge

# Podman
podman compose run --rm -it bridge
```

Scan the QR code printed in the terminal with WhatsApp: **Settings → Linked Devices → Link a Device**.

**Option 2 — HTTP QR (headless / daemon)**

Start the bridge as a daemon and fetch the QR code via HTTP:

```bash
docker compose up -d
```

Then poll the QR endpoint until a code is available:

```bash
# Check status
curl http://localhost:8080/api/auth/status

# Get QR as base64 PNG
curl http://localhost:8080/api/auth/qr
```

The response contains a `qr` field (base64-encoded PNG) you can decode and display, and a `qr_raw` field (raw string) for terminal rendering. The QR refreshes automatically; poll until `status.logged_in` is `true`.

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

# Auth endpoints (bridge must be running)
curl http://localhost:8080/api/auth/status   # check connection state
curl http://localhost:8080/api/auth/qr       # get QR as base64 PNG (during pairing only)
curl -X POST http://localhost:8080/api/auth/logout  # disconnect session

# Reset session (forces QR re-scan)
rm store/whatsapp.db store/messages.db
docker compose run --rm -it bridge
```

---

### Option B — Local Go

**Prerequisites**
- Go 1.26+
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
opencode-hub
     │ docker logs (JSON events)
     ▼
MentionListener           ←── listens for OPENSENSE_BOT_EVENT
(packages/hub/src/)
     │ createTask + runTaskWorker
     ▼
Agent (opencode)          ←── receives prompt with quoted context
     │ task output
     ▼
MentionListener           ←── sendMessageToChat via bridge REST API
     │ HTTP POST /api/messages/send
     ▼
Go bridge (whatsapp-bridge/)
     │ WhatsApp Web (whatsmeow)
     ▼
WhatsApp
```

### Components

- **Go bridge** — connects to WhatsApp, keeps SQLite up to date, exposes REST API on `:8080`, emits structured `OPENSENSE_BOT_EVENT` JSON for bot mentions
- **Python MCP server** — implements MCP protocol, reads SQLite directly and calls REST API
- **Hub MentionListener** — streams docker logs, creates agent tasks, sends replies via bridge
- **store/** — bind-mounted to host; contains `whatsapp.db` (session) and `messages.db` (history)

### Bot Event Flow

```
1. Human sends message in WhatsApp group
2. Go bridge detects mention (JID, LID, or alias) or reply-to-bot
3. Go bridge emits OPENSENSE_BOT_EVENT JSON to stdout
4. Hub MentionListener streams docker logs, parses event
5. Listener builds prompt with quoted message context (progressive disclosure)
6. Agent receives task, generates response
7. Listener sends response back via bridge REST API
8. Human sees bot reply in WhatsApp
```

---

## Bot Mention Detection

The Go bridge detects bot mentions via three methods:

1. **Protocol-level JID mentions** — WhatsApp's `@mention` system (when you type `@` and select a contact)
2. **LID-based detection** — WhatsApp uses LID (Linked Device ID) when someone selects a contact by name; the bridge matches against both phone number and LID
3. **Text-based alias matching** — hub listener checks message text for `@alias` patterns configured per user

### Reply-to-Bot Detection

When a human uses WhatsApp's "Reply" feature on the bot's message:
- `ContextInfo.StanzaID` identifies the original bot message
- `ContextInfo.Participant` is checked against bot JIDs
- Quoted message body is looked up from the in-memory cache
- Event is emitted even without `@`-mention (conversation continuity)

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

## REST API (Go Bridge)

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/auth/status` | GET | Connection and login status |
| `/api/auth/qr` | GET | QR code as base64 PNG (during pairing) |
| `/api/auth/logout` | POST | Disconnect and clear session |
| `/api/send` | POST | Send message or media |
| `/api/messages/send` | POST | Send text message (used by MentionListener) |
| `/api/chats` | GET | List all known chats |
| `/api/download` | POST | Download media from a message |
| `/api/presence` | POST | Set online/offline presence |
| `/api/presence/subscribe` | POST | Subscribe to presence updates for a contact |
| `/api/presence/get` | GET | Get last-known presence for a contact |

---

## Troubleshooting

**QR code not showing in terminal**
Run with `-it` flag: `docker compose run --rm -it bridge`
Or start as daemon and use `GET /api/auth/qr` to fetch the QR as a base64 PNG.

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

**Bot not responding to mentions**
- Check bridge is connected: `curl http://localhost:8080/api/auth/status`
- Check hub listener is running: `docker logs opencode-hub | grep listener`
- Verify bot status in DB: `sqlite3 /data/opencode-hub.sqlite "SELECT status FROM whatsapp_bot_settings WHERE user_id = 'YOUR_USER_ID'"`

For MCP-specific issues see the [MCP troubleshooting docs](https://modelcontextprotocol.io/quickstart/server#claude-for-desktop-integration-issues).
