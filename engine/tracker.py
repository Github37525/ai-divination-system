"""
engine/tracker.py
提供 run_id 落库管理及事后“应验度”反馈打卡功能
"""
import json
import os
from datetime import datetime
from typing import Dict, Any, Optional

class AuditTracker:
    def __init__(self, db_file: str = "data/audit_history.json"):
        self.db_file = db_file
        self._ensure_db_exists()

    def _ensure_db_exists(self):
        if not os.path.exists(self.db_file):
            os.makedirs(os.path.dirname(self.db_file), exist_ok=True)
            with open(self.db_file, "w", encoding="utf-8") as f:
                json.dump({}, f)

    def save_run_record(self, run_id: str, user_query: str, raw_input: dict, paipan_data: dict, ai_context: dict, llm_response: str):
        """记录单次全链路运行日志"""
        with open(self.db_file, "r+", encoding="utf-8") as f:
            history = json.load(f)
            history[run_id] = {
                "created_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "user_query": user_query,
                "raw_input": raw_input,
                "paipan_data": paipan_data,
                "ai_context": ai_context,
                "llm_response": llm_response,
                "feedback": {
                    "status": "pending",  # pending, verified, unverified, partial
                    "notes": "",
                    "updated_at": None
                }
            }
            f.seek(0)
            json.dump(history, f, ensure_ascii=False, indent=2)
            f.truncate()

    def record_user_feedback(self, run_id: str, status: str, notes: str = "") -> bool:
        """
        用户事后“应验打卡”反馈接口
        :param status: 'verified'(应验), 'unverified'(未应验), 'partial'(部分应验)
        """
        if status not in ["verified", "unverified", "partial"]:
            raise ValueError("非法应验状态标记！")

        with open(self.db_file, "r+", encoding="utf-8") as f:
            history = json.load(f)
            if run_id not in history:
                return False
            
            history[run_id]["feedback"] = {
                "status": status,
                "notes": notes,
                "updated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            }
            f.seek(0)
            json.dump(history, f, ensure_ascii=False, indent=2)
            f.truncate()
            return True