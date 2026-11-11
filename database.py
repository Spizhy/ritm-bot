import aiosqlite
import os
import json

# Support Amvera Persistent Storage (/data) or fallback to local directory
DATA_DIR = os.getenv("DATA_PATH", "/data" if os.path.isdir("/data") and os.access("/data", os.W_OK) else os.path.dirname(__file__))
DB_PATH = os.path.join(DATA_DIR, "applications.db")

async def init_db():
    async with aiosqlite.connect(DB_PATH) as db:
        # 1. Таблица заявок на пилот
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

        # 2. Таблица администраторов
        await db.execute("""
            CREATE TABLE IF NOT EXISTS admins (
                user_id INTEGER PRIMARY KEY,
                username TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        # 3. Привязка Telegram-чатов к группам
        await db.execute("""
            CREATE TABLE IF NOT EXISTS group_chats (
                chat_id INTEGER PRIMARY KEY,
                group_name TEXT NOT NULL,
                chat_title TEXT,
                bound_by INTEGER,
                is_active INTEGER DEFAULT 1,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        # 4. Расписание групп
        await db.execute("""
            CREATE TABLE IF NOT EXISTS group_schedules (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                group_name TEXT NOT NULL,
                weekday TEXT NOT NULL,
                time_start TEXT NOT NULL,
                time_end TEXT NOT NULL,
                subject TEXT NOT NULL,
                room TEXT,
                teacher TEXT,
                week_type TEXT DEFAULT 'all',
                status TEXT DEFAULT 'PLANNED',
                note TEXT
            )
        """)

        # 5. Отмены и изменения пар (лог оповещений)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS cancellations (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                group_name TEXT NOT NULL,
                date_str TEXT,
                time_str TEXT,
                subject TEXT NOT NULL,
                status TEXT NOT NULL,
                reason TEXT,
                new_room TEXT,
                starosta_name TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        # 6. Студенты групп и перекличка
        await db.execute("""
            CREATE TABLE IF NOT EXISTS students (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                group_name TEXT NOT NULL,
                user_id INTEGER,
                full_name TEXT NOT NULL,
                username TEXT,
                status TEXT DEFAULT 'present',
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
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

        # Проверяем наличие демо-расписания для ИВТ-21
        async with db.execute("SELECT COUNT(*) FROM group_schedules WHERE group_name = 'ИВТ-21'") as cursor:
            count = (await cursor.fetchone())[0]
            if count == 0:
                demo_lessons = [
                    ('ИВТ-21', 'Пятница', '08:30', '10:00', 'Высшая математика', 'Ауд. 203', 'Иванов А. С.', 'all', 'CANCELLED', 'Преподаватель на научной конференции. Занятие будет перенесено.'),
                    ('ИВТ-21', 'Пятница', '10:15', '11:45', 'Программирование', 'Ауд. 108', 'Петров К. В.', 'all', 'PLANNED', 'Лабораторная работа №4. Принести ноутбуки.'),
                    ('ИВТ-21', 'Пятница', '12:15', '13:45', 'Базы данных', 'Ауд. 314', 'Сидорова М. А.', 'all', 'DEADLINE', 'Сдача курсового проекта до 23:59!'),
                    ('ИВТ-21', 'Понедельник', '09:00', '10:30', 'Физика', 'Ауд. 402', 'Соколов В. П.', 'all', 'PLANNED', ''),
                    ('ИВТ-21', 'Понедельник', '10:45', '12:15', 'История науки', 'Ауд. 101', 'Белова О. Н.', 'all', 'PLANNED', ''),
                    ('ИВТ-21', 'Вторник', '10:15', '11:45', 'Алгоритмы и структуры', 'Ауд. 210', 'Григорьев С. А.', 'all', 'PLANNED', ''),
                    ('ИВТ-21', 'Вторник', '12:15', '13:45', 'Физкультура', 'Спортзал', 'Миронов Д. Д.', 'all', 'PLANNED', ''),
                    ('ИВТ-21', 'Среда', '08:30', '10:00', 'Компьютерные сети', 'Ауд. 305', 'Николаев А. Е.', 'all', 'PLANNED', ''),
                    ('ИВТ-21', 'Среда', '10:15', '11:45', 'Компьютерные сети (лаб)', 'Ауд. 305', 'Николаев А. Е.', 'all', 'DEADLINE', ''),
                    ('ИВТ-21', 'Четверг', '10:15', '11:45', 'Архитектура ЭВМ', 'Ауд. 108', 'Ковалев П. С.', 'all', 'PLANNED', ''),
                    ('ИВТ-21', 'Четверг', '12:15', '13:45', 'Операционные системы', 'Ауд. 108', 'Ковалев П. С.', 'all', 'PLANNED', ''),
                ]
                await db.executemany("""
                    INSERT INTO group_schedules (group_name, weekday, time_start, time_end, subject, room, teacher, week_type, status, note)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, demo_lessons)

        await db.commit()

# ================= ЗАЯВКИ =================

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

# ================= ПРИВЯЗКА ЧАТОВ =================

async def bind_group_chat(chat_id: int, group_name: str, chat_title: str = "", bound_by: int = 0) -> bool:
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""
            INSERT INTO group_chats (chat_id, group_name, chat_title, bound_by, is_active)
            VALUES (?, ?, ?, ?, 1)
            ON CONFLICT(chat_id) DO UPDATE SET
                group_name = excluded.group_name,
                chat_title = excluded.chat_title,
                is_active = 1
        """, (chat_id, group_name.strip().upper(), chat_title, bound_by))
        await db.commit()
        return True

async def get_bound_group(chat_id: int) -> str | None:
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("SELECT group_name FROM group_chats WHERE chat_id = ? AND is_active = 1", (chat_id,)) as cursor:
            row = await cursor.fetchone()
            return row[0] if row else None

async def get_chats_by_group(group_name: str) -> list[int]:
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("SELECT chat_id FROM group_chats WHERE group_name = ? AND is_active = 1", (group_name.strip().upper(),)) as cursor:
            rows = await cursor.fetchall()
            return [row[0] for row in rows]

async def get_all_active_group_chats():
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT chat_id, group_name, chat_title FROM group_chats WHERE is_active = 1") as cursor:
            rows = await cursor.fetchall()
            return [dict(row) for row in rows]

# ================= РАСПИСАНИЕ И ОТМЕНЫ =================

async def get_group_schedule(group_name: str, weekday: str = None) -> list[dict]:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        if weekday:
            query = "SELECT * FROM group_schedules WHERE group_name = ? AND weekday = ? ORDER BY time_start ASC"
            params = (group_name.strip().upper(), weekday)
        else:
            query = "SELECT * FROM group_schedules WHERE group_name = ? ORDER BY id ASC"
            params = (group_name.strip().upper(),)

        async with db.execute(query, params) as cursor:
            rows = await cursor.fetchall()
            return [dict(row) for row in rows]

async def save_cancellation(data: dict) -> int:
    async with aiosqlite.connect(DB_PATH) as db:
        group = data.get("group_name", "").strip().upper()
        subject = data.get("subject", "")
        status = data.get("status", "CANCELLED")
        status_label = data.get("statusLabel", "ОТМЕНА")
        reason = data.get("reason", "")
        new_room = data.get("room", "")

        # Записываем в лог отмен
        cursor = await db.execute("""
            INSERT INTO cancellations (group_name, date_str, time_str, subject, status, reason, new_room, starosta_name)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            group,
            data.get("dateStr", "Сегодня"),
            data.get("time", ""),
            subject,
            status,
            reason,
            new_room,
            data.get("starosta", "")
        ))

        # Обновляем статус пары в текущем расписании
        await db.execute("""
            UPDATE group_schedules
            SET status = ?, note = ?
            WHERE group_name = ? AND subject LIKE ?
        """, (status, reason, group, f"%{subject}%"))

        await db.commit()
        return cursor.lastrowid

