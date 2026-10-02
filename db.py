import sqlite3
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone

from config import DB_PATH


def utcnow():
    return datetime.now(timezone.utc)


def iso(dt):
    return dt.isoformat(timespec="seconds")


@contextmanager
def conn():
    c = sqlite3.connect(DB_PATH, isolation_level=None)
    c.row_factory = sqlite3.Row
    c.execute("PRAGMA journal_mode=WAL")
    try:
        yield c
    finally:
        c.close()


def init():
    with conn() as c:
        c.executescript("""
            CREATE TABLE IF NOT EXISTS users (
                user_id     INTEGER PRIMARY KEY,
                username    TEXT,
                first_name  TEXT,
                first_seen  TEXT NOT NULL,
                total_stars INTEGER NOT NULL DEFAULT 0
            );

            CREATE TABLE IF NOT EXISTS purchases (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id     INTEGER NOT NULL,
                plan_id     TEXT NOT NULL,
                days        INTEGER NOT NULL,
                stars       INTEGER NOT NULL,
                charge_id   TEXT UNIQUE NOT NULL,
                started_at  TEXT NOT NULL,
                expires_at  TEXT NOT NULL,
                kicked      INTEGER NOT NULL DEFAULT 0
            );

            CREATE TABLE IF NOT EXISTS join_requests (
                user_id      INTEGER PRIMARY KEY,
                chat_id      INTEGER NOT NULL,
                requested_at TEXT NOT NULL
            );

            CREATE INDEX IF NOT EXISTS idx_purchases_user    ON purchases(user_id);
            CREATE INDEX IF NOT EXISTS idx_purchases_expires ON purchases(expires_at, kicked);
        """)


def upsert_user(user):
    with conn() as c:
        c.execute("""
            INSERT INTO users (user_id, username, first_name, first_seen)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(user_id) DO UPDATE SET
                username   = excluded.username,
                first_name = excluded.first_name
        """, (user.id, user.username, user.first_name, iso(utcnow())))


def add_stars(user_id, stars):
    with conn() as c:
        c.execute("UPDATE users SET total_stars = total_stars + ? WHERE user_id = ?",
                  (stars, user_id))


# def create_purchase(user_id, plan_id, days, stars, charge_id):
#     now = utcnow()
#     expires = now + timedelta(days=days)

#     active = get_active(user_id)
#     if active:
#         base = datetime.fromisoformat(active["expires_at"])
#         if base > now:
#             expires = base + timedelta(days=days)

#     with conn() as c:
#         cur = c.execute("""
#             INSERT INTO purchases (user_id, plan_id, days, stars, charge_id, started_at, expires_at)
#             VALUES (?, ?, ?, ?, ?, ?, ?)
#         """, (user_id, plan_id, days, stars, charge_id, iso(now), iso(expires)))
#         return cur.lastrowid



def create_purchase(user_id, plan_id, duration_seconds, stars, charge_id):
    now = utcnow()
    delta = timedelta(seconds=duration_seconds)

    expires = now + delta

    active = get_active(user_id)
    if active:
        base = datetime.fromisoformat(active["expires_at"])
        if base > now:
            expires = base + delta

    with conn() as c:
        cur = c.execute("""
            INSERT INTO purchases (user_id, plan_id, days, stars, charge_id, started_at, expires_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (user_id, plan_id, duration_seconds // 86400, stars, charge_id, iso(now), iso(expires)))
        return cur.lastrowid


def get_active(user_id):
    with conn() as c:
        return c.execute("""
            SELECT * FROM purchases
            WHERE user_id = ? AND expires_at > ?
            ORDER BY expires_at DESC LIMIT 1
        """, (user_id, iso(utcnow()))).fetchone()


def is_premium(user_id):
    return get_active(user_id) is not None


def get_expired():
    with conn() as c:
        return c.execute("""
            SELECT * FROM purchases
            WHERE expires_at <= ? AND kicked = 0
        """, (iso(utcnow()),)).fetchall()


def mark_kicked(pid):
    with conn() as c:
        c.execute("UPDATE purchases SET kicked = 1 WHERE id = ?", (pid,))


def all_paid_user_ids():
    with conn() as c:
        rows = c.execute("SELECT DISTINCT user_id FROM purchases").fetchall()
        return [r["user_id"] for r in rows]


def save_join_request(user_id, chat_id):
    with conn() as c:
        c.execute("""
            INSERT INTO join_requests (user_id, chat_id, requested_at)
            VALUES (?, ?, ?)
            ON CONFLICT(user_id) DO UPDATE SET
                chat_id = excluded.chat_id,
                requested_at = excluded.requested_at
        """, (user_id, chat_id, iso(utcnow())))


def get_join_request(user_id):
    with conn() as c:
        return c.execute("SELECT * FROM join_requests WHERE user_id = ?", (user_id,)).fetchone()


def clear_join_request(user_id):
    with conn() as c:
        c.execute("DELETE FROM join_requests WHERE user_id = ?", (user_id,))


def stats():
    with conn() as c:
        users     = c.execute("SELECT COUNT(*) AS n FROM users").fetchone()["n"]
        purchases = c.execute("SELECT COUNT(*) AS n FROM purchases").fetchone()["n"]
        stars     = c.execute("SELECT COALESCE(SUM(stars),0) AS n FROM purchases").fetchone()["n"]
        active    = c.execute(
            "SELECT COUNT(DISTINCT user_id) AS n FROM purchases WHERE expires_at > ?",
            (iso(utcnow()),)
        ).fetchone()["n"]
        return {"users": users, "purchases": purchases, "stars": int(stars), "active": active}