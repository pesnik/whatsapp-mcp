import os
from dataclasses import asdict, is_dataclass
from typing import List, Dict, Any, Optional
from mcp.server.fastmcp import FastMCP
from whatsapp import (
    search_contacts as whatsapp_search_contacts,
    list_messages as whatsapp_list_messages,
    list_chats as whatsapp_list_chats,
    get_chat as whatsapp_get_chat,
    get_direct_chat_by_contact as whatsapp_get_direct_chat_by_contact,
    get_contact_chats as whatsapp_get_contact_chats,
    get_last_interaction as whatsapp_get_last_interaction,
    get_message_context as whatsapp_get_message_context,
    send_message as whatsapp_send_message,
    set_presence as whatsapp_set_presence,
    subscribe_presence as whatsapp_subscribe_presence,
    get_presence as whatsapp_get_presence,
    send_file as whatsapp_send_file,
    send_audio_message as whatsapp_audio_voice_message,
    download_media as whatsapp_download_media
)

# Initialize FastMCP server -- network-reachable by default (SSE), not
# parent-process-only stdio. opencode-hub (and any other multi-tenant
# host) needs to reach this from a *different* container over the
# network; stdio only ever works when the MCP client launches this
# process directly as its own child, which isn't the shape here. Host/
# port stay env-configurable, matching this fork's own existing pattern
# (see whatsapp.py's WHATSAPP_DB_PATH/WHATSAPP_API_BASE_URL) rather than
# hardcoded, so a plain `python main.py` still works unchanged for the
# original single-user/stdio use case if WHATSAPP_MCP_TRANSPORT is left
# at its default.
MCP_TRANSPORT = os.environ.get("WHATSAPP_MCP_TRANSPORT", "stdio")
MCP_HOST = os.environ.get("WHATSAPP_MCP_HOST", "0.0.0.0")
MCP_PORT = int(os.environ.get("WHATSAPP_MCP_PORT", "8081"))

mcp = FastMCP("whatsapp", host=MCP_HOST, port=MCP_PORT)

# whatsapp.py's own functions return real @dataclass instances (Chat,
# Message, Contact, MessageContext -- see whatsapp.py:14-49), but every
# tool below is declared to return a plain dict/list of dicts and was
# just handing the dataclass straight through unconverted. That worked
# under older/looser MCP clients, but mcp[cli]>=1.6.0's FastMCP validates
# a tool's actual return value against its declared type before sending
# it -- a raw dataclass instance fails that check with a real Pydantic
# "Input should be a valid dictionary" error (caught live: every read
# tool that touches a Chat/Message was broken this way). asdict() is
# stdlib-recursive, so it converts nested dataclasses (MessageContext's
# own message/before/after fields) in one call; leftover datetime values
# inside the resulting dict serialize fine on their own -- pydantic's
# Any-serializer already knows how to encode datetime, only the outer
# "is this actually a dict" check was the problem.
def _to_jsonable(value):
    if is_dataclass(value) and not isinstance(value, type):
        return asdict(value)
    if isinstance(value, list):
        return [_to_jsonable(v) for v in value]
    return value

@mcp.tool()
def search_contacts(query: str) -> List[Dict[str, Any]]:
    """Search WhatsApp contacts by name or phone number.
    
    Args:
        query: Search term to match against contact names or phone numbers
    """
    contacts = whatsapp_search_contacts(query)
    return _to_jsonable(contacts)

@mcp.tool()
def list_messages(
    after: Optional[str] = None,
    before: Optional[str] = None,
    sender_phone_number: Optional[str] = None,
    chat_jid: Optional[str] = None,
    query: Optional[str] = None,
    limit: int = 20,
    page: int = 0,
    include_context: bool = True,
    context_before: int = 1,
    context_after: int = 1
) -> List[Dict[str, Any]]:
    """Get WhatsApp messages matching specified criteria with optional context.
    
    Args:
        after: Optional ISO-8601 formatted string to only return messages after this date
        before: Optional ISO-8601 formatted string to only return messages before this date
        sender_phone_number: Optional phone number to filter messages by sender
        chat_jid: Optional chat JID to filter messages by chat
        query: Optional search term to filter messages by content
        limit: Maximum number of messages to return (default 20)
        page: Page number for pagination (default 0)
        include_context: Whether to include messages before and after matches (default True)
        context_before: Number of messages to include before each match (default 1)
        context_after: Number of messages to include after each match (default 1)
    """
    messages = whatsapp_list_messages(
        after=after,
        before=before,
        sender_phone_number=sender_phone_number,
        chat_jid=chat_jid,
        query=query,
        limit=limit,
        page=page,
        include_context=include_context,
        context_before=context_before,
        context_after=context_after
    )
    return _to_jsonable(messages)

