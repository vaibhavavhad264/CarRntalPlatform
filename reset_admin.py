# Run this once:  python reset_admin.py
# It (re)creates the admin account:  ID = admin   Password = admin123
from werkzeug.security import generate_password_hash
from database import get_connection

conn = get_connection()
cur = conn.cursor()
cur.execute("DELETE FROM admins WHERE admin_username = 'admin'")
cur.execute("INSERT INTO admins (admin_username, password) VALUES (%s, %s)",
            ("admin", generate_password_hash("admin123")))
conn.commit()
cur.execute("SELECT admin_username FROM admins")
print("Admins in database:", [r[0] for r in cur.fetchall()])
print("Done. Admin ID = admin, Password = admin123")
cur.close(); conn.close()
