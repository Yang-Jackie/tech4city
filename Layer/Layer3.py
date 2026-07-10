from __future__ import annotations

import json
import re
import time
from collections.abc import Callable, Mapping, Sequence
from typing import Any


CATEGORY_LABELS = (
    "not_cyberbullying",
    "abusive_behavior",
    "hate_speech",
    "online_harassment",
    "impersonation",
    "cyberstalking",
    "flaming",
    "outing",
    "doxing",
    "denigration",
    "exclusion",
    "trolling",
    "threat_or_intimidation",
    "sexual_harassment",
    "coercion_or_blackmail",
    "rumor_spreading_or_defamation",
    "public_humiliation",
    "mocking_or_ridicule",
    "insult_or_name_calling",
    "body_shaming",
    "identity_based_attack",
    "privacy_violation",
    "pile_on_or_mob_attack",
    "non_consensual_image_sharing",
    "self_harm_related_harassment",
    "spam_or_mass_targeting",
    "manipulation_or_gaslighting",
    "brigading",
    "other_harmful_behavior",
)

EVIDENCE_STRENGTHS = ("direct", "strong", "moderate", "weak", "insufficient")
SEVERITIES = ("none", "low", "medium", "high", "urgent")

CYBERBULLYING_ANALYST_PROMPT = """
You are a multilingual cyberbullying conversation analyst.

You analyze conversation logs that contain sender IDs, timestamps, message IDs,
and messages in chronological order. Your goal is to explain whether the
suspected actor's messages toward the target show signs of cyberbullying.

You must be careful, evidence-based, and supportive to the target user.

Definitions:
Cyberbullying may involve targeted aggression, repeated harassment, humiliation,
intimidation, impersonation, identity-based abuse, privacy attacks, outing,
doxing, coercion, rumor-spreading, exclusion, cyberstalking, trolling, flaming,
or pile-on behavior. A single message can still be serious if it contains
threats, privacy exposure, coercion, or highly targeted abuse. However, not
every rude, toxic, sarcastic, or angry message is cyberbullying.

Category definitions:

* abusive_behavior: Broad hostile, insulting, degrading, or aggressive behavior.
* hate_speech: Attack or demeaning language targeting protected or identity-based attributes such as race, ethnicity, religion, nationality, gender, sexuality, disability, caste, or similar.
* online_harassment: Repeated or targeted unwanted hostile behavior toward a person.
* impersonation: Pretending to be another person or account in order to deceive, mock, harm, or manipulate.
* cyberstalking: Persistent unwanted monitoring, following, contacting, or tracking across time or platforms.
* flaming: Hostile, aggressive, or inflammatory argument meant to provoke or attack.
* outing: Revealing someone's private identity, status, relationship, personal history, or sensitive information without consent.
* doxing: Revealing or threatening to reveal private identifying, contact, school, workplace, or location information.
* denigration: Spreading degrading claims, rumors, or damaging statements about someone.
* exclusion: Deliberately isolating, excluding, or encouraging others to reject a target.
* trolling: Provoking, baiting, or disrupting to upset, humiliate, or get a reaction.
* threat_or_intimidation: Threatening harm, punishment, exposure, or intimidation.
* sexual_harassment: Unwanted sexual comments, pressure, humiliation, or targeting.
* coercion_or_blackmail: Pressuring someone through threats, exposure, manipulation, or demands.
* rumor_spreading_or_defamation: Spreading unverified harmful claims about a person.
* public_humiliation: Trying to embarrass or shame someone in front of others.
* mocking_or_ridicule: Making fun of someone repeatedly or cruelly.
* insult_or_name_calling: Direct insults, slurs, or degrading labels.
* body_shaming: Attacking appearance, body, weight, height, skin, or physical traits.
* identity_based_attack: Attacking a person because of identity or perceived identity.
* privacy_violation: Sharing, requesting, or exploiting private information without consent.
* pile_on_or_mob_attack: Multiple people targeting one person in a coordinated or escalating way.
* non_consensual_image_sharing: Sharing or threatening to share private images without consent.
* self_harm_related_harassment: Targeting someone's vulnerability in a harmful or abusive way.
* spam_or_mass_targeting: Repeated mass messages, tagging, or flooding directed at a target.
* manipulation_or_gaslighting: Distorting events or blaming the target to confuse, shame, or control them.
* brigading: Coordinating others to attack, report, shame, or overwhelm a target.
* other_harmful_behavior: Harmful behavior that does not fit the above categories.
* not_cyberbullying: The evidence does not support a cyberbullying interpretation.

Rules:

* Use only the provided conversation.
* Do not invent missing context.
* Do not assume guilt. Use cautious language such as "suspected", "may indicate", or "the evidence suggests".
* Distinguish cyberbullying from ordinary conflict, joking, sarcasm, criticism, or one-off rude behavior.
* Consider sender, target, order, timestamp, repetition, escalation, public/private setting, multiple actors, and whether one person is singled out.
* Cite message_id values as evidence.
* Do not quote explicit slurs, private information, or highly harmful wording. Use sanitized excerpts or paraphrases.
* Do not blame the target.
* Do not recommend retaliation.
* If evidence is weak or context is missing, say so clearly.
* If there are threats, privacy exposure, coercion, sexual harassment, doxing, impersonation, or cyberstalking signals, mark the severity higher and recommend trusted human/platform support.
* Output valid JSON only.
""".strip()

