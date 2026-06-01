import json
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator

from app.config import get_settings


def _db_path() -> Path:
    path = get_settings().database_path
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


@contextmanager
def connect() -> Iterator[sqlite3.Connection]:
    connection = sqlite3.connect(_db_path())
    connection.row_factory = sqlite3.Row
    try:
        yield connection
        connection.commit()
    finally:
        connection.close()


def init_db() -> None:
    with connect() as connection:
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS analyses (
                id TEXT PRIMARY KEY,
                status TEXT NOT NULL,
                error TEXT,
                result_json TEXT,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS text_cache (
                cache_key TEXT PRIMARY KEY,
                text TEXT NOT NULL,
                metadata_json TEXT NOT NULL,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS cv_rewrites (
                id TEXT PRIMARY KEY,
                analysis_id TEXT NOT NULL,
                status TEXT NOT NULL,
                error TEXT,
                result_json TEXT,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
            """
        )


def create_analysis(analysis_id: str) -> None:
    with connect() as connection:
        connection.execute(
            "INSERT INTO analyses (id, status) VALUES (?, ?)",
            (analysis_id, "queued"),
        )


def update_analysis(
    analysis_id: str,
    status: str,
    *,
    error: str | None = None,
    result: dict[str, Any] | None = None,
) -> None:
    result_json = json.dumps(result, ensure_ascii=False) if result is not None else None
    with connect() as connection:
        connection.execute(
            """
            UPDATE analyses
            SET status = ?, error = ?, result_json = ?, updated_at = CURRENT_TIMESTAMP
            WHERE id = ?
            """,
            (status, error, result_json, analysis_id),
        )


def get_analysis(analysis_id: str) -> dict[str, Any] | None:
    with connect() as connection:
        row = connection.execute(
            "SELECT id, status, error, result_json FROM analyses WHERE id = ?",
            (analysis_id,),
        ).fetchone()
    if row is None:
        return None
    result = json.loads(row["result_json"]) if row["result_json"] else None
    return {"id": row["id"], "status": row["status"], "error": row["error"], "result": result}


def get_cached_text(cache_key: str) -> tuple[str, dict[str, Any]] | None:
    with connect() as connection:
        row = connection.execute(
            "SELECT text, metadata_json FROM text_cache WHERE cache_key = ?",
            (cache_key,),
        ).fetchone()
    if row is None:
        return None
    return row["text"], json.loads(row["metadata_json"])


def get_cached_text_value(cache_key: str) -> str | None:
    cached = get_cached_text(cache_key)
    return cached[0] if cached else None


def set_cached_text(cache_key: str, text: str, metadata: dict[str, Any]) -> None:
    with connect() as connection:
        connection.execute(
            """
            INSERT OR REPLACE INTO text_cache (cache_key, text, metadata_json)
            VALUES (?, ?, ?)
            """,
            (cache_key, text, json.dumps(metadata, ensure_ascii=False)),
        )


def save_cv_rewrite(
    rewrite_id: str,
    analysis_id: str,
    status: str,
    *,
    error: str | None = None,
    result: dict[str, Any] | None = None,
) -> None:
    result_json = json.dumps(result, ensure_ascii=False) if result is not None else None
    with connect() as connection:
        connection.execute(
            """
            INSERT OR REPLACE INTO cv_rewrites (id, analysis_id, status, error, result_json, updated_at)
            VALUES (?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
            """,
            (rewrite_id, analysis_id, status, error, result_json),
        )


def get_cv_rewrite(rewrite_id: str) -> dict[str, Any] | None:
    with connect() as connection:
        row = connection.execute(
            "SELECT id, analysis_id, status, error, result_json FROM cv_rewrites WHERE id = ?",
            (rewrite_id,),
        ).fetchone()
    if row is None:
        return None
    result = json.loads(row["result_json"]) if row["result_json"] else None
    return {
        "id": row["id"],
        "analysis_id": row["analysis_id"],
        "status": row["status"],
        "error": row["error"],
        "result": result,
    }
