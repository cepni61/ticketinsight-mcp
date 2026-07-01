"""Seed script that creates data/tickets.db with realistic IT support data.

Creates three tables (categories, agents, tickets) and populates them with
sample records resembling a real IT helpdesk system.
"""

from __future__ import annotations

import sqlite3
import sys
from datetime import datetime, timedelta
from pathlib import Path

if sys.stdout.encoding is not None and sys.stdout.encoding.lower() != "utf-8":
    sys.stdout.reconfigure(encoding="utf-8")

DB_PATH = Path(__file__).parent / "tickets.db"

CATEGORIES: list[str] = [
    "Hardware",
    "Network",
    "Software",
    "Access Management",
    "Email",
    "Printer",
    "VPN",
]

AGENTS: list[tuple[str, str]] = [
    ("Ayse Kaya", "Service Desk"),
    ("Mehmet Demir", "Network Operations"),
    ("Elif Sahin", "Service Desk"),
    ("Burak Yildiz", "Infrastructure"),
    ("Zeynep Aydin", "Application Support"),
    ("Can Ozturk", "Network Operations"),
]

REQUESTERS: list[str] = [
    "Fatma Celik",
    "Ali Yilmaz",
    "Deniz Arslan",
    "Selin Kurt",
    "Emre Aksoy",
    "Gizem Polat",
    "Kerem Aslan",
    "Nur Cetin",
    "Onur Bulut",
    "Pelin Sari",
]

PRIORITIES: list[str] = ["Low", "Medium", "High", "Critical"]
STATUSES: list[str] = ["Open", "In Progress", "Resolved", "Closed"]

TICKET_TEMPLATES: list[tuple[str, str]] = [
    ("Laptop will not power on", "Hardware"),
    ("Monitor showing flickering screen", "Hardware"),
    ("Keyboard keys not responding", "Hardware"),
    ("Cannot connect to office Wi-Fi", "Network"),
    ("Network drive not accessible", "Network"),
    ("Slow internet connection in building B", "Network"),
    ("Excel crashes when opening large files", "Software"),
    ("Need software license activation", "Software"),
    ("Application update failing silently", "Software"),
    ("New employee needs system access", "Access Management"),
    ("Password reset request", "Access Management"),
    ("Access denied to shared folder", "Access Management"),
    ("Cannot send emails with attachments", "Email"),
    ("Mailbox storage full", "Email"),
    ("Suspicious phishing email received", "Email"),
    ("Printer on 3rd floor out of toner", "Printer"),
    ("Print jobs stuck in queue", "Printer"),
    ("Cannot install printer driver", "Printer"),
    ("VPN connection drops frequently", "VPN"),
    ("Unable to connect to VPN from home", "VPN"),
    ("VPN client update required", "VPN"),
    ("Blue screen error on startup", "Hardware"),
    ("Docking station not detected", "Hardware"),
    ("DNS resolution failing intermittently", "Network"),
    ("Software installation permission denied", "Software"),
    ("Account locked out after failed logins", "Access Management"),
    ("Outlook calendar not syncing", "Email"),
    ("Printer paper jam error persists", "Printer"),
    ("VPN certificate expired", "VPN"),
    ("External monitor resolution issue", "Hardware"),
    ("Shared mailbox permission request", "Email"),
    ("Firewall blocking internal application", "Network"),
]


def _random_datetime(base: datetime, day_offset: int, hour: int, minute: int) -> str:
    return (base + timedelta(days=day_offset, hours=hour, minutes=minute)).strftime(
        "%Y-%m-%d %H:%M:%S"
    )


def create_schema(conn: sqlite3.Connection) -> None:
    """Create the categories, agents, and tickets tables."""
    conn.executescript(
        """
        DROP TABLE IF EXISTS tickets;
        DROP TABLE IF EXISTS categories;
        DROP TABLE IF EXISTS agents;

        CREATE TABLE categories (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL UNIQUE
        );

        CREATE TABLE agents (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            team TEXT NOT NULL
        );

        CREATE TABLE tickets (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL,
            category_id INTEGER NOT NULL,
            priority TEXT NOT NULL,
            status TEXT NOT NULL,
            requester TEXT NOT NULL,
            assigned_to INTEGER NOT NULL,
            created_at TEXT NOT NULL,
            resolved_at TEXT,
            FOREIGN KEY (category_id) REFERENCES categories (id),
            FOREIGN KEY (assigned_to) REFERENCES agents (id)
        );
        """
    )


def seed_data(conn: sqlite3.Connection) -> None:
    """Insert sample categories, agents, and ticket records."""
    cursor = conn.cursor()

    cursor.executemany(
        "INSERT INTO categories (name) VALUES (?)",
        [(name,) for name in CATEGORIES],
    )
    category_ids = {
        name: cid
        for cid, name in cursor.execute("SELECT id, name FROM categories").fetchall()
    }

    cursor.executemany(
        "INSERT INTO agents (name, team) VALUES (?, ?)",
        AGENTS,
    )
    agent_ids = [row[0] for row in cursor.execute("SELECT id FROM agents").fetchall()]

    base = datetime(2026, 1, 5, 9, 0, 0)
    tickets: list[tuple] = []
    for i, (title, category_name) in enumerate(TICKET_TEMPLATES):
        category_id = category_ids[category_name]
        priority = PRIORITIES[i % len(PRIORITIES)]
        status = STATUSES[i % len(STATUSES)]
        requester = REQUESTERS[i % len(REQUESTERS)]
        assigned_to = agent_ids[i % len(agent_ids)]
        created_at = _random_datetime(base, day_offset=i, hour=i % 8, minute=(i * 7) % 60)

        resolved_at = None
        if status in ("Resolved", "Closed"):
            resolved_at = _random_datetime(
                base, day_offset=i + (1 + i % 3), hour=(i + 2) % 8, minute=(i * 11) % 60
            )

        tickets.append(
            (
                title,
                category_id,
                priority,
                status,
                requester,
                assigned_to,
                created_at,
                resolved_at,
            )
        )

    cursor.executemany(
        """
        INSERT INTO tickets (
            title, category_id, priority, status, requester,
            assigned_to, created_at, resolved_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        tickets,
    )
    conn.commit()


def main() -> None:
    """Build the SQLite database from scratch and seed it with sample data."""
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    try:
        create_schema(conn)
        seed_data(conn)
        ticket_count = conn.execute("SELECT COUNT(*) FROM tickets").fetchone()[0]
        print(f"Seeded {ticket_count} tickets into {DB_PATH}")
    finally:
        conn.close()


if __name__ == "__main__":
    main()
