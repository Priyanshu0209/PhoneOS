import time
import json
import os
from typing import Dict, Any, List

class ErrorLearningSystem:
    """
    Bounded engineering-error pipeline: ERROR -> LOG -> CLASSIFY -> ROOT CAUSE -> PROPOSED FIX -> VERIFY.
    Classifies errors heuristically and logs them for operator review.
    Does not automatically rewrite flight-critical safety logic.
    """
    def __init__(self, db_path: str = "error_learning.json"):
        self.db_path = db_path
        self.history: List[Dict[str, Any]] = self._load()

    def _load(self) -> List[Dict[str, Any]]:
        if os.path.exists(self.db_path):
            try:
                with open(self.db_path, "r") as f:
                    return json.load(f)
            except Exception:
                pass
        return []

    def _save(self):
        try:
            with open(self.db_path, "w") as f:
                json.dump(self.history[-500:], f) # Keep bounded to last 500
        except Exception:
            pass

    def report_error(self, drone_id: str, subsystem: str, error_message: str, error_type: str = "EXCEPTION"):
        """
        Reports an error into the learning pipeline.
        """
        classification = self._classify_error(subsystem, error_message)
        
        record = {
            "timestamp": time.time(),
            "drone_id": drone_id,
            "subsystem": subsystem,
            "error_type": error_type,
            "error_message": error_message,
            "root_cause": classification["root_cause"],
            "proposed_fix": classification["proposed_fix"],
            "recovery": classification["recovery"],
            "result": "PENDING_VERIFICATION"
        }
        
        self.history.append(record)
        self._save()
        return record

    def _classify_error(self, subsystem: str, msg: str) -> Dict[str, str]:
        msg_lower = msg.lower()
        
        # Heuristic rules engine for known patterns
        if "timeout" in msg_lower and "mavsdk" in msg_lower:
            return {
                "root_cause": "MAVSDK connection to PX4 timed out.",
                "proposed_fix": "Verify UDP/Serial connection to Pixhawk. Restart telemetry module.",
                "recovery": "SYSTEM_RESTART"
            }
        elif "gps" in msg_lower or "gps_lost" in msg_lower or "no global position" in msg_lower:
            return {
                "root_cause": "GPS signal lost or HDOP too high.",
                "proposed_fix": "Move vehicle to open sky. Verify GPS antenna connection.",
                "recovery": "HOLD_OR_LAND"
            }
        elif "arm" in msg_lower and "rejected" in msg_lower:
            return {
                "root_cause": "PX4 Pre-arm checks failed.",
                "proposed_fix": "Review PX4 commander logs. Often caused by uncalibrated sensors or missing GPS.",
                "recovery": "MANUAL_INTERVENTION"
            }
        elif "battery" in msg_lower and ("low" in msg_lower or "critical" in msg_lower):
            return {
                "root_cause": "Battery voltage below safe threshold.",
                "proposed_fix": "Replace battery pack immediately.",
                "recovery": "RTL_OR_LAND"
            }
            
        # Default fallback
        return {
            "root_cause": "Unknown or unclassified subsystem exception.",
            "proposed_fix": "Review application logs and reproduce on bench.",
            "recovery": "MANUAL_INTERVENTION"
        }