CYBERBULLYING_ANALYSIS_SCHEMA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "required": [
        "is_suspected_cyberbullying",
        "confidence",
        "severity",
        "target_user_ids",
        "suspected_actor_user_ids",
        "categories",
        "evidence",
        "pattern_analysis",
        "explanation_for_target",
        "uncertainty",
        "recommended_next_steps",
    ],
    "properties": {
        "is_suspected_cyberbullying": {"type": "boolean"},
        "confidence": {"type": "number", "minimum": 0, "maximum": 1},
        "severity": {"type": "string", "enum": list(SEVERITIES)},
        "target_user_ids": {"type": "array", "items": {"type": "string"}},
        "suspected_actor_user_ids": {"type": "array", "items": {"type": "string"}},
        "categories": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": ["label", "evidence_strength", "message_ids", "why"],
                "properties": {
                    "label": {"type": "string", "enum": list(CATEGORY_LABELS)},
                    "evidence_strength": {"type": "string", "enum": list(EVIDENCE_STRENGTHS)},
                    "message_ids": {"type": "array", "items": {"type": "string"}},
                    "why": {"type": "string"},
                },
            },
        },
        "evidence": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": ["message_ids", "category", "sanitized_excerpt", "why_it_matters"],
                "properties": {
                    "message_ids": {"type": "array", "items": {"type": "string"}},
                    "category": {"type": "string", "enum": list(CATEGORY_LABELS)},
                    "sanitized_excerpt": {"type": "string"},
                    "why_it_matters": {"type": "string"},
                },
            },
        },
        "pattern_analysis": {
            "type": "object",
            "additionalProperties": False,
            "required": [
                "is_targeted",
                "is_repeated",
                "shows_escalation",
                "has_power_or_group_dynamic",
                "notes",
            ],
            "properties": {
                "is_targeted": {"type": "boolean"},
                "is_repeated": {"type": "boolean"},
                "shows_escalation": {"type": "boolean"},
                "has_power_or_group_dynamic": {"type": "boolean"},
                "notes": {"type": "string"},
            },
        },
        "explanation_for_target": {"type": "string"},
        "uncertainty": {"type": "array", "items": {"type": "string"}},
        "recommended_next_steps": {"type": "array", "items": {"type": "string"}},
    },
}


