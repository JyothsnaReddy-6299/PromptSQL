from sqlalchemy import Column, String, Text, DateTime
import json
from app.utils.tz_helper import get_ist_time
from app.database.connection import Base


class ClarificationSession(Base):
    __tablename__ = "clarification_sessions"

    id = Column(String(64), primary_key=True)  # unique UUID
    user_id = Column(String(50), nullable=False, index=True)
    original_question = Column(Text, nullable=False)
    table_name = Column(String(100), nullable=False)
    clarification_prompt = Column(Text, nullable=False)
    options_json = Column(Text, nullable=False)  # JSON array of options
    proposed_plan_json = Column(Text, nullable=True)  # JSON representation of base proposed plan
    expires_at = Column(DateTime, nullable=False)
    created_at = Column(DateTime, default=get_ist_time, nullable=False)

    def to_dict(self):
        def safe_json_load(raw, fallback):
            if not raw:
                return fallback
            try:
                return json.loads(raw)
            except Exception:
                return fallback

        return {
            "id": self.id,
            "user_id": self.user_id,
            "original_question": self.original_question,
            "table_name": self.table_name,
            "clarification_prompt": self.clarification_prompt,
            "options": safe_json_load(self.options_json, []),
            "proposed_plan": safe_json_load(self.proposed_plan_json, None),
            "expires_at": self.expires_at.isoformat() if self.expires_at else None,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }
