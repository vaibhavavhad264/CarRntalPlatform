import os, re
import mysql.connector
from werkzeug.security import generate_password_hash

def get_connection():
    return mysql.connector.connect(
        host="localhost",
        user="root",
        password="Pass@123",   # <-- ENTER YOUR MYSQL PASSWORD HERE
        database="rentcar",
    )

BASE = os.path.dirname(os.path.abspath(__file__))
# Real photos: put  <model-name>.jpg  in  static/images/cars  OR  static/images  (also .jpeg .png .webp)
# e.g. hyundai-creta.jpg   (older file names thar.jpg and bmw.jpg are still understood)
IMG_DIR = os.path.join(BASE, "static", "images")
PHOTO_DIRS = [os.path.join(IMG_DIR, "cars"), IMG_DIR]
ALIASES = {"mahindra-thar": ["thar"], "bmw-m3": ["bmw"], "renault-kwid": ["kwid"],
           "tempo-traveller": ["tempo-traveler", "tempo"]}
MIMES = {".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".png": "image/png", ".webp": "image/webp"}

def slug(model):
    return re.sub(r"[^a-z0-9]+", "-", model.lower()).strip("-")

def find_photo(model):
    names = [slug(model)] + ALIASES.get(slug(model), [])
    for folder in PHOTO_DIRS:
        for name in names:
            for ext in MIMES:
                path = os.path.join(folder, name + ext)
                if os.path.isfile(path):
                    return path
    return None

def seed_images():
    """Store each car's real photo INSIDE MySQL (car.image).
    Photo file = static/images/cars/<model-name>.jpg (or in static/images). Refreshed at every start."""
    conn = get_connection()
    cur = conn.cursor(dictionary=True)
    cur.execute("SELECT car_id, model, image_mime, (image IS NULL) AS no_img FROM car")
    missing = []
    for row in cur.fetchall():
        photo = find_photo(row["model"])
        if photo:
            with open(photo, "rb") as fh:
                data = fh.read()
            cur.execute("UPDATE car SET image=%s, image_mime=%s WHERE car_id=%s",
                        (data, MIMES[os.path.splitext(photo)[1].lower()], row["car_id"]))
        else:
            missing.append(slug(row["model"]) + ".jpg")
            if not row["no_img"] and row["image_mime"] == "image/svg+xml":
                cur.execute("UPDATE car SET image=NULL WHERE car_id=%s", (row["car_id"],))   # drop old drawings
    conn.commit()
    cur.close(); conn.close()
    if missing:
        print("No photo yet for:", ", ".join(missing), "(put them in static/images/cars)")

def ensure_admin():
    """Create the default admin (admin / admin123) if the admins table is empty."""
    conn = get_connection(); cur = conn.cursor()
    cur.execute("SELECT COUNT(*) FROM admins")
    if cur.fetchone()[0] == 0:
        cur.execute("INSERT INTO admins (admin_username, password) VALUES (%s,%s)",
                    ("admin", generate_password_hash("admin123")))
        conn.commit()
    cur.close(); conn.close()