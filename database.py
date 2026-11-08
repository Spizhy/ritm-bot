import aiosqlite
import os

# Support Amvera Persistent Storage (/data) or fallback to local directory
DATA_DIR = os.getenv("DATA_PATH", "/data" if os.path.isdir("/data") and os.access("/data", os.W_OK) else os.path.dirname(__file__))
DB_PATH = os.path.join(DATA_DIR, "applications.db")

async def init_db():
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""
            CREATE TABLE IF NOT EXISTS applications (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                username TEXT,
                role TEXT,
                full_name TEXT,
                institution TEXT,
                faculty TEXT,
                group_name TEXT,
                students_count INTEGER,
                chat_platform TEXT,
                schedule_source TEXT,
                cancel_frequency TEXT,
                cancel_channel TEXT,
                curator_report TEXT,
                pilot_readiness TEXT,
                routine_info TEXT,
                contact TEXT,
                status TEXT DEFAULT 'pending',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS admins (
                user_id INTEGER PRIMARY KEY,
                username TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        # Ensure any missing columns exist if table was created in an older version
        existing_cols = []
        async with db.execute("PRAGMA table_info(applications)") as cursor:
            rows = await cursor.fetchall()
            existing_cols = [r[1] for r in rows]

        new_cols = {
            "faculty": "TEXT",
            "chat_platform": "TEXT",
            "schedule_source": "TEXT",
            "cancel_frequency": "TEXT",
            "cancel_channel": "TEXT",
            "curator_report": "TEXT",
            "pilot_readiness": "TEXT",
            "routine_info": "TEXT",
            "status": "TEXT DEFAULT 'pending'"
        }

        for col, col_type in new_cols.items():
            if col not in existing_cols:
                try:
                    await db.execute(f"ALTER TABLE applications ADD COLUMN {col} {col_type}")
                except Exception:
                    pass

        await db.commit()

async def save_application(data: dict) -> int:
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute("""
            INSERT INTO applications (
                user_id, username, role, full_name, institution, faculty,
                group_name, students_count, chat_platform, schedule_source,
                cancel_frequency, cancel_channel, curator_report, pilot_readiness,
                routine_info, contact, status
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'pending')
        """, (
            data.get("user_id"),
            data.get("username", ""),
            data.get("role", "Староста"),
            data.get("full_name", "Не указано"),
            data.get("institution", "Не указано"),
            data.get("faculty", ""),
            data.get("group_name", "Не указано"),
            data.get("students_count", 0),
            data.get("chat_platform", ""),
            data.get("schedule_source", ""),
            data.get("cancel_frequency", ""),
            data.get("cancel_channel", ""),
            data.get("curator_report", ""),
            data.get("pilot_readiness", ""),
            data.get("routine_info", ""),
            data.get("contact", "")
        ))
        await db.commit()
        return cursor.lastrowid

async def update_application_status(app_id: int, status: str) -> bool:
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("UPDATE applications SET status = ? WHERE id = ?", (status, app_id))
        await db.commit()
        return True

async def get_application_by_id(app_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT * FROM applications WHERE id = ?", (app_id,)) as cursor:
            row = await cursor.fetchone()
            return dict(row) if row else None

async def get_applications_count() -> int:
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("SELECT COUNT(*) FROM applications") as cursor:
            row = await cursor.fetchone()
            return row[0] if row else 0

async def get_recent_applications(limit: int = 10):
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("""
            SELECT id, user_id, username, role, full_name, institution,
                   group_name, students_count, status, created_at
            FROM applications
            ORDER BY id DESC
            LIMIT ?
        """, (limit,)) as cursor:
            rows = await cursor.fetchall()
            return [dict(row) for row in rows]

async def add_admin(user_id: int, username: str = ""):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""
            INSERT OR IGNORE INTO admins (user_id, username)
            VALUES (?, ?)
        """, (user_id, username))
        await db.commit()

async def get_admins() -> list[int]:
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("SELECT user_id FROM admins") as cursor:
            rows = await cursor.fetchall()
            return [row[0] for row in rows]
