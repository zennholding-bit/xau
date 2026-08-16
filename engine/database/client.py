"""
Tunn wrapper runt Supabase-klienten så resten av systemet
inte behöver bry sig om anslutningsdetaljer.
"""
from functools import lru_cache
from supabase import create_client, Client
from engine.config.settings import settings


@lru_cache(maxsize=1)
def get_db() -> Client:
    if not settings.SUPABASE_URL or not settings.SUPABASE_SERVICE_ROLE_KEY:
        raise RuntimeError(
            "SUPABASE_URL / SUPABASE_SERVICE_ROLE_KEY är inte satta. "
            "Kopiera .env.example till .env och fyll i värdena, "
            "eller sätt dem som GitHub Secrets."
        )
    return create_client(settings.SUPABASE_URL, settings.SUPABASE_SERVICE_ROLE_KEY)


def upsert(table: str, rows: list[dict], on_conflict: str | None = None) -> int:
    """Upsertar en lista rader. Returnerar antal rader som skickades."""
    if not rows:
        return 0
    db = get_db()
    query = db.table(table).upsert(rows, on_conflict=on_conflict) if on_conflict else db.table(table).upsert(rows)
    query.execute()
    return len(rows)


def insert(table: str, rows: list[dict]) -> list[dict]:
    if not rows:
        return []
    db = get_db()
    res = db.table(table).insert(rows).execute()
    return res.data


def log_run_start(run_type: str) -> int:
    db = get_db()
    res = db.table("system_runs").insert({"run_type": run_type, "status": "RUNNING"}).execute()
    return res.data[0]["id"]


def log_run_finish(run_id: int, status: str, items_processed: int = 0,
                    errors: list | None = None, log_summary: str = "") -> None:
    db = get_db()
    db.table("system_runs").update({
        "finished_at": "now()",
        "status": status,
        "items_processed": items_processed,
        "errors": errors or [],
        "log_summary": log_summary,
    }).eq("id", run_id).execute()
