# app/core/schemas.py
from dataclasses import dataclass, field, asdict
from typing import List, Optional

@dataclass
class ChatAuthor:
    id: str
    name: str
    avatar_url: Optional[str] = None
    is_mod: bool = False
    is_sub: bool = False
    is_owner: bool = False
    badges: List[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return asdict(self)

@dataclass
class ChatMessage:
    id: str                  # Уникальный ID сообщения с платформы
    platform: str            # "twitch", "youtube", "kick", etc.
    author: ChatAuthor
    text: str
    timestamp: int           # UNIX-время в миллисекундах

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "platform": self.platform,
            "author": self.author.to_dict(),
            "text": self.text,
            "timestamp": self.timestamp
        }
