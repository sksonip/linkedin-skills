"""Approval rendering and runtime enforcement for external write actions."""
from __future__ import annotations
import hashlib
import hmac
import json
import secrets
import time
from dataclasses import dataclass
from typing import Optional


APPROVAL_TTL_SECONDS = 10 * 60
_CONFIRMATIONS = {"yes", "y", "post", "publish", "approve", "approved"}
_ACTIVE_APPROVALS: dict[str, tuple[str, float]] = {}


class ApprovalError(PermissionError):
    """Raised when an external write lacks a valid, exact approval receipt."""


@dataclass(frozen=True)
class ApprovalReceipt:
    """Opaque, short-lived receipt bound to one exact external action."""

    receipt_id: str
    action_digest: str
    expires_at: float


def _digest_action(
    *, kind: str, draft_text: str, target_url: str, action_context: Optional[dict]
) -> str:
    canonical = json.dumps(
        {
            "kind": kind,
            "draft_text": draft_text,
            "target_url": target_url,
            "action_context": action_context or {},
        },
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def issue_approval(
    *,
    kind: str,
    draft_text: str,
    target_url: str,
    user_confirmation: str,
    action_context: Optional[dict] = None,
) -> ApprovalReceipt:
    """Issue a one-use receipt after the user explicitly confirms a shown draft.

    ``user_confirmation`` must be the user's verbatim confirmation from the
    current interaction. The receipt is bound to the content, target, kind and
    backend-relevant context, expires after ten minutes, and cannot be reused.
    """
    if user_confirmation.strip().lower() not in _CONFIRMATIONS:
        raise ApprovalError("explicit user confirmation is required")
    digest = _digest_action(
        kind=kind,
        draft_text=draft_text,
        target_url=target_url,
        action_context=action_context,
    )
    receipt_id = secrets.token_urlsafe(24)
    expires_at = time.monotonic() + APPROVAL_TTL_SECONDS
    _ACTIVE_APPROVALS[receipt_id] = (digest, expires_at)
    return ApprovalReceipt(receipt_id, digest, expires_at)


def consume_approval(
    receipt: Optional[ApprovalReceipt],
    *,
    kind: str,
    draft_text: str,
    target_url: str,
    action_context: Optional[dict] = None,
) -> None:
    """Validate and consume a receipt before an external write is attempted."""
    if not isinstance(receipt, ApprovalReceipt):
        raise ApprovalError("a valid approval receipt is required before publishing")
    stored = _ACTIVE_APPROVALS.pop(receipt.receipt_id, None)
    if stored is None:
        raise ApprovalError("approval receipt is invalid or has already been used")
    expected_digest, expires_at = stored
    if time.monotonic() > expires_at:
        raise ApprovalError("approval receipt has expired")
    if receipt.expires_at != expires_at or not hmac.compare_digest(
        receipt.action_digest, expected_digest
    ):
        raise ApprovalError("approval receipt has been altered")
    actual_digest = _digest_action(
        kind=kind,
        draft_text=draft_text,
        target_url=target_url,
        action_context=action_context,
    )
    if not hmac.compare_digest(expected_digest, actual_digest):
        raise ApprovalError("approved action does not match the requested publish action")


def render_approval_card(
    *,
    kind: str,  # "post" | "comment" | "reply" | "reaction"
    preview_text: str,
    target_url: Optional[str] = None,
    reaction_type: Optional[str] = None,
    char_count: Optional[int] = None,
    extra_context: Optional[dict] = None,
) -> str:
    """Format a standardized approval card for the user to review.

    The card MUST contain:
    - What the action is (post / comment / reply / reaction)
    - The full preview text
    - Target URL if applicable
    - A clear prompt: "reply YES to post or suggest edits"
    """
    lines = [f"## Draft ready for approval — {kind}", ""]
    if target_url:
        lines.append(f"**Target:** {target_url}")
    if reaction_type:
        lines.append(f"**Reaction:** `{reaction_type}`")
    if char_count is None:
        char_count = len(preview_text)
    lines.append(f"**Chars:** {char_count}")
    lines.append("")
    lines.append("**Preview:**")
    lines.append("")
    for pl in preview_text.splitlines() or [""]:
        lines.append(f"> {pl}")
    lines.append("")
    if extra_context:
        lines.append("**Context:**")
        for k, v in extra_context.items():
            lines.append(f"- **{k}**: {v}")
        lines.append("")
    lines.append("Reply **post** / **yes** to publish, or suggest edits.")
    return "\n".join(lines)
