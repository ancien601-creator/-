import aiosqlite
from config import DB_PATH


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
                type TEXT NOT NULL,
                title TEXT,
                text TEXT,
                photo_id TEXT,
                channel_id INTEGER NOT NULL,
                channel_username TEXT,
                message_id INTEGER,
                status TEXT NOT NULL DEFAULT 'active',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                finish_condition TEXT,
                finish_value TEXT,
                winners_count INTEGER DEFAULT 1,
                button_text TEXT DEFAULT 'Участвовать',
                show_count INTEGER DEFAULT 0,
                total_slots INTEGER,
                max_attempts INTEGER DEFAULT 1,
                payment_type TEXT,
                slot_price REAL,
                currency TEXT DEFAULT 'XTR',
                winning_slot INTEGER,
                participant_limit INTEGER,
                round1_minutes INTEGER,
                round2_minutes INTEGER,
                round3_minutes INTEGER,
                current_round INTEGER DEFAULT 0
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
                payment_status TEXT DEFAULT 'pending',
                telegram_payment_charge_id TEXT,
                booked_at TIMESTAMP,
                UNIQUE(contest_id, slot_number),
                FOREIGN KEY(contest_id) REFERENCES contests(id)
            );
            CREATE TABLE IF NOT EXISTS lottery_tickets (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                contest_id INTEGER NOT NULL,
                user_id INTEGER NOT NULL,
                username TEXT,
                full_name TEXT,
                quantity INTEGER DEFAULT 1,
                payment_status TEXT DEFAULT 'free',
                charge_id TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY(contest_id) REFERENCES contests(id)
            );
            CREATE TABLE IF NOT EXISTS battle_participants (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                contest_id INTEGER NOT NULL,
                user_id INTEGER NOT NULL,
                username TEXT,
                full_name TEXT,
                status TEXT DEFAULT 'active',
                joined_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(contest_id, user_id),
                FOREIGN KEY(contest_id) REFERENCES contests(id)
            );
            CREATE TABLE IF NOT EXISTS battle_votes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                contest_id INTEGER NOT NULL,
                round INTEGER NOT NULL,
                voter_id INTEGER NOT NULL,
                candidate_id INTEGER NOT NULL,
                voted_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(contest_id, round, voter_id),
                FOREIGN KEY(contest_id) REFERENCES contests(id)
            );
            CREATE TABLE IF NOT EXISTS battle_messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                contest_id INTEGER NOT NULL,
                round INTEGER NOT NULL,
                message_id INTEGER NOT NULL,
                candidate1_id INTEGER,
                candidate2_id INTEGER,
                FOREIGN KEY(contest_id) REFERENCES contests(id)
            );
        """)
        await db.commit()

        # Migrations for existing DBs
        migrations = [
            "ALTER TABLE contests ADD COLUMN show_count INTEGER DEFAULT 0",
            "ALTER TABLE contests ADD COLUMN participant_limit INTEGER",
            "ALTER TABLE contests ADD COLUMN round1_minutes INTEGER",
            "ALTER TABLE contests ADD COLUMN round2_minutes INTEGER",
            "ALTER TABLE contests ADD COLUMN round3_minutes INTEGER",
            "ALTER TABLE contests ADD COLUMN current_round INTEGER DEFAULT 0",
        ]
        for sql in migrations:
            try:
                await db.execute(sql)
                await db.commit()
            except Exception:
                pass


# ──────── ADMINS ────────

async def upsert_admin(user_id: int, username: str):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("INSERT OR REPLACE INTO admins (id, username) VALUES (?, ?)", (user_id, username))
        await db.commit()


async def get_admin_channels(admin_id: int) -> list[dict]:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT * FROM admin_channels WHERE admin_id = ?", (admin_id,)) as cur:
            return [dict(r) for r in await cur.fetchall()]


async def add_admin_channel(admin_id: int, channel_id: int, title: str, username: str):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "INSERT OR REPLACE INTO admin_channels (admin_id, channel_id, channel_title, channel_username) VALUES (?, ?, ?, ?)",
            (admin_id, channel_id, title, username)
        )
        await db.commit()


async def remove_admin_channel(admin_id: int, channel_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("DELETE FROM admin_channels WHERE admin_id = ? AND channel_id = ?", (admin_id, channel_id))
        await db.commit()


# ──────── CONTESTS ────────

async def create_contest(data: dict) -> int:
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute(
            """INSERT INTO contests
               (admin_id, type, title, text, photo_id, channel_id, channel_username,
                finish_condition, finish_value, winners_count, button_text, show_count,
                total_slots, max_attempts, payment_type, slot_price, currency, winning_slot,
                participant_limit, round1_minutes, round2_minutes, round3_minutes)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (
                data.get("admin_id"), data.get("type"), data.get("title"),
                data.get("text"), data.get("photo_id"), data.get("channel_id"),
                data.get("channel_username"), data.get("finish_condition"),
                data.get("finish_value"), data.get("winners_count"), data.get("button_text", "Участвовать"),
                data.get("show_count", 0), data.get("total_slots"), data.get("max_attempts", 1),
                data.get("payment_type"), data.get("slot_price"), data.get("currency", "XTR"),
                data.get("winning_slot"), data.get("participant_limit"),
                data.get("round1_minutes"), data.get("round2_minutes"), data.get("round3_minutes"),
            )
        )
        await db.commit()
        return cur.lastrowid


