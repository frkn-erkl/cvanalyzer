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
    connection = sqlite3.connect(_db_path(), timeout=10.0)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA journal_mode=WAL")
    connection.execute("PRAGMA busy_timeout=10000")
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
        _ensure_column(connection, "analyses", "progress_json", "TEXT")
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS llm_tasks (
                id TEXT PRIMARY KEY,
                kind TEXT NOT NULL,
                status TEXT NOT NULL,
                error TEXT,
                progress_json TEXT,
                result_json TEXT,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
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
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS skill_gap_listings (
                job_key TEXT PRIMARY KEY,
                job_url TEXT,
                job_title TEXT NOT NULL,
                company TEXT,
                source TEXT NOT NULL,
                first_seen_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                last_seen_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS skill_gap_items (
                job_key TEXT NOT NULL,
                skill_name TEXT NOT NULL,
                gap_type TEXT NOT NULL,
                PRIMARY KEY (job_key, skill_name, gap_type),
                FOREIGN KEY (job_key) REFERENCES skill_gap_listings(job_key) ON DELETE CASCADE
            )
            """
        )


def _ensure_column(connection: sqlite3.Connection, table: str, column: str, column_type: str) -> None:
    columns = {
        row["name"]
        for row in connection.execute(f"PRAGMA table_info({table})").fetchall()
    }
    if column not in columns:
        connection.execute(f"ALTER TABLE {table} ADD COLUMN {column} {column_type}")


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
    clear_progress: bool = True,
) -> None:
    result_json = json.dumps(result, ensure_ascii=False) if result is not None else None
    with connect() as connection:
        should_clear_progress = status == "running" or (status == "completed" and clear_progress)
        if should_clear_progress:
            connection.execute(
                """
                UPDATE analyses
                SET status = ?, error = ?, result_json = ?, progress_json = NULL, updated_at = CURRENT_TIMESTAMP
                WHERE id = ?
                """,
                (status, error, result_json, analysis_id),
            )
        else:
            connection.execute(
                """
                UPDATE analyses
                SET status = ?, error = ?, result_json = ?, updated_at = CURRENT_TIMESTAMP
                WHERE id = ?
                """,
                (status, error, result_json, analysis_id),
            )


def update_analysis_progress(analysis_id: str, progress: dict[str, Any]) -> None:
    progress_json = json.dumps(progress, ensure_ascii=False)
    with connect() as connection:
        connection.execute(
            """
            UPDATE analyses
            SET progress_json = ?, updated_at = CURRENT_TIMESTAMP
            WHERE id = ?
            """,
            (progress_json, analysis_id),
        )


def list_completed_analyses() -> list[dict[str, Any]]:
    with connect() as connection:
        rows = connection.execute(
            """
            SELECT id, result_json
            FROM analyses
            WHERE status = 'completed' AND result_json IS NOT NULL
            ORDER BY updated_at ASC
            """
        ).fetchall()
    results: list[dict[str, Any]] = []
    for row in rows:
        result = json.loads(row["result_json"])
        results.append({"id": row["id"], "result": result})
    return results


def get_skill_gap_job_keys() -> set[str]:
    with connect() as connection:
        rows = connection.execute("SELECT job_key FROM skill_gap_listings").fetchall()
    return {row["job_key"] for row in rows}


def get_analysis(analysis_id: str) -> dict[str, Any] | None:
    with connect() as connection:
        row = connection.execute(
            "SELECT id, status, error, result_json, progress_json FROM analyses WHERE id = ?",
            (analysis_id,),
        ).fetchone()
    if row is None:
        return None
    result = json.loads(row["result_json"]) if row["result_json"] else None
    progress = json.loads(row["progress_json"]) if row["progress_json"] else None
    return {
        "id": row["id"],
        "status": row["status"],
        "error": row["error"],
        "result": result,
        "progress": progress,
    }


def fail_stale_running_analyses(*, max_age_seconds: float) -> int:
    with connect() as connection:
        cursor = connection.execute(
            """
            UPDATE analyses
            SET status = 'failed',
                error = 'Analiz zaman aşımına uğradı veya sunucu yeniden başlatıldı.',
                progress_json = NULL,
                updated_at = CURRENT_TIMESTAMP
            WHERE status IN ('queued', 'running')
              AND updated_at < datetime('now', ?)
            """,
            (f"-{int(max_age_seconds)} seconds",),
        )
        return cursor.rowcount


def create_llm_task(task_id: str, kind: str) -> None:
    with connect() as connection:
        connection.execute(
            "INSERT INTO llm_tasks (id, kind, status) VALUES (?, ?, ?)",
            (task_id, kind, "queued"),
        )


def update_llm_task(
    task_id: str,
    status: str,
    *,
    error: str | None = None,
    result: dict[str, Any] | None = None,
    clear_progress: bool = True,
) -> None:
    result_json = json.dumps(result, ensure_ascii=False) if result is not None else None
    with connect() as connection:
        if status == "completed" and clear_progress:
            connection.execute(
                """
                UPDATE llm_tasks
                SET status = ?, error = ?, result_json = ?, progress_json = NULL, updated_at = CURRENT_TIMESTAMP
                WHERE id = ?
                """,
                (status, error, result_json, task_id),
            )
        else:
            connection.execute(
                """
                UPDATE llm_tasks
                SET status = ?, error = ?, result_json = ?, updated_at = CURRENT_TIMESTAMP
                WHERE id = ?
                """,
                (status, error, result_json, task_id),
            )


def update_llm_task_progress(task_id: str, progress: dict[str, Any]) -> None:
    progress_json = json.dumps(progress, ensure_ascii=False)
    with connect() as connection:
        connection.execute(
            """
            UPDATE llm_tasks
            SET progress_json = ?, updated_at = CURRENT_TIMESTAMP
            WHERE id = ?
            """,
            (progress_json, task_id),
        )


def get_llm_task(task_id: str) -> dict[str, Any] | None:
    with connect() as connection:
        row = connection.execute(
            "SELECT id, kind, status, error, progress_json, result_json FROM llm_tasks WHERE id = ?",
            (task_id,),
        ).fetchone()
    if row is None:
        return None
    progress = json.loads(row["progress_json"]) if row["progress_json"] else None
    result = json.loads(row["result_json"]) if row["result_json"] else None
    return {
        "id": row["id"],
        "kind": row["kind"],
        "status": row["status"],
        "error": row["error"],
        "progress": progress,
        "result": result,
    }


def fail_stale_running_llm_tasks(*, max_age_seconds: float) -> int:
    with connect() as connection:
        cursor = connection.execute(
            """
            UPDATE llm_tasks
            SET status = 'failed',
                error = 'LLM görevi zaman aşımına uğradı veya sunucu yeniden başlatıldı.',
                progress_json = NULL,
                updated_at = CURRENT_TIMESTAMP
            WHERE status IN ('queued', 'running')
              AND updated_at < datetime('now', ?)
            """,
            (f"-{int(max_age_seconds)} seconds",),
        )
        return cursor.rowcount


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


def upsert_skill_gap_listing(
    job_key: str,
    *,
    job_url: str | None,
    job_title: str,
    company: str | None,
    source: str,
) -> None:
    with connect() as connection:
        connection.execute(
            """
            INSERT INTO skill_gap_listings (job_key, job_url, job_title, company, source)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(job_key) DO UPDATE SET
                job_url = excluded.job_url,
                job_title = excluded.job_title,
                company = excluded.company,
                source = excluded.source,
                last_seen_at = CURRENT_TIMESTAMP
            """,
            (job_key, job_url, job_title, company, source),
        )


def replace_skill_gap_items(
    job_key: str,
    *,
    missing_required: list[str],
    missing_preferred: list[str],
) -> None:
    with connect() as connection:
        connection.execute("DELETE FROM skill_gap_items WHERE job_key = ?", (job_key,))
        for skill_name in missing_required:
            connection.execute(
                """
                INSERT OR IGNORE INTO skill_gap_items (job_key, skill_name, gap_type)
                VALUES (?, ?, 'required')
                """,
                (job_key, skill_name),
            )
        for skill_name in missing_preferred:
            connection.execute(
                """
                INSERT OR IGNORE INTO skill_gap_items (job_key, skill_name, gap_type)
                VALUES (?, ?, 'preferred')
                """,
                (job_key, skill_name),
            )


def get_skill_gap_summary_rows() -> list[dict[str, Any]]:
    with connect() as connection:
        rows = connection.execute(
            """
            SELECT
                i.skill_name,
                i.gap_type,
                COUNT(DISTINCT i.job_key) AS listing_count
            FROM skill_gap_items i
            GROUP BY i.skill_name, i.gap_type
            ORDER BY listing_count DESC, i.skill_name ASC
            """
        ).fetchall()
        aggregates: list[dict[str, Any]] = []
        for row in rows:
            listings = connection.execute(
                """
                SELECT l.job_key, l.job_url, l.job_title, l.company, l.source, l.last_seen_at
                FROM skill_gap_items i
                JOIN skill_gap_listings l ON l.job_key = i.job_key
                WHERE i.skill_name = ? AND i.gap_type = ?
                ORDER BY l.last_seen_at DESC
                """,
                (row["skill_name"], row["gap_type"]),
            ).fetchall()
            aggregates.append(
                {
                    "skill_name": row["skill_name"],
                    "gap_type": row["gap_type"],
                    "listing_count": row["listing_count"],
                    "listings": [dict(listing) for listing in listings],
                }
            )
        return aggregates


def clear_skill_gaps() -> None:
    with connect() as connection:
        connection.execute("DELETE FROM skill_gap_items")
        connection.execute("DELETE FROM skill_gap_listings")


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
