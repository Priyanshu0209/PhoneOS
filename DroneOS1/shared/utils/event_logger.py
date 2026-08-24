import json
import time
import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path

class EventLogger:
    def __init__(self, log_dir: str = "logs"):
        self.log_path = Path(log_dir) / "events.jsonl"
        self.log_path.parent.mkdir(parents=True, exist_ok=True)
        
        self.logger = logging.getLogger("EventLogger")
        self.logger.setLevel(logging.INFO)
        
        if not self.logger.handlers:
            # Max 10MB per file, 5 backups
            handler = RotatingFileHandler(self.log_path, maxBytes=10*1024*1024, backupCount=5)
            # Use raw message for JSONL
            handler.setFormatter(logging.Formatter('%(message)s'))
            self.logger.addHandler(handler)

    def log_event(self, source: str, severity: str, drone_id: str, event_type: str, message: str):
        event = {
            "timestamp": time.time(),
            "source": source,
            "severity": severity.upper(),
            "drone_id": drone_id,
            "event": event_type,
            "message": message
        }
        self.logger.info(json.dumps(event))

# Singleton instance
event_logger = EventLogger()