# ================= ПЕРЕКЛИЧКА В ЧАТЕ =================

async def register_chat_rollcall(group_name: str, user_id: int, full_name: str, username: str, status: str):
    async with aiosqlite.connect(DB_PATH) as db:
        group = group_name.strip().upper()
        # Проверяем, есть ли запись студента
        async with db.execute("SELECT id FROM students WHERE group_name = ? AND user_id = ?", (group, user_id)) as cursor:
            row = await cursor.fetchone()
            if row:
                await db.execute("""
                    UPDATE students
                    SET status = ?, full_name = ?, username = ?, updated_at = CURRENT_TIMESTAMP
                    WHERE id = ?
                """, (status, full_name, username, row[0]))
            else:
                await db.execute("""
                    INSERT INTO students (group_name, user_id, full_name, username, status)
                    VALUES (?, ?, ?, ?, ?)
                """, (group, user_id, full_name, username, status))
        await db.commit()

async def get_rollcall_summary(group_name: str) -> dict:
    async with aiosqlite.connect(DB_PATH) as db:
        group = group_name.strip().upper()
        counts = {'present': 0, 'late': 0, 'excuse': 0, 'absent': 0}
        async with db.execute("""
            SELECT status, COUNT(*) FROM students
            WHERE group_name = ?
            GROUP BY status
        """, (group,)) as cursor:
            rows = await cursor.fetchall()
            for st, cnt in rows:
                if st in counts:
                    counts[st] = cnt

        total = sum(counts.values())
        return {
            'total': total,
            'counts': counts,
            'attended': counts['present'] + counts['late'] + counts['excuse']
        }
