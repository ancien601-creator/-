import aiosqlite
from config import DB_PATH

class Database:
    @staticmethod
    async def init_db():
        # НАДЁЖНОСТЬ: Получаем путь к папке и создаем её, если её нет
        db_dir = os.path.dirname(DB_PATH)
        if db_dir:
            os.makedirs(db_dir, exist_ok=True)

        async with aiosqlite.connect(DB_PATH) as db:
            # Таблица конкурсов
            await db.execute("""
                CREATE TABLE IF NOT EXISTS contests (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    chat_id TEXT,
                    text TEXT,
                    photo_id TEXT,
                    message_id INTEGER,
                    finish_type TEXT,
                    winners_count INTEGER,
                    button_text TEXT,
                    status TEXT DEFAULT 'active'
                )
            """)
            # Таблица спонсоров (обязательных каналов)
            await db.execute("""
                CREATE TABLE IF NOT EXISTS sponsors (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    contest_id INTEGER,
                    channel_id TEXT,
                    channel_username TEXT,
                    FOREIGN KEY(contest_id) REFERENCES contests(id) ON DELETE CASCADE
                )
            """)
            # Таблица участников
            await db.execute("""
                CREATE TABLE IF NOT EXISTS participants (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER,
                    contest_id INTEGER,
                    UNIQUE(user_id, contest_id),
                    FOREIGN KEY(contest_id) REFERENCES contests(id) ON DELETE CASCADE
                )
            """)
            await db.commit()

    @staticmethod
    async def add_contest(chat_id, text, photo_id, finish_type, winners_count, button_text):
        async with aiosqlite.connect(DB_PATH) as db:
            cursor = await db.execute(
                "INSERT INTO contests (chat_id, text, photo_id, finish_type, winners_count, button_text) VALUES (?, ?, ?, ?, ?, ?)",
                (str(chat_id), text, photo_id, finish_type, winners_count, button_text)
            )
            contest_id = cursor.lastrowid
            await db.commit()
            return contest_id

    @staticmethod
    async def update_contest_message(contest_id, message_id):
        async with aiosqlite.connect(DB_PATH) as db:
            await db.execute("UPDATE contests SET message_id = ? WHERE id = ?", (message_id, contest_id))
            await db.commit()

    @staticmethod
    async def add_sponsor(contest_id, channel_id, channel_username):
        async with aiosqlite.connect(DB_PATH) as db:
            await db.execute(
                "INSERT INTO sponsors (contest_id, channel_id, channel_username) VALUES (?, ?, ?)",
                (contest_id, str(channel_id), channel_username)
            )
            await db.commit()

    @staticmethod
    async def get_sponsors(contest_id):
        async with aiosqlite.connect(DB_PATH) as db:
            async with db.execute("SELECT channel_id, channel_username FROM sponsors WHERE contest_id = ?", (contest_id,)) as cursor:
                return await cursor.fetchall()

    @staticmethod
    async def get_contest(contest_id):
        async with aiosqlite.connect(DB_PATH) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute("SELECT * FROM contests WHERE id = ?", (contest_id,)) as cursor:
                return await cursor.fetchone()

    @staticmethod
    async def get_active_contests():
        async with aiosqlite.connect(DB_PATH) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute("SELECT * FROM contests WHERE status = 'active'") as cursor:
                return await cursor.fetchall()

    @staticmethod
    async def add_participant(user_id, contest_id):
        async with aiosqlite.connect(DB_PATH) as db:
            try:
                await db.execute("INSERT INTO participants (user_id, contest_id) VALUES (?, ?)", (user_id, contest_id))
                await db.commit()
                return True
            except aiosqlite.IntegrityError:
                return False  # Уже участвует

    @staticmethod
    async def get_participants(contest_id):
        async with aiosqlite.connect(DB_PATH) as db:
            async with db.execute("SELECT user_id FROM participants WHERE contest_id = ?", (contest_id,)) as cursor:
                rows = await cursor.fetchall()
                return [row[0] for row in rows]

    @staticmethod
    async def close_contest(contest_id):
        async with aiosqlite.connect(DB_PATH) as db:
            await db.execute("UPDATE contests SET status = 'finished' WHERE id = ?", (contest_id,))
            await db.commit()
