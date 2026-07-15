from __future__ import annotations

import unittest

from telegram.formatting import format_message, message_text, partial_phone, user_name


class FormattingTests(unittest.TestCase):
    def test_partial_phone_hides_all_but_last_four_digits(self) -> None:
        self.assertEqual(partial_phone("84123456789"), "*******6789")
        self.assertEqual(partial_phone(""), "(not available)")

    def test_user_name_prefers_name_and_active_username(self) -> None:
        user = {
            "id": 1,
            "first_name": "Test",
            "last_name": "User",
            "usernames": {"active_usernames": ["tester"]},
        }
        self.assertEqual(user_name(user), "Test User (@tester)")

    def test_text_and_media_rendering(self) -> None:
        self.assertEqual(
            message_text({"@type": "messageText", "text": {"text": "hello"}}),
            "hello",
        )
        self.assertEqual(
            message_text({"@type": "messagePhoto", "caption": {"text": "caption"}}),
            "[Photo] caption",
        )

    def test_message_format_does_not_expose_phone(self) -> None:
        users = {
            5: {
                "id": 5,
                "first_name": "Alice",
                "last_name": "",
                "phone_number": "84123456789",
            }
        }
        message = {
            "date": 0,
            "sender_id": {"@type": "messageSenderUser", "user_id": 5},
            "content": {"@type": "messageText", "text": {"text": "hello"}},
        }
        rendered = format_message(message, users)
        self.assertIn("Alice: hello", rendered)
        self.assertNotIn("84123456789", rendered)


if __name__ == "__main__":
    unittest.main()