async def set_contest_message_id(contest_id: int, message_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("UPDATE contests SET message_id = ? WHERE id = ?", (message_id, contest_id))
        await db.commit()


async def set_contest_current_round(contest_id: int, round_num: int):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("UPDATE contests SET current_round = ? WHERE id = ?", (round_num, contest_id))
        await db.commit()


async def get_contest(contest_id: int) -> dict | None:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT * FROM contests WHERE id = ?", (contest_id,)) as cur:
            row = await cur.fetchone()
            return dict(row) if row else None


async def get_admin_contests(admin_id: int) -> list[dict]:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT * FROM contests WHERE admin_id = ? ORDER BY created_at DESC", (admin_id,)) as cur:
            return [dict(r) for r in await cur.fetchall()]


async def finish_contest(contest_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("UPDATE contests SET status = 'finished' WHERE id = ?", (contest_id,))
        await db.commit()


# ──────── SPONSORS ────────

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
        async with db.execute("SELECT * FROM contest_sponsors WHERE contest_id = ?", (contest_id,)) as cur:
            return [dict(r) for r in await cur.fetchall()]


# ──────── PARTICIPANTS (classic) ────────

async def add_participant(contest_id: int, user_id: int, username: str, full_name: str) -> bool:
    async with aiosqlite.connect(DB_PATH) as db:
        try:
            await db.execute(
                "INSERT INTO participants (contest_id, user_id, username, full_name) VALUES (?, ?, ?, ?)",
                (contest_id, user_id, username, full_name)
            )
            await db.commit()
            return True
        except aiosqlite.IntegrityError:
            return False


async def get_participants(contest_id: int) -> list[dict]:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT * FROM participants WHERE contest_id = ?", (contest_id,)) as cur:
            return [dict(r) for r in await cur.fetchall()]


async def count_participants(contest_id: int) -> int:
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("SELECT COUNT(*) FROM participants WHERE contest_id = ?", (contest_id,)) as cur:
            row = await cur.fetchone()
            return row[0] if row else 0


async def is_participant(contest_id: int, user_id: int) -> bool:
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("SELECT 1 FROM participants WHERE contest_id = ? AND user_id = ?", (contest_id, user_id)) as cur:
            return await cur.fetchone() is not None


# ──────── SLOTS ────────

async def get_slot(contest_id: int, slot_number: int) -> dict | None:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT * FROM slots WHERE contest_id = ? AND slot_number = ?", (contest_id, slot_number)) as cur:
            row = await cur.fetchone()
            return dict(row) if row else None


async def get_all_slots(contest_id: int) -> list[dict]:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT * FROM slots WHERE contest_id = ? ORDER BY slot_number", (contest_id,)) as cur:
            return [dict(r) for r in await cur.fetchall()]


async def count_user_slots(contest_id: int, user_id: int) -> int:
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("SELECT COUNT(*) FROM slots WHERE contest_id = ? AND user_id = ?", (contest_id, user_id)) as cur:
            row = await cur.fetchone()
            return row[0] if row else 0


async def book_slot(contest_id: int, slot_number: int, user_id: int, username: str, full_name: str, payment_status: str = "free") -> bool:
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("SELECT user_id FROM slots WHERE contest_id = ? AND slot_number = ?", (contest_id, slot_number)) as cur:
            row = await cur.fetchone()
        if row and row[0] is not None:
            return False
        await db.execute(
            """INSERT INTO slots (contest_id, slot_number, user_id, username, full_name, payment_status, booked_at)
               VALUES (?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
               ON CONFLICT(contest_id, slot_number) DO UPDATE SET
               user_id=excluded.user_id, username=excluded.username,
               full_name=excluded.full_name, payment_status=excluded.payment_status,
               booked_at=excluded.booked_at WHERE slots.user_id IS NULL""",
            (contest_id, slot_number, user_id, username, full_name, payment_status)
        )
        await db.commit()
        async with db.execute("SELECT user_id FROM slots WHERE contest_id = ? AND slot_number = ?", (contest_id, slot_number)) as cur:
            row2 = await cur.fetchone()
            return bool(row2 and row2[0] == user_id)


async def set_slot_paid(contest_id: int, slot_number: int, charge_id: str):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "UPDATE slots SET payment_status='paid', telegram_payment_charge_id=? WHERE contest_id=? AND slot_number=?",
            (charge_id, contest_id, slot_number)
        )
        await db.commit()


async def get_booked_slots_count(contest_id: int) -> int:
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("SELECT COUNT(*) FROM slots WHERE contest_id=? AND user_id IS NOT NULL", (contest_id,)) as cur:
            row = await cur.fetchone()
            return row[0] if row else 0


# ──────── LOTTERY TICKETS ────────

async def get_user_ticket_count(contest_id: int, user_id: int) -> int:
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            "SELECT COALESCE(SUM(quantity), 0) FROM lottery_tickets WHERE contest_id=? AND user_id=?",
            (contest_id, user_id)
        ) as cur:
            row = await cur.fetchone()
            return row[0] if row else 0