@mcp.tool()
def list_chats(
    query: Optional[str] = None,
    limit: int = 20,
    page: int = 0,
    include_last_message: bool = True,
    sort_by: str = "last_active"
) -> List[Dict[str, Any]]:
    """Get WhatsApp chats matching specified criteria.
    
    Args:
        query: Optional search term to filter chats by name or JID
        limit: Maximum number of chats to return (default 20)
        page: Page number for pagination (default 0)
        include_last_message: Whether to include the last message in each chat (default True)
        sort_by: Field to sort results by, either "last_active" or "name" (default "last_active")
    """
    chats = whatsapp_list_chats(
        query=query,
        limit=limit,
        page=page,
        include_last_message=include_last_message,
        sort_by=sort_by
    )
    return _to_jsonable(chats)

@mcp.tool()
def get_chat(chat_jid: str, include_last_message: bool = True) -> Optional[Dict[str, Any]]:
    """Get WhatsApp chat metadata by JID.

    Args:
        chat_jid: The JID of the chat to retrieve
        include_last_message: Whether to include the last message (default True)
    """
    chat = whatsapp_get_chat(chat_jid, include_last_message)
    return _to_jsonable(chat) if chat is not None else None

@mcp.tool()
def get_direct_chat_by_contact(sender_phone_number: str) -> Optional[Dict[str, Any]]:
    """Get WhatsApp chat metadata by sender phone number.

    Args:
        sender_phone_number: The phone number to search for
    """
    chat = whatsapp_get_direct_chat_by_contact(sender_phone_number)
    return _to_jsonable(chat) if chat is not None else None

@mcp.tool()
def get_contact_chats(jid: str, limit: int = 20, page: int = 0) -> List[Dict[str, Any]]:
    """Get all WhatsApp chats involving the contact.

    Args:
        jid: The contact's JID to search for
        limit: Maximum number of chats to return (default 20)
        page: Page number for pagination (default 0)
    """
    chats = whatsapp_get_contact_chats(jid, limit, page)
    return _to_jsonable(chats)

@mcp.tool()
def get_last_interaction(jid: str) -> str:
    """Get most recent WhatsApp message involving the contact.
    
    Args:
        jid: The JID of the contact to search for
    """
    message = whatsapp_get_last_interaction(jid)
    return message

@mcp.tool()
def get_message_context(
    message_id: str,
    before: int = 5,
    after: int = 5
) -> Dict[str, Any]:
    """Get context around a specific WhatsApp message.
    
    Args:
        message_id: The ID of the message to get context for
        before: Number of messages to include before the target message (default 5)
        after: Number of messages to include after the target message (default 5)
    """
    context = whatsapp_get_message_context(message_id, before, after)
    return _to_jsonable(context)

@mcp.tool()
def send_message(
    recipient: str,
    message: str
) -> Dict[str, Any]:
    """Send a WhatsApp message to a person or group.

    Args:
        recipient: A phone number with country code but no + or other symbols,
                 a JID (e.g., "123456789@s.whatsapp.net" or a group JID like
                 "123456789@g.us"), OR a plain display name -- a name is
                 automatically resolved against your already-synced chats and
                 contacts (the same lookup list_chats/search_contacts use) if
                 it matches exactly one. If it matches none or more than one,
                 this returns success=false with the real candidates found
                 (or a note that nothing matched) instead of attempting to
                 send -- don't retry blindly on that kind of failure, resolve
                 the ambiguity (via list_chats/search_contacts, or by asking
                 the user) and call this again with the exact JID.
        message: The message text to send

    Returns:
        A dictionary containing success status and a status message
    """
    # Validate input
    if not recipient:
        return {
            "success": False,
            "message": "Recipient must be provided"
        }
    
    # Call the whatsapp_send_message function with the unified recipient parameter
    success, status_message = whatsapp_send_message(recipient, message)
    return {
        "success": success,
        "message": status_message
    }

