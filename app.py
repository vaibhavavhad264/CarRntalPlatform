import math, re
from datetime import datetime
from decimal import Decimal
from functools import wraps
import mysql.connector
from flask import (Flask, render_template, request, redirect, url_for,
                   session, flash, Response)
from werkzeug.security import generate_password_hash, check_password_hash
from database import get_connection, seed_images, ensure_admin

app = Flask(__name__)
# In production keep this in an environment variable, never hardcode it.
app.secret_key = "change-this-secret-key"

EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
FIRST_BOOKING_DISCOUNT = Decimal("0.30")
SORTS = {
    "price_asc": "price_per_hour ASC", "price_desc": "price_per_hour DESC",
    "rating_desc": "rating DESC", "seats_asc": "seats ASC",
    "seats_desc": "seats DESC", "model_asc": "model ASC",
    "electric_first": "electric DESC, price_per_hour ASC",
    "electric_last": "electric ASC, price_per_hour ASC",
}
# in_use = the car has a confirmed booking running RIGHT NOW (it can still be booked for later dates)
CAR_COLS = ("car_id, model, specification, availability, seats, city, price_per_hour, ac, electric, rating, "
            "EXISTS(SELECT 1 FROM bookings b WHERE b.car_id=car.car_id AND b.status='confirmed' "
            "AND TIMESTAMP(b.date_start,b.start_time) <= NOW() AND TIMESTAMP(b.date_end,b.end_time) > NOW()) AS in_use")

def login_required(f):
    @wraps(f)
    def wrapper(*args, **kwargs):
        if "username" not in session:
            flash("Please log in to continue.")
            return redirect(url_for("login"))
        return f(*args, **kwargs)
    return wrapper

def admin_required(f):
    @wraps(f)
    def wrapper(*args, **kwargs):
        if "admin" not in session:
            flash("Admin login required.", "error")
            return redirect(url_for("admin_login"))
        return f(*args, **kwargs)
    return wrapper

@app.errorhandler(mysql.connector.Error)
def db_error(e):
    # Show a simple page (NOT a redirect, which would loop forever if the home page also needs the database).
    app.logger.error(e)
    return ("<body style='font-family:sans-serif;max-width:640px;margin:60px auto'>"
            "<h2>Database problem</h2><p>The app could not use the MySQL database. Please check:</p><ol>"
            "<li>MySQL is running.</li>"
            "<li>You ran the latest <b>rentcar.sql</b> (it recreates the database).</li>"
            "<li>The password in <b>database.py</b> is correct.</li></ol>"
            "<p>The exact error is shown in the terminal where you ran <code>python app.py</code>.</p></body>"), 500

@app.route("/")
def index():
    conn = get_connection(); cur = conn.cursor(dictionary=True)
    cur.execute("SELECT COUNT(*) AS cars, COUNT(DISTINCT city) AS cities, ROUND(AVG(rating),1) AS rating FROM car")
    stats = cur.fetchone()
    cur.execute(f"SELECT {CAR_COLS} FROM car WHERE availability=1 ORDER BY rating DESC LIMIT 3")
    featured = cur.fetchall()
    cur.execute("SELECT DISTINCT city FROM car ORDER BY city"); cities = [r["city"] for r in cur.fetchall()]
    cur.close(); conn.close()
    return render_template("index.html", stats=stats, featured=featured, cities=cities)

@app.route("/about")
def about():
    return render_template("about.html")

@app.route("/faq")
def faq():
    return render_template("faq.html")

# ---------- AUTH ----------
@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        f = request.form
        username, email = f.get("username", "").strip(), f.get("email", "").strip()
        pw, pw2, lic = f.get("password", ""), f.get("confirm", ""), f.get("license", "")
        errors = []
        if not username: errors.append("Username is required.")
        if not EMAIL_RE.match(email): errors.append("Enter a valid email address.")
        if len(pw) < 6: errors.append("Password must be at least 6 characters.")
        if pw != pw2: errors.append("Passwords do not match.")
        try:
            age = int(f.get("age", ""))
            if age < 18: errors.append("You must be at least 18 years old.")
        except ValueError:
            age = 0; errors.append("Age must be a whole number.")
        if lic not in ("yes", "no"): errors.append("Please answer yes or no for the driving license.")
        if not errors:
            conn = get_connection(); cur = conn.cursor(dictionary=True)
            cur.execute("SELECT username, email FROM users WHERE username=%s OR email=%s", (username, email))
            for r in cur.fetchall():
                if r["username"] == username: errors.append("Username is already taken.")
                if r["email"] == email: errors.append("Email is already registered.")
            if not errors:
                cur.execute("INSERT INTO users (username,password,email,age,license) VALUES (%s,%s,%s,%s,%s)",
                            (username, generate_password_hash(pw), email, age, lic == "yes"))
                conn.commit()
            cur.close(); conn.close()
        if errors:
            for e in dict.fromkeys(errors): flash(e, "error")
            return render_template("register.html", form=f)
        flash("Registration successful! Please log in.")
        return redirect(url_for("login"))
    return render_template("register.html", form={})

