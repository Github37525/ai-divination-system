"""SQLite 审计日志与应验反馈存储。"""
from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Union


FEEDBACK_STATUSES = frozenset({"pending", "verified", "unverified", "partial"})


class AuditTracker:
    """以每次操作独立连接的方式安全保存、查询运行记录。"""

    def __init__(self, db_file: Optional[Union[str, Path]] = None):
        self.db_file = Path(db_file) if db_file else (
            Path(__file__).resolve().parents[1] / "data" / "audit_history.sqlite3"
        )
        self.db_file.parent.mkdir(parents=True, exist_ok=True)
        self._initialize_schema()

    @contextmanager
    def _connect(self):
        connection = sqlite3.connect(self.db_file, timeout=5)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute("PRAGMA busy_timeout = 5000")
        try:
            with connection:
                yield connection
        finally:
            connection.close()

    def _initialize_schema(self) -> None:
        with self._connect() as connection:
            connection.execute("PRAGMA journal_mode = WAL")
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS runs (
                    run_id TEXT PRIMARY KEY,
                    created_at TEXT NOT NULL,
                    user_query TEXT NOT NULL,
                    raw_input_json TEXT NOT NULL,
                    paipan_data_json TEXT NOT NULL,
                    ai_context_json TEXT NOT NULL,
                    guardrail_log_json TEXT NOT NULL,
                    llm_response TEXT NOT NULL,
                    llm_metadata_json TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS feedback (
                    run_id TEXT PRIMARY KEY REFERENCES runs(run_id) ON DELETE CASCADE,
                    status TEXT NOT NULL CHECK (
                        status IN ('pending', 'verified', 'unverified', 'partial')
                    ),
                    notes TEXT NOT NULL DEFAULT '',
                    updated_at TEXT
                );
                CREATE INDEX IF NOT EXISTS idx_runs_created_at
                    ON runs(created_at DESC);
                """
            )

    @staticmethod
    def _dump(value: Any) -> str:
        return json.dumps(value, ensure_ascii=False, separators=(",", ":"))

    @staticmethod
    def _timestamp() -> str:
        return datetime.now(timezone.utc).isoformat(timespec="milliseconds")

    def save_run_record(
        self,
        run_id: str,
        user_query: str,
        raw_input: dict,
        paipan_data: dict,
        ai_context: dict,
        llm_response: str,
        guardrail_log: Optional[List[dict]] = None,
        llm_metadata: Optional[dict] = None,
    ) -> None:
        """原子写入完整链路；重复 run_id 会明确失败，不静默覆盖。"""
        if not isinstance(run_id, str) or not run_id.strip():
            raise ValueError("run_id 不能为空。")
        if not isinstance(user_query, str) or not user_query.strip():
            raise ValueError("user_query 不能为空。")
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO runs (
                    run_id, created_at, user_query, raw_input_json,
                    paipan_data_json, ai_context_json, guardrail_log_json,
                    llm_response, llm_metadata_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    run_id,
                    self._timestamp(),
                    user_query.strip(),
                    self._dump(raw_input),
                    self._dump(paipan_data),
                    self._dump(ai_context),
                    self._dump(guardrail_log or []),
                    llm_response,
                    self._dump(llm_metadata or {}),
                ),
            )
            connection.execute(
                "INSERT INTO feedback (run_id, status, notes, updated_at) VALUES (?, 'pending', '', NULL)",
                (run_id,),
            )

    def record_user_feedback(self, run_id: str, status: str, notes: str = "") -> bool:
        """更新应验、未应验、部分应验或尚无结果状态。"""
        if status not in FEEDBACK_STATUSES:
            raise ValueError("非法应验状态标记。")
        if not isinstance(notes, str):
            raise ValueError("反馈说明必须是字符串。")
        updated_at = None if status == "pending" and not notes else self._timestamp()
        with self._connect() as connection:
            cursor = connection.execute(
                "UPDATE feedback SET status = ?, notes = ?, updated_at = ? WHERE run_id = ?",
                (status, notes.strip(), updated_at, run_id),
            )
        return cursor.rowcount == 1

    @staticmethod
    def _decode_row(row: sqlite3.Row, include_payload: bool = True) -> Dict[str, Any]:
        result: Dict[str, Any] = {
            "run_id": row["run_id"],
            "created_at": row["created_at"],
            "user_query": row["user_query"],
            "llm_response": row["llm_response"],
            "feedback": {
                "status": row["feedback_status"],
                "notes": row["feedback_notes"],
                "updated_at": row["feedback_updated_at"],
            },
        }
        if include_payload:
            result.update(
                raw_input=json.loads(row["raw_input_json"]),
                paipan_data=json.loads(row["paipan_data_json"]),
                ai_context=json.loads(row["ai_context_json"]),
                guardrail_log=json.loads(row["guardrail_log_json"]),
                llm_metadata=json.loads(row["llm_metadata_json"]),
            )
        return result

    def get_run(self, run_id: str) -> Optional[Dict[str, Any]]:
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT runs.*, feedback.status AS feedback_status,
                       feedback.notes AS feedback_notes,
                       feedback.updated_at AS feedback_updated_at
                FROM runs JOIN feedback USING (run_id)
                WHERE run_id = ?
                """,
                (run_id,),
            ).fetchone()
        return self._decode_row(row) if row else None

    def list_history(self, limit: int = 20, offset: int = 0) -> List[Dict[str, Any]]:
        if type(limit) is not int or not 1 <= limit <= 100:
            raise ValueError("limit 必须是 1 到 100 的整数。")
        if type(offset) is not int or offset < 0:
            raise ValueError("offset 必须是非负整数。")
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT runs.*, feedback.status AS feedback_status,
                       feedback.notes AS feedback_notes,
                       feedback.updated_at AS feedback_updated_at
                FROM runs JOIN feedback USING (run_id)
                ORDER BY runs.created_at DESC, runs.run_id DESC
                LIMIT ? OFFSET ?
                """,
                (limit, offset),
            ).fetchall()
        return [self._decode_row(row, include_payload=False) for row in rows]
