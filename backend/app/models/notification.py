import datetime

from sqlalchemy import Column, DateTime, Integer, JSON, String, Text

from app.models.base import Base


class ConversationLog(Base):
    __tablename__ = "conversation_logs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    messenger_user_id = Column(String(100), nullable=False, index=True)
    # Speaker allowed values: User, Bot, Staff
    speaker = Column(String(50), nullable=False)
    message_text = Column(Text)
    payload = Column(JSON, nullable=True)
    timestamp = Column(DateTime, default=datetime.datetime.now)


class NotificationQueue(Base):
    __tablename__ = "notification_queue"

    id = Column(Integer, primary_key=True, autoincrement=True)
    recipient_id = Column(String(100))
    # Channel allowed values: SMS, Messenger, Dashboard
    channel = Column(String(50))
    payload = Column(JSON, nullable=False)
    # Status allowed values: Pending, Sent, Failed
    status = Column(String(50), default="Pending", index=True)
    created_at = Column(DateTime, default=datetime.datetime.now)
