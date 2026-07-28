from pydantic import BaseModel


class AIReplyResult(BaseModel):
    """Result from the Gemini AI reply generation.

    Attributes:
        reply_text: The text to send back to the customer (either AI-generated
            or a generic holding message if handoff is needed).
        needs_human_handoff: Whether this conversation should be escalated
            to a human staff member.
        handoff_reason: Human-readable explanation of why handoff was
            triggered (e.g. "Customer requested refund", "Customer asked
            about repair status").  ``None`` when no handoff is needed.
    """

    reply_text: str
    needs_human_handoff: bool
    handoff_reason: str | None = None
