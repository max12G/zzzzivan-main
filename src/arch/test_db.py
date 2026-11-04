import mysql.connector
from mysql.connector import Error

try:
    cnx = mysql.connector.connect(
        host="185.114.247.43",
        port=3306,
        database="sch688_vvedenie",
        user="sch688_vvedenie",
        password="Qwerty123",
        connection_timeout=5,
    )
    print("✅ Подключение OK")

    cur = cnx.cursor()
    cur.execute("SHOW TABLES")
    print("Таблицы:", [r[0] for r in cur.fetchall()])

    cur.execute("DESCRIBE users")
    print("Структура users:")
    for row in cur.fetchall():
        print("  ", row)

    cur.execute("SELECT COUNT(*) FROM users")
    print("Пользователей в базе:", cur.fetchone()[0])

    cur.close(); cnx.close()
except Error as e:
    print("❌ Ошибка БД:", e)