class Layer3:
    """Adapter for the ChatGPT cyberbullying conversation explanation model."""

    DEFAULT_MODEL = "chatgpt-answer"

    def __init__(
        self,
        *,
        model: str = DEFAULT_MODEL,
        analyzer: Callable[..., dict[str, Any]] | None = None,
        client: Any | None = None,
        max_retries: int = 3,
        retry_sleep: float = 2.0,
        reasoning_effort: str = "auto",
        timeout: float | None = None,
    ) -> None:
        if max_retries <= 0:
            raise ValueError("max_retries must be positive")
        if retry_sleep < 0:
            raise ValueError("retry_sleep cannot be negative")

        self.model = model
        self._analyzer = analyzer
        self.client = client
        self.max_retries = max_retries
        self.retry_sleep = retry_sleep
        self.reasoning_effort = reasoning_effort
        self.timeout = timeout

    def explain(
        self,
        conversation: Any,
        *,
        target_user_ids: Sequence[str] | None = None,
        suspected_actor_user_ids: Sequence[str] | None = None,
        model: str | None = None,
        client: Any | None = None,
        max_retries: int | None = None,
        retry_sleep: float | None = None,
        reasoning_effort: str | None = None,
        timeout: float | None = None,
    ) -> dict[str, Any]:
        """Analyze a conversation using the local prompt and custom input format."""
        resolved_model = model or self.model
        analyzer = self._analyzer or self._analyze_cyberbullying_conversation

        analysis = analyzer(
            conversation,
            target_user_ids=target_user_ids,
            suspected_actor_user_ids=suspected_actor_user_ids,
            model=resolved_model,
            client=self.client if client is None else client,
            max_retries=self.max_retries if max_retries is None else max_retries,
            retry_sleep=self.retry_sleep if retry_sleep is None else retry_sleep,
            reasoning_effort=self.reasoning_effort if reasoning_effort is None else reasoning_effort,
            timeout=self.timeout if timeout is None else timeout,
        )

        return {
            "layer": 3,
            "explanation": analysis["explanation_for_target"],
            "analysis": analysis,
            "model": resolved_model,
        }

    def _analyze_cyberbullying_conversation(
        self,
        conversation_input: Mapping[str, Any] | Sequence[Mapping[str, Any]],
        *,
        target_user_ids: Sequence[str] | None = None,
        suspected_actor_user_ids: Sequence[str] | None = None,
        model: str = DEFAULT_MODEL,
        client: Any | None = None,
        max_retries: int = 3,
        retry_sleep: float = 2.0,
        reasoning_effort: str = "auto",
        timeout: float | None = None,
    ) -> dict[str, Any]:
        if max_retries <= 0:
            raise ValueError("max_retries must be positive")
        if retry_sleep < 0:
            raise ValueError("retry_sleep cannot be negative")

        payload = normalize_conversation_input(
            conversation_input,
            target_user_ids=target_user_ids,
            suspected_actor_user_ids=suspected_actor_user_ids,
        )
        input_text = json.dumps({"conversation": payload}, ensure_ascii=False)
        api_client = client or self._default_openai_client()
        kwargs: dict[str, Any] = {
            "model": model,
            "instructions": CYBERBULLYING_ANALYST_PROMPT,
            "input": input_text,
            "text": {
                "format": {
                    "type": "json_schema",
                    "name": "cyberbullying_analysis",
                    "schema": CYBERBULLYING_ANALYSIS_SCHEMA,
                    "strict": True,
                }
            },
        }
        if reasoning_effort != "auto":
            kwargs["reasoning"] = {"effort": reasoning_effort}
        if timeout is not None:
            kwargs["timeout"] = timeout

        last_error: Exception | None = None
        for attempt in range(1, max_retries + 1):
            try:
                response = api_client.responses.create(**kwargs)
                parsed = extract_json_object(get_response_output_text(response))
                return validate_analysis_output(parsed)
            except Exception as exc:  # noqa: BLE001 - preserve SDK/parsing errors after retries.
                last_error = exc
                if attempt >= max_retries:
                    break
                time.sleep(retry_sleep * attempt)

        raise RuntimeError(f"GPT cyberbullying analysis failed after {max_retries} attempts: {last_error}") from last_error

    @staticmethod
    def _default_openai_client() -> Any:
        from openai import OpenAI

        return OpenAI()


