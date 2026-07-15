"""Interactive smoke tests for basic TDLib user-account operations."""

from __future__ import annotations

import sys
from datetime import datetime
from typing import Any

from .auth import AuthorizationError, authorize
from .config import ConfigurationError, TdlibConfig
from .formatting import format_message, partial_phone, user_name
from .tdjson_client import TdJsonClient, TdlibError, TdlibTimeout


CHAT_LIMIT = 20
HISTORY_PAGE_SIZE = 10


def show_account(client: TdJsonClient) -> dict[str, Any]:
    me = client.request({"@type": "getMe"})
    usernames = (me.get("usernames") or {}).get("active_usernames") or []
    print("\nCurrent Telegram account")
    print(f"  ID:       {me.get('id')}")
    print(f"  Name:     {user_name(me)}")
    print(f"  Username: @{usernames[0]}" if usernames else "  Username: (none)")
    print(f"  Phone:    {partial_phone(me.get('phone_number', ''))}")
    return me


def list_main_chats(client: TdJsonClient, limit: int = CHAT_LIMIT) -> list[dict[str, Any]]:
    try:
        client.request(
            {"@type": "loadChats", "chat_list": {"@type": "chatListMain"}, "limit": limit}
        )
    except TdlibError as exc:
        # 404 is the documented signal that all chats from the list are loaded.
        if exc.code != 404:
            raise
    result = client.request(
        {"@type": "getChats", "chat_list": {"@type": "chatListMain"}, "limit": limit}
    )
    cache = client.snapshot_chats()
    chats = [cache[chat_id] for chat_id in result.get("chat_ids", []) if chat_id in cache]

    print(f"\nMain chats (up to {limit})")
    if not chats:
        print("  No chats were returned.")
    for index, chat in enumerate(chats, start=1):
        chat_type = (chat.get("type") or {}).get("@type", "chat").removeprefix("chatType")
        print(f"  {index:>2}. {chat.get('title', '(untitled)')} [{chat_type}] (id={chat['id']})")
    return chats


def show_history(
    client: TdJsonClient, chat: dict[str, Any], from_message_id: int = 0
) -> int | None:
    result = client.request(
        {
            "@type": "getChatHistory",
            "chat_id": chat["id"],
            "from_message_id": from_message_id,
            "offset": 0,
            "limit": HISTORY_PAGE_SIZE,
            "only_local": False,
        }
    )
    messages = result.get("messages", [])
    print(f"\nRecent messages in {chat.get('title', chat['id'])!r} (newest first)")
    if not messages:
        print("  No messages were returned.")
        return None
    users = client.snapshot_users()
    for message in messages:
        print("  " + format_message(message, users))
    return messages[-1].get("id")


def browse_history(client: TdJsonClient) -> None:
    chats = list_main_chats(client)
    if not chats:
        return
    choice = input("Select a chat number, or press Enter to cancel: ").strip()
    if not choice:
        return
    try:
        chat = chats[int(choice) - 1]
    except (ValueError, IndexError):
        print("Invalid chat selection.")
        return

    from_message_id = 0
    while True:
        next_id = show_history(client, chat, from_message_id)
        if not next_id:
            return
        if input("Load 10 older messages? Type yes to continue: ").strip().lower() != "yes":
            return
        from_message_id = next_id


def send_saved_message(client: TdJsonClient) -> None:
    me = client.request({"@type": "getMe"})
    saved_chat = client.request(
        {"@type": "createPrivateChat", "user_id": me["id"], "force": False}
    )
    text = (
        "TDLib Python test from tech4city — "
        + datetime.now().astimezone().isoformat(timespec="seconds")
    )
    print("\nThe following real message will be sent only to Saved Messages:")
    print(f"  {text}")
    if input("Type yes to send it: ").strip().lower() != "yes":
        print("Send canceled.")
        return

    message = client.request(
        {
            "@type": "sendMessage",
            "chat_id": saved_chat["id"],
            "input_message_content": {
                "@type": "inputMessageText",
                "text": {"@type": "formattedText", "text": text, "entities": []},
                "link_preview_options": {"@type": "linkPreviewOptions", "is_disabled": True},
                "clear_draft": False,
            },
        }
    )
    message_id = message.get("id")
    sending_state = (message.get("sending_state") or {}).get("@type")
    if not sending_state:
        print(f"Message sent successfully (id={message_id}).")
        return
    completion = client.wait_for_send(message_id, timeout=20.0)
    if completion is None:
        print(f"Message was accepted by TDLib but confirmation timed out (id={message_id}).")
    elif completion.get("@type") == "updateMessageSendSucceeded":
        final_message = completion.get("message") or {}
        print(f"Message sent successfully (id={final_message.get('id')}).")
    else:
        error = completion.get("error") or {}
        print(f"Message failed: {error.get('code')} {error.get('message')}")


def test_network(client: TdJsonClient) -> None:
    client.request({"@type": "testNetwork"}, timeout=30.0)
    print("Telegram network test succeeded.")


def interactive_menu(client: TdJsonClient) -> None:
    actions = {
        "1": ("Show current account", lambda: show_account(client)),
        "2": ("List main chats", lambda: list_main_chats(client)),
        "3": ("Select a chat and read recent messages", lambda: browse_history(client)),
        "4": ("Send a test message to Saved Messages", lambda: send_saved_message(client)),
        "5": ("Test Telegram network connectivity", lambda: test_network(client)),
    }
    while True:
        print("\nTDLib basic usage tests")
        for key, (label, _) in actions.items():
            print(f"  {key}. {label}")
        print("  6. Exit cleanly")
        choice = input("Choose an action: ").strip()
        if choice == "6":
            return
        action = actions.get(choice)
        if action is None:
            print("Invalid selection.")
            continue
        try:
            action[1]()
        except (TdlibError, TdlibTimeout) as exc:
            print(exc)


def main() -> int:
    try:
        config = TdlibConfig.load()
        with TdJsonClient(config.tdjson_path) as client:
            version = client.start()
            print(f"Loaded TDLib {version} from {config.tdjson_path}")
            print("Using Telegram production data centers.")
            authorize(client, config)
            print("Authorization ready.")
            interactive_menu(client)
        print("TDLib closed cleanly.")
        return 0
    except KeyboardInterrupt:
        print("\nCanceled. Closing TDLib...")
        return 130
    except (ConfigurationError, AuthorizationError, FileNotFoundError, RuntimeError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())

