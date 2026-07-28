"""
Pydantic schemas for conversation threads, messages, and replies.
"""

from typing import Optional

from pydantic import BaseModel, ConfigDict, field_validator


class ConversationThreadSummary(BaseModel):
    """Summary of one customer's conversation thread for the list view."""

    messenger_user_id: str
    customer_id: Optional[int] = None
    customer_name: Optional[str] = None
    last_message_text: Optional[str] = None
    last_message_timestamp: Optional[str] = None
    unread_handoff: bool = False
    thread_state: Optional[str] = "AI_CONTROLLED"
    thread_state_pinned: bool = False


class ConversationMessage(BaseModel):
    """A single message within a conversation thread."""

    id: int
    speaker: str
    message_text: Optional[str] = None
    timestamp: str

    model_config = ConfigDict(from_attributes=True)


class SendReplyRequest(BaseModel):
    """Payload for sending a manual staff reply to a customer."""

    message_text: str

    @field_validator("message_text")
    @classmethod
    def message_text_must_not_be_empty(cls, v: str) -> str:
        stripped = v.strip()
        if not stripped:
            raise ValueError("message_text must not be empty")
        return stripped


class NotificationResponse(BaseModel):
    """A notification queue item for the staff dashboard."""

    id: int
    recipient_id: Optional[str] = None
    channel: Optional[str] = None
    payload: Optional[dict] = None
    status: str
    created_at: str

    model_config = ConfigDict(from_attributes=True)


class NotificationUpdateRequest(BaseModel):
    """Update the status of a notification queue item."""

    status: str

    @field_validator("status")
    @classmethod
    def validate_status(cls, v: str) -> str:
        allowed = {"Pending", "Sent", "Resolved"}
        if v not in allowed:
            raise ValueError(
                f"Invalid status '{v}'. Must be one of: {', '.join(sorted(allowed))}"
            )
        return v