@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        username, pw = request.form.get("username", "").strip(), request.form.get("password", "")
        conn = get_connection(); cur = conn.cursor(dictionary=True)
        cur.execute("SELECT password FROM users WHERE username=%s", (username,))
        user = cur.fetchone(); cur.close(); conn.close()
        if user and check_password_hash(user["password"], pw):
            session["username"] = username
            flash(f"Welcome back, {username}!")
            return redirect(url_for("index"))
        flash("Invalid username or password.", "error")
    return render_template("login.html")

@app.route("/logout")
def logout():
    session.pop("username", None)
    flash("You have been logged out.")
    return redirect(url_for("index"))

# ---------- CARS ----------
@app.route("/car-image/<int:car_id>")
def car_image(car_id):
    conn = get_connection(); cur = conn.cursor(dictionary=True)
    cur.execute("SELECT image, image_mime FROM car WHERE car_id=%s", (car_id,))
    row = cur.fetchone(); cur.close(); conn.close()
    if not row or not row["image"]:
        return Response(status=404)
    return Response(row["image"], mimetype=row["image_mime"])

@app.route("/rentcar")
def rentcar():
    a = request.args
    sql = f"SELECT {CAR_COLS} FROM car WHERE 1=1"
    params = []
    if a.get("city"): sql += " AND city=%s"; params.append(a["city"])
    if a.get("seats", "").isdigit(): sql += " AND seats=%s"; params.append(int(a["seats"]))
    if a.get("q", "").strip(): sql += " AND LOWER(model) LIKE %s"; params.append("%" + a["q"].strip().lower() + "%")
    if a.get("ac") in ("0", "1"): sql += " AND ac=%s"; params.append(int(a["ac"]))
    if a.get("electric") in ("0", "1"): sql += " AND electric=%s"; params.append(int(a["electric"]))
    for key, op in (("min_price", ">="), ("max_price", "<=")):
        try:
            v = float(a.get(key, ""))
            sql += f" AND price_per_hour {op} %s"; params.append(v)   # op comes from a fixed tuple, not user input
        except ValueError:
            pass
    sql += " ORDER BY " + SORTS.get(a.get("sort"), "car_id ASC")      # whitelist => safe
    conn = get_connection(); cur = conn.cursor(dictionary=True)
    cur.execute(sql, params); cars = cur.fetchall()
    cur.execute("SELECT DISTINCT city FROM car ORDER BY city"); cities = [r["city"] for r in cur.fetchall()]
    cur.execute("SELECT DISTINCT seats FROM car ORDER BY seats"); seats = [r["seats"] for r in cur.fetchall()]
    cur.close(); conn.close()
    return render_template("rentcar.html", cars=cars, cities=cities, seat_opts=seats, a=a)

# ---------- BOOKING ----------
def check_booking(cur, car_id, f, username, lock=False):
    """Validate a booking. Returns (error, data). Price, duration, discount and total come from the SERVER."""
    suffix = " FOR UPDATE" if lock else ""
    cur.execute("SELECT license FROM users WHERE username=%s" + suffix, (username,))
    user = cur.fetchone()
    if not user: return "User not found.", None
    if not user["license"]: return "You need a valid driving license to book a car.", None
    cur.execute("SELECT * FROM car WHERE car_id=%s" + suffix, (car_id,))
    car = cur.fetchone()
    if not car: return "Car not found.", None
    if not car["availability"]: return "This car is currently unavailable.", None
    location = f.get("location", "").strip()
    if not location: return "Pick-up location is required.", None
    try:
        start = datetime.strptime(f"{f.get('start_date')} {f.get('start_time')}", "%Y-%m-%d %H:%M")
        end = datetime.strptime(f"{f.get('end_date')} {f.get('end_time')}", "%Y-%m-%d %H:%M")
    except (ValueError, TypeError):
        return "Enter a valid start and end date and time.", None
    if start < datetime.now(): return "Start date/time cannot be in the past.", None
    if end <= start: return "End date/time must be after the start.", None
    # Only CONFIRMED bookings block a car; cancelled ones are ignored.
    cur.execute("SELECT booking_id FROM bookings WHERE car_id=%s AND status='confirmed' "
                "AND TIMESTAMP(date_start,start_time) < %s AND TIMESTAMP(date_end,end_time) > %s",
                (car_id, end, start))
    if cur.fetchone(): return "This car is already booked for part of that period. Try later dates.", None
    # Rule: partial hours are rounded UP to the next whole hour.
    hours = math.ceil((end - start).total_seconds() / 3600)
    subtotal = Decimal(hours) * car["price_per_hour"]
    # 30% off the user's FIRST booking (cancelled bookings count, so the offer is used only once).
    cur.execute("SELECT COUNT(*) AS n FROM bookings WHERE username=%s", (username,))
    first = cur.fetchone()["n"] == 0
    discount = (subtotal * FIRST_BOOKING_DISCOUNT).quantize(Decimal("0.01")) if first else Decimal("0.00")
    return None, dict(car=car, location=location, start=start, end=end, hours=hours,
                      subtotal=subtotal, discount=discount, total=subtotal - discount, first=first)

