"""Interactive TDLib user authorization state machine."""

from __future__ import annotations

import base64
from getpass import getpass
from typing import Any

from .config import TdlibConfig
from .tdjson_client import TdJsonClient, TdlibError


class AuthorizationError(RuntimeError):
    """Authorization cannot safely continue."""


def _submit(client: TdJsonClient, request: dict[str, Any]) -> bool:
    try:
        client.request(request, timeout=60.0)
        return True
    except TdlibError as exc:
        print(f"Authentication was not accepted: {exc}")
        return False


def authorize(client: TdJsonClient, config: TdlibConfig) -> None:
    """Drive authorization using exactly the states emitted by TDLib."""
    version = -1
    while True:
        state, version = client.wait_for_authorization_change(version, timeout=300.0)
        state_type = state.get("@type")

        if state_type == "authorizationStateWaitTdlibParameters":
            if not _submit(
                client,
                {
                    "@type": "setTdlibParameters",
                    "use_test_dc": config.use_test_dc,
                    "database_directory": str(config.database_directory),
                    "files_directory": str(config.files_directory),
                    # TDLib's JSON representation for a TL `bytes` field is base64.
                    "database_encryption_key": base64.b64encode(
                        config.database_encryption_key.encode("utf-8")
                    ).decode("ascii"),
                    "use_file_database": True,
                    "use_chat_info_database": True,
                    "use_message_database": True,
                    "use_secret_chats": False,
                    "api_id": config.api_id,
                    "api_hash": config.api_hash,
                    "system_language_code": "en",
                    "device_model": "Detectives Python TDLib CLI",
                    "system_version": "Windows",
                    "application_version": "1.0.0",
                },
            ):
                version -= 1
        elif state_type == "authorizationStateWaitPhoneNumber":
            phone = input("Phone number in international format (for example +84123...): ").strip()
            if not _submit(
                client,
                {"@type": "setAuthenticationPhoneNumber", "phone_number": phone},
            ):
                version -= 1
        elif state_type == "authorizationStateWaitEmailAddress":
            email = input("Telegram requested a login email address: ").strip()
            if not _submit(
                client,
                {"@type": "setAuthenticationEmailAddress", "email_address": email},
            ):
                version -= 1
        elif state_type == "authorizationStateWaitEmailCode":
            code = input("Email authentication code: ").strip()
            if not _submit(
                client,
                {
                    "@type": "checkAuthenticationEmailCode",
                    "code": {"@type": "emailAddressAuthenticationCode", "code": code},
                },
            ):
                version -= 1
        elif state_type == "authorizationStateWaitCode":
            code_info = state.get("code_info") or {}
            code_type = (code_info.get("type") or {}).get("@type", "authentication code")
            print(f"Telegram is waiting for: {code_type}.")
            code = input("Authentication code: ").strip()
            if not _submit(client, {"@type": "checkAuthenticationCode", "code": code}):
                version -= 1
        elif state_type == "authorizationStateWaitPassword":
            hint = state.get("password_hint")
            if hint:
                print(f"Two-step verification hint: {hint}")
            password = getpass("Two-step verification password: ")
            if not _submit(
                client,
                {"@type": "checkAuthenticationPassword", "password": password},
            ):
                version -= 1
        elif state_type == "authorizationStateWaitOtherDeviceConfirmation":
            print("Confirm this login from an existing Telegram device using this link:")
            print(state.get("link", "(link unavailable)"))
        elif state_type == "authorizationStateWaitRegistration":
            raise AuthorizationError(
                "Telegram reports that this phone number has no account. "
                "Registration is intentionally disabled."
            )
        elif state_type == "authorizationStateWaitPremiumPurchase":
            raise AuthorizationError(
                "Telegram requires Premium to complete this authorization. "
                "The standalone test will not make purchases."
            )
        elif state_type == "authorizationStateReady":
            return
        elif state_type in {
            "authorizationStateLoggingOut",
            "authorizationStateClosing",
            "authorizationStateClosed",
        }:
            raise AuthorizationError(f"Authorization stopped in state {state_type}.")
        else:
            raise AuthorizationError(f"Unsupported authorization state: {state_type}")
