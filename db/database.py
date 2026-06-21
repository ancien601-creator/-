import aiosqlite
from config import DB_PATH


async def get_db() -> aiosqlite.Connection:
    return await aiosqlite.connect(DB_PATH)


async def init_db():
    async with aiosqlite.connect(DB_PATH) as db:
        await db.executescript("""
            CREATE TABLE IF NOT EXISTS admins (
                id INTEGER PRIMARY KEY,
                username TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS admin_channels (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                admin_id INTEGER NOT NULL,
                channel_id INTEGER NOT NULL,
                channel_title TEXT,
                channel_username TEXT,
                UNIQUE(admin_id, channel_id)
            );

            CREATE TABLE IF NOT EXISTS contests (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                admin_id INTEGER NOT NULL,
                type TEXT NOT NULL CHECK(type IN ('classic', 'slots')),
                title TEXT,
                text TEXT,
                photo_id TEXT,
                channel_id INTEGER NOT NULL,
                channel_username TEXT,
                message_id INTEGER,
                status TEXT NOT NULL DEFAULT 'active' CHECK(status IN ('active', 'finished')),
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

                -- Classic fields
                finish_condition TEXT CHECK(finish_condition IN ('time', 'count')),
                finish_value TEXT,
                winners_count INTEGER DEFAULT 1,
                button_text TEXT DEFAULT 'Участвовать',

                -- Slots fields
                total_slots INTEGER,
                max_attempts INTEGER DEFAULT 1,
                payment_type TEXT CHECK(payment_type IN ('free', 'paid')),
                slot_price REAL,
                currency TEXT DEFAULT 'XTR',
                winning_slot INTEGER,
                show_count INTEGER DEFAULT 0
            );

            CREATE TABLE IF NOT EXISTS contest_sponsors (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                contest_id INTEGER NOT NULL,
                channel_username TEXT NOT NULL,
                channel_id INTEGER,
                FOREIGN KEY(contest_id) REFERENCES contests(id)
            );

            CREATE TABLE IF NOT EXISTS participants (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                contest_id INTEGER NOT NULL,
                user_id INTEGER NOT NULL,
                username TEXT,
                full_name TEXT,
                joined_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(contest_id, user_id),
                FOREIGN KEY(contest_id) REFERENCES contests(id)
            );

            CREATE TABLE IF NOT EXISTS slots (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                contest_id INTEGER NOT NULL,
                slot_number INTEGER NOT NULL,
                user_id INTEGER,
                username TEXT,
                full_name TEXT,
                payment_status TEXT DEFAULT 'pending' CHECK(payment_status IN ('pending', 'paid', 'free')),
                telegram_payment_charge_id TEXT,
                booked_at TIMESTAMP,
                UNIQUE(contest_id, slot_number),
                FOREIGN KEY(contest_id) REFERENCES contests(id)
            );
        """)
        # Migrate: add max_attempts if missing (for existing DBs)
        try:
            await db.execute("ALTER TABLE contests ADD COLUMN max_attempts INTEGER DEFAULT 1")
        except Exception:
            pass
        try:
            await db.execute("ALTER TABLE contests ADD COLUMN show_count INTEGER DEFAULT 0")
            await db.commit()
        except Exception:
            pass
        await db.commit()


# ──────────────────────── ADMINS ────────────────────────

async def upsert_admin(user_id: int, username: str):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "INSERT OR REPLACE INTO admins (id, username) VALUES (?, ?)",
            (user_id, username)
        )
        await db.commit()


async def get_admin_channels(admin_id: int) -> list[dict]:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT * FROM admin_channels WHERE admin_id = ?", (admin_id,)
        ) as cur:
            rows = await cur.fetchall()
            return [dict(r) for r in rows]


async def add_admin_channel(admin_id: int, channel_id: int, title: str, username: str):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            """INSERT OR REPLACE INTO admin_channels (admin_id, channel_id, channel_title, channel_username)
               VALUES (?, ?, ?, ?)""",
            (admin_id, channel_id, title, username)
        )
        await db.commit()


async def remove_admin_channel(admin_id: int, channel_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "DELETE FROM admin_channels WHERE admin_id = ? AND channel_id = ?",
            (admin_id, channel_id)
        )
        await db.commit()


# ──────────────────────── CONTESTS ────────────────────────