async def get_total_tickets(contest_id: int) -> int:
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            "SELECT COALESCE(SUM(quantity), 0) FROM lottery_tickets WHERE contest_id=?", (contest_id,)
        ) as cur:
            row = await cur.fetchone()
            return row[0] if row else 0


async def add_lottery_tickets(contest_id: int, user_id: int, username: str, full_name: str, quantity: int, payment_status: str = "free", charge_id: str = None):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "INSERT INTO lottery_tickets (contest_id, user_id, username, full_name, quantity, payment_status, charge_id) VALUES (?,?,?,?,?,?,?)",
            (contest_id, user_id, username, full_name, quantity, payment_status, charge_id)
        )
        await db.commit()


async def get_all_tickets_pool(contest_id: int) -> list[dict]:
    """Returns flat list with each ticket as a separate entry (for random draw)."""
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT * FROM lottery_tickets WHERE contest_id=? AND payment_status != 'pending'", (contest_id,)
        ) as cur:
            rows = [dict(r) for r in await cur.fetchall()]
    pool = []
    for row in rows:
        for _ in range(row["quantity"]):
            pool.append(row)
    return pool


# ──────── BATTLE ────────

async def add_battle_participant(contest_id: int, user_id: int, username: str, full_name: str) -> bool:
    async with aiosqlite.connect(DB_PATH) as db:
        try:
            await db.execute(
                "INSERT INTO battle_participants (contest_id, user_id, username, full_name) VALUES (?,?,?,?)",
                (contest_id, user_id, username, full_name)
            )
            await db.commit()
            return True
        except aiosqlite.IntegrityError:
            return False


async def get_battle_participants(contest_id: int, status: str = None) -> list[dict]:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        if status:
            async with db.execute(
                "SELECT * FROM battle_participants WHERE contest_id=? AND status=? ORDER BY joined_at",
                (contest_id, status)
            ) as cur:
                return [dict(r) for r in await cur.fetchall()]
        async with db.execute(
            "SELECT * FROM battle_participants WHERE contest_id=? ORDER BY joined_at", (contest_id,)
        ) as cur:
            return [dict(r) for r in await cur.fetchall()]


async def count_battle_participants(contest_id: int) -> int:
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("SELECT COUNT(*) FROM battle_participants WHERE contest_id=?", (contest_id,)) as cur:
            row = await cur.fetchone()
            return row[0] if row else 0


async def is_battle_participant(contest_id: int, user_id: int) -> bool:
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("SELECT 1 FROM battle_participants WHERE contest_id=? AND user_id=?", (contest_id, user_id)) as cur:
            return await cur.fetchone() is not None


async def eliminate_battle_participant(contest_id: int, user_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "UPDATE battle_participants SET status='eliminated' WHERE contest_id=? AND user_id=?",
            (contest_id, user_id)
        )
        await db.commit()


async def add_battle_vote(contest_id: int, round_num: int, voter_id: int, candidate_id: int) -> bool:
    """Returns True if vote recorded, False if already voted."""
    async with aiosqlite.connect(DB_PATH) as db:
        try:
            await db.execute(
                "INSERT INTO battle_votes (contest_id, round, voter_id, candidate_id) VALUES (?,?,?,?)",
                (contest_id, round_num, voter_id, candidate_id)
            )
            await db.commit()
            return True
        except aiosqlite.IntegrityError:
            return False


async def get_vote_count(contest_id: int, round_num: int, candidate_id: int) -> int:
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            "SELECT COUNT(*) FROM battle_votes WHERE contest_id=? AND round=? AND candidate_id=?",
            (contest_id, round_num, candidate_id)
        ) as cur:
            row = await cur.fetchone()
            return row[0] if row else 0


async def add_battle_message(contest_id: int, round_num: int, message_id: int, c1_id: int = None, c2_id: int = None):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "INSERT INTO battle_messages (contest_id, round, message_id, candidate1_id, candidate2_id) VALUES (?,?,?,?,?)",
            (contest_id, round_num, message_id, c1_id, c2_id)
        )
        await db.commit()


async def get_battle_messages(contest_id: int, round_num: int) -> list[dict]:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT * FROM battle_messages WHERE contest_id=? AND round=?", (contest_id, round_num)
        ) as cur:
            return [dict(r) for r in await cur.fetchall()]


async def delete_battle_messages_db(contest_id: int, round_num: int):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("DELETE FROM battle_messages WHERE contest_id=? AND round=?", (contest_id, round_num))
        await db.commit()
