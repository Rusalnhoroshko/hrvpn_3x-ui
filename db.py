# db.py
import aiosqlite
import logging
from datetime import datetime, timedelta, timezone

DB_FILE = 'subscriptions.db'

async def init_db():
    async with aiosqlite.connect(DB_FILE) as db:
        await db.execute('''
            CREATE TABLE IF NOT EXISTS subscriptions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                key_id TEXT,
                access_url TEXT,
                expires_at TEXT,
                notified_5_days BOOLEAN DEFAULT 0,
                notified_1_day BOOLEAN DEFAULT 0,
                notified_expired BOOLEAN DEFAULT 0
            )
        ''')
        await db.execute('''
            CREATE TABLE IF NOT EXISTS test_usage (
                user_id INTEGER PRIMARY KEY,
                used_at TEXT
            )
        ''')
        await db.execute('''
            CREATE TABLE IF NOT EXISTS users (
                user_id INTEGER PRIMARY KEY,
                first_interaction TEXT
            )
        ''')
        await db.execute('''
            CREATE TABLE IF NOT EXISTS purchase_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                amount INTEGER,
                period INTEGER,
                action TEXT,
                purchase_date TEXT,
                label TEXT,
                operation_id TEXT
            )
        ''')

        await db.commit()

async def save_purchase_history(user_id, amount, period, action, label, operation_id):
    async with aiosqlite.connect(DB_FILE) as db:
        await db.execute('''
            INSERT INTO purchase_history (user_id, amount, period, action, label, purchase_date, operation_id)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        ''', (user_id, amount, period, action, label, datetime.now(timezone.utc).isoformat(), operation_id))
        await db.commit()
    logging.info(f"Purchase history for user {user_id} saved.")

async def add_user(user_id):
    async with aiosqlite.connect(DB_FILE) as db:
        await db.execute('''
            INSERT OR IGNORE INTO users (user_id, first_interaction)
            VALUES (?, ?)
        ''', (user_id, datetime.now(timezone.utc).isoformat()))
        await db.commit()

async def save_subscription(user_id, key_data, duration_days):
    expires_at = datetime.now(timezone.utc) + timedelta(days=duration_days)
    async with aiosqlite.connect(DB_FILE) as db:
        await db.execute('''
            INSERT INTO subscriptions (user_id, key_id, access_url, expires_at)
            VALUES (?, ?, ?, ?)
        ''', (user_id, key_data['id'], key_data['accessUrl'], expires_at.isoformat()))
        await db.commit()
    logging.info(f"Subscription for user {user_id} saved until {expires_at}")

async def get_subscriptions(user_id):
    async with aiosqlite.connect(DB_FILE) as db:
        cursor = await db.execute('''
            SELECT id, key_id, access_url, expires_at FROM subscriptions WHERE user_id = ?
        ''', (user_id,))
        rows = await cursor.fetchall()
        subscriptions = []
        for row in rows:
            sub_id, key_id, access_url, expires_at_str = row
            try:
                expires_at = datetime.fromisoformat(expires_at_str).replace(tzinfo=timezone.utc)
            except ValueError:
                expires_at = datetime.now(timezone.utc)
            subscriptions.append({
                'id': sub_id,
                'key_id': key_id,
                'access_url': access_url,
                'expires_at': expires_at
            })
        return subscriptions

async def delete_subscription(sub_id, user_id):
    async with aiosqlite.connect(DB_FILE) as db:
        await db.execute('''
            DELETE FROM subscriptions WHERE id = ?
        ''', (sub_id,))
        await db.commit()
    logging.info(f"Subscription {sub_id} for user {user_id} deleted")

async def extend_subscription(user_id, sub_id, additional_days):
    async with aiosqlite.connect(DB_FILE) as db:
        cursor = await db.execute('''
            SELECT expires_at FROM subscriptions
            WHERE id = ? AND user_id = ? LIMIT 1
        ''', (sub_id, user_id))
        row = await cursor.fetchone()
        if row:
            current_expires_at_str = row[0]
            current_expires_at = datetime.fromisoformat(current_expires_at_str).replace(tzinfo=timezone.utc)
            if current_expires_at > datetime.now(timezone.utc):
                new_expires_at = current_expires_at + timedelta(days=additional_days)
            else:
                new_expires_at = datetime.now(timezone.utc) + timedelta(days=additional_days)
            await db.execute('''
                UPDATE subscriptions SET expires_at = ?
                WHERE id = ? AND user_id = ?
            ''', (new_expires_at.isoformat(), sub_id, user_id))
            await db.commit()
            logging.info(f"Subscription {sub_id} for user {user_id} extended until {new_expires_at}")
        else:
            logging.error(f"Subscription {sub_id} for user {user_id} not found")

async def get_all_subscriptions():
    async with aiosqlite.connect(DB_FILE) as db:
        cursor = await db.execute('SELECT id, user_id, key_id, access_url, expires_at FROM subscriptions')
        rows = await cursor.fetchall()
        subscriptions = []
        for row in rows:
            sub_id, user_id, key_id, access_url, expires_at_str = row
            expires_at = datetime.fromisoformat(expires_at_str).replace(tzinfo=timezone.utc)
            subscriptions.append({
                'id': sub_id,
                'user_id': user_id,
                'key_id': key_id,
                'access_url': access_url,
                'expires_at': expires_at
            })
        return subscriptions

async def get_all_users():
    async with aiosqlite.connect(DB_FILE) as db:
        cursor = await db.execute('SELECT user_id FROM users')
        users = await cursor.fetchall()
        return [{'user_id': row[0]} for row in users]

async def update_subscription_async(sub_id, new_expires_at):
    async with aiosqlite.connect(DB_FILE) as db:
        await db.execute('UPDATE subscriptions SET expires_at = ? WHERE id = ?', (new_expires_at, sub_id))
        await db.commit()

async def get_subscription_expiry_async(sub_id):
    async with aiosqlite.connect(DB_FILE) as db:
        cursor = await db.execute('SELECT expires_at FROM subscriptions WHERE id = ?', (sub_id,))
        row = await cursor.fetchone()
        return row[0] if row else None

async def delete_subscription_async(sub_id):
    async with aiosqlite.connect(DB_FILE) as db:
        await db.execute('DELETE FROM subscriptions WHERE id = ?', (sub_id,))
        await db.commit()