def normalize_conversation_input(
    conversation_input: Mapping[str, Any] | Sequence[Mapping[str, Any]],
    *,
    target_user_ids: Sequence[str] | None = None,
    suspected_actor_user_ids: Sequence[str] | None = None,
) -> dict[str, Any]:
    if isinstance(conversation_input, Mapping):
        payload = dict(conversation_input)
        if "messages" not in payload and isinstance(payload.get("conversation"), Mapping):
            payload = dict(payload["conversation"])
    else:
        payload = {"messages": list(conversation_input)}

    if "messages" not in payload:
        raise ValueError("conversation_input must contain a 'messages' list")
    if not isinstance(payload["messages"], list):
        raise ValueError("conversation_input['messages'] must be a list")

    payload["messages"] = [
        normalize_message(message, index)
        for index, message in enumerate(payload["messages"])
    ]
    if target_user_ids is not None:
        payload["target_user_ids"] = [str(user_id) for user_id in target_user_ids]
    else:
        payload["target_user_ids"] = [str(user_id) for user_id in payload.get("target_user_ids", [])]
    if suspected_actor_user_ids is not None:
        payload["suspected_actor_user_ids"] = [str(user_id) for user_id in suspected_actor_user_ids]
    else:
        payload["suspected_actor_user_ids"] = [
            str(user_id) for user_id in payload.get("suspected_actor_user_ids", [])
        ]
    return payload


def normalize_message(message: Mapping[str, Any], index: int) -> dict[str, Any]:
    if not isinstance(message, Mapping):
        raise ValueError(f"messages[{index}] must be an object")

    message_id = first_present(message, ("message_id", "id", "mid", "turn_id"), "message_id", index)
    sender_id = first_present(
        message,
        ("sender_id", "sender", "user_id", "author_id", "speaker", "from"),
        "sender_id",
        index,
    )
    text = first_present(message, ("message", "text", "content", "body"), "message", index)

    normalized = {
        "message_id": str(message_id),
        "timestamp": str(message.get("timestamp", message.get("created_at", ""))),
        "sender_id": str(sender_id),
        "message": str(text),
    }

    copied_keys = {
        "message_id",
        "id",
        "mid",
        "turn_id",
        "timestamp",
        "created_at",
        "sender_id",
        "sender",
        "user_id",
        "author_id",
        "speaker",
        "from",
        "message",
        "text",
        "content",
        "body",
    }
    for key, value in message.items():
        if key not in copied_keys and key not in normalized:
            normalized[str(key)] = value
    return normalized


def first_present(message: Mapping[str, Any], keys: tuple[str, ...], label: str, index: int) -> Any:
    for key in keys:
        value = message.get(key)
        if value is not None and value != "":
            return value
    raise ValueError(f"messages[{index}] is missing a required {label!r} field")


def get_response_output_text(response: Any) -> str:
    output_text = getattr(response, "output_text", None)
    if isinstance(output_text, str) and output_text.strip():
        return output_text

    output = getattr(response, "output", None)
    if output:
        parts = []
        for item in output:
            for content in getattr(item, "content", []) or []:
                text = getattr(content, "text", None)
                if isinstance(text, str):
                    parts.append(text)
        if parts:
            return "".join(parts)
    raise ValueError("OpenAI response did not contain output_text")


def extract_json_object(text: str) -> dict[str, Any]:
    stripped = text.strip()
    if stripped.startswith("```"):
        stripped = re.sub(r"^```(?:json)?\s*", "", stripped)
        stripped = re.sub(r"\s*```$", "", stripped)
    try:
        parsed = json.loads(stripped)
    except json.JSONDecodeError:
        start = stripped.find("{")
        end = stripped.rfind("}")
        if start < 0 or end < start:
            raise
        parsed = json.loads(stripped[start : end + 1])
    if not isinstance(parsed, dict):
        raise ValueError("Expected model output to be a JSON object")
    return parsed