@app.route("/booking/<int:car_id>")
@login_required
def booking(car_id):
    conn = get_connection(); cur = conn.cursor(dictionary=True)
    cur.execute("SELECT * FROM car WHERE car_id=%s", (car_id,)); car = cur.fetchone()
    cur.execute("SELECT license FROM users WHERE username=%s", (session["username"],)); user = cur.fetchone()
    cur.execute("SELECT COUNT(*) AS n FROM bookings WHERE username=%s", (session["username"],)); n = cur.fetchone()["n"]
    cur.close(); conn.close()
    if not car:
        flash("Car not found.", "error"); return redirect(url_for("rentcar"))
    if not car["availability"]:
        flash("This car is currently unavailable.", "error"); return redirect(url_for("rentcar"))
    if not user or not user["license"]:
        flash("You need a valid driving license to book a car.", "error"); return redirect(url_for("rentcar"))
    return render_template("booking.html", car=car, first=(n == 0), today=datetime.now().strftime("%Y-%m-%d"))

@app.route("/confirm-booking", methods=["POST"])
@login_required
def confirm_booking():
    f = request.form
    try: car_id = int(f.get("car_id", ""))
    except ValueError:
        flash("Invalid car.", "error"); return redirect(url_for("rentcar"))
    final = "confirm" in f
    conn = get_connection(); cur = conn.cursor(dictionary=True)
    try:
        if final: conn.start_transaction()          # BEGIN
        err, d = check_booking(cur, car_id, f, session["username"], lock=final)
        if err:
            conn.rollback(); flash(err, "error")
            return redirect(url_for("booking", car_id=car_id))
        if not final:
            cur.execute("SELECT email FROM users WHERE username=%s", (session["username"],))
            user = cur.fetchone()
            return render_template("confirm_booking.html", d=d, user=user, f=f)
        cur.execute(
            "INSERT INTO bookings (location,username,car_id,model,date_start,start_time,date_end,end_time,"
            "subtotal,discount_amount,total_amount) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
            (d["location"], session["username"], car_id, d["car"]["model"], d["start"].date(),
             d["start"].time(), d["end"].date(), d["end"].time(), d["subtotal"], d["discount"], d["total"]))
        booking_id = cur.lastrowid
        conn.commit()                               # COMMIT
        flash("Booking confirmed successfully!")
        return redirect(url_for("booking_success", booking_id=booking_id))
    except mysql.connector.Error as e:
        conn.rollback(); app.logger.error(e)        # ROLLBACK
        flash("Could not save the booking. Please try again.", "error")
        return redirect(url_for("booking", car_id=car_id))
    finally:
        cur.close(); conn.close()

@app.route("/booking-success/<int:booking_id>")
@login_required
def booking_success(booking_id):
    conn = get_connection(); cur = conn.cursor(dictionary=True)
    cur.execute("SELECT b.*, c.city FROM bookings b JOIN car c ON c.car_id=b.car_id "
                "WHERE b.booking_id=%s AND b.username=%s", (booking_id, session["username"]))
    b = cur.fetchone(); cur.close(); conn.close()
    if not b:
        flash("Booking not found.", "error"); return redirect(url_for("index"))
    return render_template("booking_success.html", b=b)

def start_of(b):   # MySQL TIME comes back as timedelta
    return datetime.combine(b["date_start"], (datetime.min + b["start_time"]).time())

def end_of(b):
    return datetime.combine(b["date_end"], (datetime.min + b["end_time"]).time())

