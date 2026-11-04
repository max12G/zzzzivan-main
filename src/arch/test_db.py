import os
import sqlite3


db_path = os.path.join(os.path.dirname(__file__), "data", "app.db")
os.makedirs(os.path.dirname(db_path), exist_ok=True)

try:
    cnx = sqlite3.connect(db_path)
    print(f"✅ Локальная БД доступна: {db_path}")

    cur = cnx.cursor()
    cur.execute("SELECT name FROM sqlite_master WHERE type = 'table'")
    print("Таблицы:", [row[0] for row in cur.fetchall()])

    cur.execute("PRAGMA table_info(users)")
    print("Структура users:")
    for row in cur.fetchall():
        print("  ", row)

    cur.execute("SELECT COUNT(*) FROM users")
    print("Пользователей в базе:", cur.fetchone()[0])

    cur.close()
    cnx.close()
except sqlite3.Error as error:
    print("❌ Ошибка локальной БД:", error)