def validate_analysis_output(parsed: dict[str, Any]) -> dict[str, Any]:
    required = set(CYBERBULLYING_ANALYSIS_SCHEMA["required"])
    missing = sorted(required - set(parsed))
    if missing:
        raise ValueError(f"Analysis JSON is missing required keys: {missing}")

    if not isinstance(parsed["is_suspected_cyberbullying"], bool):
        raise ValueError("is_suspected_cyberbullying must be a boolean")

    confidence = parsed["confidence"]
    if not isinstance(confidence, int | float) or isinstance(confidence, bool):
        raise ValueError("confidence must be a number")
    if not 0 <= float(confidence) <= 1:
        raise ValueError("confidence must be between 0 and 1")
    parsed["confidence"] = float(confidence)

    if parsed["severity"] not in SEVERITIES:
        raise ValueError(f"Invalid severity: {parsed['severity']!r}")

    ensure_string_list(parsed["target_user_ids"], "target_user_ids")
    ensure_string_list(parsed["suspected_actor_user_ids"], "suspected_actor_user_ids")
    ensure_string_list(parsed["uncertainty"], "uncertainty")
    ensure_string_list(parsed["recommended_next_steps"], "recommended_next_steps")

    if not isinstance(parsed["categories"], list):
        raise ValueError("categories must be a list")
    for index, category in enumerate(parsed["categories"]):
        ensure_object_keys(category, ("label", "evidence_strength", "message_ids", "why"), f"categories[{index}]")
        if category["label"] not in CATEGORY_LABELS:
            raise ValueError(f"Invalid category label: {category['label']!r}")
        if category["evidence_strength"] not in EVIDENCE_STRENGTHS:
            raise ValueError(f"Invalid evidence_strength: {category['evidence_strength']!r}")
        ensure_string_list(category["message_ids"], f"categories[{index}].message_ids")
        if not isinstance(category["why"], str):
            raise ValueError(f"categories[{index}].why must be a string")

    if not isinstance(parsed["evidence"], list):
        raise ValueError("evidence must be a list")
    for index, evidence in enumerate(parsed["evidence"]):
        ensure_object_keys(
            evidence,
            ("message_ids", "category", "sanitized_excerpt", "why_it_matters"),
            f"evidence[{index}]",
        )
        ensure_string_list(evidence["message_ids"], f"evidence[{index}].message_ids")
        if evidence["category"] not in CATEGORY_LABELS:
            raise ValueError(f"Invalid evidence category: {evidence['category']!r}")
        if not isinstance(evidence["sanitized_excerpt"], str):
            raise ValueError(f"evidence[{index}].sanitized_excerpt must be a string")
        if not isinstance(evidence["why_it_matters"], str):
            raise ValueError(f"evidence[{index}].why_it_matters must be a string")

    ensure_object_keys(
        parsed["pattern_analysis"],
        ("is_targeted", "is_repeated", "shows_escalation", "has_power_or_group_dynamic", "notes"),
        "pattern_analysis",
    )
    for key in ("is_targeted", "is_repeated", "shows_escalation", "has_power_or_group_dynamic"):
        if not isinstance(parsed["pattern_analysis"][key], bool):
            raise ValueError(f"pattern_analysis.{key} must be a boolean")
    if not isinstance(parsed["pattern_analysis"]["notes"], str):
        raise ValueError("pattern_analysis.notes must be a string")

    if not isinstance(parsed["explanation_for_target"], str):
        raise ValueError("explanation_for_target must be a string")
    return parsed


def ensure_object_keys(value: Any, keys: tuple[str, ...], label: str) -> None:
    if not isinstance(value, dict):
        raise ValueError(f"{label} must be an object")
    missing = sorted(set(keys) - set(value))
    if missing:
        raise ValueError(f"{label} is missing required keys: {missing}")


def ensure_string_list(value: Any, label: str) -> None:
    if not isinstance(value, list) or any(not isinstance(item, str) for item in value):
        raise ValueError(f"{label} must be a list of strings")


__all__ = [
    "CATEGORY_LABELS",
    "CYBERBULLYING_ANALYSIS_SCHEMA",
    "CYBERBULLYING_ANALYST_PROMPT",
    "Layer3",
]
