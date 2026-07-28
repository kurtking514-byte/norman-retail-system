from pydantic import BaseModel, ConfigDict


class MessagingEntry(BaseModel):
    model_config = ConfigDict(extra="allow")

    sender: dict
    recipient: dict
    timestamp: int
    message: dict | None = None
    postback: dict | None = None


class WebhookEntry(BaseModel):
    model_config = ConfigDict(extra="allow")

    id: str
    time: int
    messaging: list[MessagingEntry]


class WebhookPayload(BaseModel):
    model_config = ConfigDict(extra="allow")

    object: str
    entry: list[WebhookEntry]
