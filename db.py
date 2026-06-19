import aiosqlite
import json
import os
from typing import Optional

DB_NAME = os.path.join(os.getenv("DATA_DIR", "/app/data"), "bot.db")

# --- Пользователи ---
async def add_user(user_id: int, username: Optional[str]):
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute(
            "INSERT OR IGNORE INTO users (user_id, username) VALUES (?, ?)",
            (user_id, username)
        )
        await db.commit()

async def is_admin(user_id: int) -> bool:
    """Администратор – если есть хотя бы один канал в admin_channels."""
    async with aiosqlite.connect(DB_NAME) as db:
        async with db.execute(
            "SELECT COUNT(*) FROM admin_channels WHERE user_id = ?",
            (user_id,)
        ) as cursor:
            row = await cursor.fetchone()
            return row[0] > 0

# --- Каналы администраторов ---
async def add_admin_channel(user_id: int, channel_id: int, channel_username: Optional[str]):
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute(
            "INSERT OR IGNORE INTO admin_channels (user_id, channel_id, channel_username) VALUES (?, ?, ?)",
            (user_id, channel_id, channel_username)
        )
        await db.commit()

async def remove_admin_channel(user_id: int, channel_id: int):
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute(
            "DELETE FROM admin_channels WHERE user_id = ? AND channel_id = ?",
            (user_id, channel_id)
        )
        await db.commit()

async def get_admin_channels(user_id: int) -> list[tuple[int, Optional[str]]]:
    async with aiosqlite.connect(DB_NAME) as db:
        async with db.execute(
            "SELECT channel_id, channel_username FROM admin_channels WHERE user_id = ?",
            (user_id,)
        ) as cursor:
            return await cursor.fetchall()

# --- Конкурсы ---
async def create_contest(data: dict) -> int:
    async with aiosqlite.connect(DB_NAME) as db:
        cols = ', '.join(data.keys())
        placeholders = ', '.join(['?' for _ in data])
        sql = f"INSERT INTO contests ({cols}) VALUES ({placeholders})"
        cursor = await db.execute(sql, tuple(data.values()))
        await db.commit()
        return cursor.lastrowid

async def get_contest(contest_id: int) -> Optional[dict]:
    async with aiosqlite.connect(DB_NAME) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT * FROM contests WHERE id = ?", (contest_id,)) as cursor:
            row = await cursor.fetchone()
            return dict(row) if row else None

async def update_contest(contest_id: int, **kwargs):
    async with aiosqlite.connect(DB_NAME) as db:
        sets = ', '.join([f"{k} = ?" for k in kwargs])
        values = list(kwargs.values()) + [contest_id]
        await db.execute(f"UPDATE contests SET {sets} WHERE id = ?", values)
        await db.commit()

async def get_active_contests_for_admin(user_id: int) -> list[dict]:
    async with aiosqlite.connect(DB_NAME) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT * FROM contests WHERE created_by = ? AND status = 'active'",
            (user_id,)
        ) as cursor:
            return [dict(row) for row in await cursor.fetchall()]

# --- Участники (classic) ---
async def add_participant(contest_id: int, user_id: int) -> bool:
    async with aiosqlite.connect(DB_NAME) as db:
        try:
            await db.execute(
                "INSERT INTO participants (contest_id, user_id) VALUES (?, ?)",
                (contest_id, user_id)
            )
            await db.commit()
            return True
        except aiosqlite.IntegrityError:
            return False

async def get_participants_count(contest_id: int) -> int:
    async with aiosqlite.connect(DB_NAME) as db:
        async with db.execute(
            "SELECT COUNT(*) FROM participants WHERE contest_id = ?",
            (contest_id,)
        ) as cursor:
            row = await cursor.fetchone()
            return row[0]

async def get_random_participants(contest_id: int, limit: int) -> list[int]:
    async with aiosqlite.connect(DB_NAME) as db:
        async with db.execute(
            "SELECT user_id FROM participants WHERE contest_id = ? ORDER BY RANDOM() LIMIT ?",
            (contest_id, limit)
        ) as cursor:
            rows = await cursor.fetchall()
            return [row[0] for row in rows]

# --- Слоты ---
async def reserve_slot(contest_id: int, slot_number: int, user_id: int) -> bool:
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute("BEGIN IMMEDIATE")
        try:
            async with db.execute(
                "SELECT user_id FROM slots WHERE contest_id = ? AND slot_number = ?",
                (contest_id, slot_number)
            ) as cursor:
                if await cursor.fetchone():
                    await db.rollback()
                    return False
            await db.execute(
                "INSERT INTO slots (contest_id, slot_number, user_id, payment_status) VALUES (?, ?, ?, 1)",
                (contest_id, slot_number, user_id)
            )
            await db.commit()
            return True
        except:
            await db.rollback()
            return False

async def get_slot_owner(contest_id: int, slot_number: int) -> Optional[int]:
    async with aiosqlite.connect(DB_NAME) as db:
        async with db.execute(
            "SELECT user_id FROM slots WHERE contest_id = ? AND slot_number = ?",
            (contest_id, slot_number)
        ) as cursor:
            row = await cursor.fetchone()
            return row[0] if row else None

async def get_occupied_slots(contest_id: int) -> dict[int, int]:
    async with aiosqlite.connect(DB_NAME) as db:
        async with db.execute(
            "SELECT slot_number, user_id FROM slots WHERE contest_id = ?",
            (contest_id,)
        ) as cursor:
            rows = await cursor.fetchall()
            return {row[0]: row[1] for row in rows}