async def create_contest(data: dict) -> int:
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute(
            """INSERT INTO contests
               (admin_id, type, title, text, photo_id, channel_id, channel_username,
                finish_condition, finish_value, winners_count, button_text,
                total_slots, max_attempts, payment_type, slot_price, currency, winning_slot, show_count)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                data.get("admin_id"),
                data.get("type"),
                data.get("title"),
                data.get("text"),
                data.get("photo_id"),
                data.get("channel_id"),
                data.get("channel_username"),
                data.get("finish_condition"),
                data.get("finish_value"),
                data.get("winners_count"),
                data.get("button_text", "Участвовать"),
                data.get("total_slots"),
                data.get("max_attempts", 1),
                data.get("payment_type"),
                data.get("slot_price"),
                data.get("currency", "XTR"),
                data.get("winning_slot"),
                data.get("show_count", 0),
            )
        )
        await db.commit()
        return cur.lastrowid


async def set_contest_message_id(contest_id: int, message_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "UPDATE contests SET message_id = ? WHERE id = ?",
            (message_id, contest_id)
        )
        await db.commit()


async def get_contest(contest_id: int) -> dict | None:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT * FROM contests WHERE id = ?", (contest_id,)) as cur:
            row = await cur.fetchone()
            return dict(row) if row else None


async def get_admin_contests(admin_id: int, status: str = None) -> list[dict]:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        if status:
            async with db.execute(
                "SELECT * FROM contests WHERE admin_id = ? AND status = ? ORDER BY created_at DESC",
                (admin_id, status)
            ) as cur:
                rows = await cur.fetchall()
        else:
            async with db.execute(
                "SELECT * FROM contests WHERE admin_id = ? ORDER BY created_at DESC",
                (admin_id,)
            ) as cur:
                rows = await cur.fetchall()
        return [dict(r) for r in rows]


async def finish_contest(contest_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "UPDATE contests SET status = 'finished' WHERE id = ?",
            (contest_id,)
        )
        await db.commit()


# ──────────────────────── SPONSORS ────────────────────────

async def add_sponsor(contest_id: int, channel_username: str, channel_id: int = None):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "INSERT INTO contest_sponsors (contest_id, channel_username, channel_id) VALUES (?, ?, ?)",
            (contest_id, channel_username, channel_id)
        )
        await db.commit()


async def get_sponsors(contest_id: int) -> list[dict]:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT * FROM contest_sponsors WHERE contest_id = ?", (contest_id,)
        ) as cur:
            rows = await cur.fetchall()
            return [dict(r) for r in rows]


# ──────────────────────── PARTICIPANTS ────────────────────────

async def add_participant(contest_id: int, user_id: int, username: str, full_name: str) -> bool:
    async with aiosqlite.connect(DB_PATH) as db:
        try:
            await db.execute(
                """INSERT INTO participants (contest_id, user_id, username, full_name)
                   VALUES (?, ?, ?, ?)""",
                (contest_id, user_id, username, full_name)
            )
            await db.commit()
            return True
        except aiosqlite.IntegrityError:
            return False


async def get_participants(contest_id: int) -> list[dict]:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT * FROM participants WHERE contest_id = ?", (contest_id,)
        ) as cur:
            rows = await cur.fetchall()
            return [dict(r) for r in rows]


async def count_participants(contest_id: int) -> int:
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            "SELECT COUNT(*) FROM participants WHERE contest_id = ?", (contest_id,)
        ) as cur:
            row = await cur.fetchone()
            return row[0] if row else 0


async def is_participant(contest_id: int, user_id: int) -> bool:
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            "SELECT 1 FROM participants WHERE contest_id = ? AND user_id = ?",
            (contest_id, user_id)
        ) as cur:
            return await cur.fetchone() is not None


# ──────────────────────── SLOTS ────────────────────────

async def get_slot(contest_id: int, slot_number: int) -> dict | None:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT * FROM slots WHERE contest_id = ? AND slot_number = ?",
            (contest_id, slot_number)
        ) as cur:
            row = await cur.fetchone()
            return dict(row) if row else None


async def get_all_slots(contest_id: int) -> list[dict]:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT * FROM slots WHERE contest_id = ? ORDER BY slot_number",
            (contest_id,)
        ) as cur:
            rows = await cur.fetchall()
            return [dict(r) for r in rows]


async def count_user_slots(contest_id: int, user_id: int) -> int:
    """Count how many slots this user has booked in this contest."""
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            "SELECT COUNT(*) FROM slots WHERE contest_id = ? AND user_id = ?",
            (contest_id, user_id)
        ) as cur:
            row = await cur.fetchone()
            return row[0] if row else 0


async def book_slot(contest_id: int, slot_number: int, user_id: int,
                    username: str, full_name: str, payment_status: str = "free") -> bool:
    """Returns True if successfully booked, False if already taken."""
    async with aiosqlite.connect(DB_PATH) as db:
        existing = await db.execute(
            "SELECT user_id FROM slots WHERE contest_id = ? AND slot_number = ?",
            (contest_id, slot_number)
        )
        row = await existing.fetchone()
        if row and row[0] is not None:
            return False
        await db.execute(
            """INSERT INTO slots (contest_id, slot_number, user_id, username, full_name, payment_status, booked_at)
               VALUES (?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
               ON CONFLICT(contest_id, slot_number) DO UPDATE SET
               user_id = excluded.user_id,
               username = excluded.username,
               full_name = excluded.full_name,
               payment_status = excluded.payment_status,
               booked_at = excluded.booked_at
               WHERE slots.user_id IS NULL""",
            (contest_id, slot_number, user_id, username, full_name, payment_status)
        )
        await db.commit()
        async with db.execute(
            "SELECT user_id FROM slots WHERE contest_id = ? AND slot_number = ?",
            (contest_id, slot_number)
        ) as cur:
            row2 = await cur.fetchone()
            return row2 and row2[0] == user_id


async def set_slot_paid(contest_id: int, slot_number: int, charge_id: str):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            """UPDATE slots SET payment_status = 'paid', telegram_payment_charge_id = ?
               WHERE contest_id = ? AND slot_number = ?""",
            (charge_id, contest_id, slot_number)
        )
        await db.commit()


async def get_booked_slots_count(contest_id: int) -> int:
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            "SELECT COUNT(*) FROM slots WHERE contest_id = ? AND user_id IS NOT NULL",
            (contest_id,)
        ) as cur:
            row = await cur.fetchone()
            return row[0] if row else 0