@app.route("/my-bookings")
@login_required
def my_bookings():
    conn = get_connection(); cur = conn.cursor(dictionary=True)
    cur.execute("SELECT b.*, c.city FROM bookings b JOIN car c ON c.car_id=b.car_id "
                "WHERE b.username=%s ORDER BY b.date_start DESC, b.start_time DESC", (session["username"],))
    rows = cur.fetchall(); cur.close(); conn.close()
    now = datetime.now()
    for b in rows:
        if b["status"] == "cancelled": b["label"], b["cls"] = "Cancelled", "cancelled"
        elif start_of(b) > now:        b["label"], b["cls"] = "Upcoming", "upcoming"
        elif end_of(b) > now:          b["label"], b["cls"] = "Ongoing", "ongoing"
        else:                          b["label"], b["cls"] = "Completed", "done"
        b["can_cancel"] = b["label"] == "Upcoming"
    return render_template("my_bookings.html", bookings=rows)

@app.route("/cancel-booking/<int:booking_id>", methods=["POST"])
@login_required
def cancel_booking(booking_id):
    conn = get_connection(); cur = conn.cursor(dictionary=True)
    try:
        conn.start_transaction()
        cur.execute("SELECT * FROM bookings WHERE booking_id=%s AND username=%s FOR UPDATE",
                    (booking_id, session["username"]))
        b = cur.fetchone()
        if not b: flash("Booking not found.", "error")
        elif b["status"] != "confirmed": flash("This booking is already cancelled.", "error")
        elif start_of(b) <= datetime.now(): flash("A booking can only be cancelled before its start time.", "error")
        else:
            cur.execute("UPDATE bookings SET status='cancelled' WHERE booking_id=%s", (booking_id,))
            flash("Booking cancelled.")
        conn.commit()
    except mysql.connector.Error as e:
        conn.rollback(); app.logger.error(e); flash("Could not cancel the booking.", "error")
    finally:
        cur.close(); conn.close()
    return redirect(url_for("my_bookings"))

# ---------- ADMIN ----------
@app.route("/admin/login", methods=["GET", "POST"])
def admin_login():
    if request.method == "POST":
        name, pw = request.form.get("username", "").strip(), request.form.get("password", "")
        conn = get_connection(); cur = conn.cursor(dictionary=True)
        cur.execute("SELECT password FROM admins WHERE admin_username=%s", (name,))
        row = cur.fetchone(); cur.close(); conn.close()
        if row and check_password_hash(row["password"], pw):
            session["admin"] = name
            return redirect(url_for("admin_dashboard"))
        flash("Invalid admin username or password.", "error")
    return render_template("admin_login.html")

@app.route("/admin/logout")
def admin_logout():
    session.pop("admin", None)
    flash("Admin logged out.")
    return redirect(url_for("index"))

@app.route("/admin")
@admin_required
def admin_dashboard():
    conn = get_connection(); cur = conn.cursor(dictionary=True)
    cur.execute("SELECT COUNT(*) AS n FROM users"); users_n = cur.fetchone()["n"]
    cur.execute("SELECT COUNT(*) AS n FROM car"); cars_n = cur.fetchone()["n"]
    cur.execute("SELECT COUNT(*) AS n, COALESCE(SUM(total_amount),0) AS revenue, COALESCE(SUM(discount_amount),0) AS disc "
                "FROM bookings WHERE status='confirmed'")
    bk = cur.fetchone()
    cur.execute("SELECT COUNT(*) AS n FROM bookings WHERE status='cancelled'"); cancelled = cur.fetchone()["n"]
    cur.execute("SELECT username, email, age, license FROM users ORDER BY username")   # never select password hashes
    users = cur.fetchall()
    cur.execute("SELECT car_id, model, city, seats, price_per_hour, ac, electric, availability, rating FROM car ORDER BY car_id")
    cars = cur.fetchall()
    cur.execute("SELECT booking_id, username, model, location, date_start, start_time, date_end, end_time, "
                "subtotal, discount_amount, total_amount, status FROM bookings ORDER BY booking_id DESC")
    bookings = cur.fetchall()
    cur.close(); conn.close()
    return render_template("admin_dashboard.html", users_n=users_n, cars_n=cars_n, bk=bk, cancelled=cancelled,
                           users=users, cars=cars, bookings=bookings)

if __name__ == "__main__":
    try:
        seed_images()
        ensure_admin()
    except mysql.connector.Error as e:
        print("MySQL error:", e, "\nCheck rentcar.sql was run and the password in database.py.")
    app.run(debug=True)