@mcp.tool()
def set_presence(available: bool) -> Dict[str, Any]:
    """Broadcast this WhatsApp account's own online/offline status to contacts.

    A manual action, not automatic -- call it deliberately (e.g. before sending
    a message) rather than every turn, since an account that's always "online"
    is itself a signal that it's automated, not a person.

    Args:
        available: True to appear online, False to appear offline
    """
    success, status_message = whatsapp_set_presence(available)
    return {"success": success, "message": status_message}

@mcp.tool()
def subscribe_presence(jid: str) -> Dict[str, Any]:
    """Start receiving presence (online/last seen) updates for one contact.

    Required before get_presence returns anything useful for that contact --
    WhatsApp never pushes presence for someone you haven't subscribed to, and
    what you get after subscribing still depends on their own privacy settings.

    Args:
        jid: The contact's JID (e.g. "123456789@s.whatsapp.net")
    """
    success, status_message = whatsapp_subscribe_presence(jid)
    return {"success": success, "message": status_message}

@mcp.tool()
def get_presence(jid: str) -> Optional[Dict[str, Any]]:
    """Get the last-known presence for a contact you've subscribed to.

    Returns None if no presence update has arrived yet for this JID (call
    subscribe_presence first, then allow a moment for WhatsApp to push one).

    Args:
        jid: The contact's JID (e.g. "123456789@s.whatsapp.net")

    Returns:
        A dict with "unavailable" (bool) and "last_seen" (unix timestamp,
        omitted if the contact has hidden it), or None if unknown.
    """
    return whatsapp_get_presence(jid)

@mcp.tool()
def send_file(recipient: str, media_path: str) -> Dict[str, Any]:
    """Send a file such as a picture, raw audio, video or document via WhatsApp to the specified recipient.

    Args:
        recipient: A phone number, a JID, or a plain display name -- same
                 automatic name resolution (and same fail-fast-on-ambiguity
                 behavior) as send_message. See send_message's own docstring
                 for the details.
        media_path: The absolute path to the media file to send (image, video, document)
    
    Returns:
        A dictionary containing success status and a status message
    """
    
    # Call the whatsapp_send_file function
    success, status_message = whatsapp_send_file(recipient, media_path)
    return {
        "success": success,
        "message": status_message
    }

@mcp.tool()
def send_audio_message(recipient: str, media_path: str) -> Dict[str, Any]:
    """Send any audio file as a WhatsApp audio message to the specified recipient. If it errors due to ffmpeg not being installed, use send_file instead.

    Args:
        recipient: A phone number, a JID, or a plain display name -- same
                 automatic name resolution (and same fail-fast-on-ambiguity
                 behavior) as send_message. See send_message's own docstring
                 for the details.
        media_path: The absolute path to the audio file to send (will be converted to Opus .ogg if it's not a .ogg file)
    
    Returns:
        A dictionary containing success status and a status message
    """
    success, status_message = whatsapp_audio_voice_message(recipient, media_path)
    return {
        "success": success,
        "message": status_message
    }

@mcp.tool()
def download_media(message_id: str, chat_jid: str) -> Dict[str, Any]:
    """Download media from a WhatsApp message and get the local file path.
    
    Args:
        message_id: The ID of the message containing the media
        chat_jid: The JID of the chat containing the message
    
    Returns:
        A dictionary containing success status, a status message, and the file path if successful
    """
    file_path = whatsapp_download_media(message_id, chat_jid)
    
    if file_path:
        return {
            "success": True,
            "message": "Media downloaded successfully",
            "file_path": file_path
        }
    else:
        return {
            "success": False,
            "message": "Failed to download media"
        }

if __name__ == "__main__":
    # Initialize and run the server
    mcp.run(transport=MCP_TRANSPORT)