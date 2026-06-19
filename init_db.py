import asyncio
import aiosqlite
import os

DB_NAME = os.path.join("/app/data", "bot.db")

async def create_tables():
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute("PRAGMA journal_mode=WAL")
        await db.execute("""
            CREATE TABLE IF NOT EXISTS users (
                user_id INTEGER PRIMARY KEY,
                username TEXT,
                registered_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS admin_channels (
                user_id INTEGER NOT NULL,
                channel_id INTEGER NOT NULL,
                channel_username TEXT,
                added_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY (user_id, channel_id),
                FOREIGN KEY (user_id) REFERENCES users (user_id)
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS contests (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                type TEXT CHECK(type IN ('classic', 'slots')) NOT NULL,
                title TEXT DEFAULT '',
                text TEXT,
                photo_file_id TEXT,
                channel_id INTEGER NOT NULL,
                message_id INTEGER,
                status TEXT DEFAULT 'active',
                created_by INTEGER NOT NULL,
                end_condition TEXT CHECK(end_condition IN ('time', 'participants')),
                end_value TEXT,
                winners_count INTEGER DEFAULT 1,
                slots_count INTEGER,
                winning_slot INTEGER,
                payment_required INTEGER DEFAULT 0,
                slot_price INTEGER DEFAULT 0,
                sponsor_channels TEXT DEFAULT '[]',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                finished_at TIMESTAMP,
                FOREIGN KEY (created_by) REFERENCES users (user_id)
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS participants (
                contest_id INTEGER NOT NULL,
                user_id INTEGER NOT NULL,
                joined_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY (contest_id, user_id),
                FOREIGN KEY (contest_id) REFERENCES contests (id),
                FOREIGN KEY (user_id) REFERENCES users (user_id)
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS slots (
                contest_id INTEGER NOT NULL,
                slot_number INTEGER NOT NULL,
                user_id INTEGER NOT NULL,
                payment_status INTEGER DEFAULT 1,
                PRIMARY KEY (contest_id, slot_number),
                FOREIGN KEY (contest_id) REFERENCES contests (id),
                FOREIGN KEY (user_id) REFERENCES users (user_id)
            )
        """)
        await db.commit()

if __name__ == "__main__":
    asyncio.run(create_tables())
