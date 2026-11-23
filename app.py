import csv, io, math, os, re
from datetime import datetime
from decimal import Decimal
from functools import wraps
import mysql.connector
from flask import (Flask, render_template, request, redirect, url_for,
                   session, flash, Response)
from werkzeug.security import generate_password_hash, check_password_hash
from database import get_connection, seed_images, ensure_admin, find_photo, MIMES

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

DEFAULT_CAR_SVG = """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 600 400" width="100%" height="100%">
  <rect width="600" height="400" fill="#f0f1f4"/>
  <path d="M120 250 L180 160 Q200 130 240 130 L380 130 Q420 130 450 165 L500 230 L530 235 Q540 240 540 255 L540 280 Q540 290 530 290 L500 290 Q485 260 450 260 Q415 260 400 290 L240 290 Q225 260 190 260 Q155 260 140 290 L90 290 Q80 290 80 280 L80 260 Q80 248 95 245 Z" fill="#ff5a36" opacity="0.85"/>
  <circle cx="190" cy="290" r="35" fill="#222"/>
  <circle cx="190" cy="290" r="16" fill="#fff"/>
  <circle cx="450" cy="290" r="35" fill="#222"/>
  <circle cx="450" cy="290" r="16" fill="#fff"/>
  <path d="M210 165 L300 165 L300 220 L165 220 Z" fill="#ffffff" opacity="0.8"/>
  <path d="M315 165 L415 165 L445 220 L315 220 Z" fill="#ffffff" opacity="0.8"/>
  <text x="300" y="365" font-family="sans-serif" font-size="18" font-weight="bold" fill="#888" text-anchor="middle">RentCar Fleet</text>
</svg>"""

# ---------- CARS ----------
@app.route("/car-image/<int:car_id>")
def car_image(car_id):
    conn = get_connection(); cur = conn.cursor(dictionary=True)
    cur.execute("SELECT image, image_mime FROM car WHERE car_id=%s", (car_id,))
    row = cur.fetchone(); cur.close(); conn.close()
    if not row or not row["image"]:
        return Response(DEFAULT_CAR_SVG, mimetype="image/svg+xml")
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

# ---------- USER PROFILE & INVOICE ----------
@app.route("/profile", methods=["GET", "POST"])
@login_required
def profile():
    username = session["username"]
    conn = get_connection(); cur = conn.cursor(dictionary=True)
    if request.method == "POST":
        action = request.form.get("action")
        if action == "update_email":
            email = request.form.get("email", "").strip()
            if not EMAIL_RE.match(email):
                flash("Enter a valid email address.", "error")
            else:
                cur.execute("SELECT username FROM users WHERE email=%s AND username!=%s", (email, username))
                if cur.fetchone():
                    flash("This email is already registered to another account.", "error")
                else:
                    cur.execute("UPDATE users SET email=%s WHERE username=%s", (email, username))
                    conn.commit()
                    flash("Email address updated successfully!")
        elif action == "change_password":
            curr_pw = request.form.get("current_password", "")
            new_pw = request.form.get("new_password", "")
            confirm_pw = request.form.get("confirm_password", "")
            cur.execute("SELECT password FROM users WHERE username=%s", (username,))
            user_row = cur.fetchone()
            if not user_row or not check_password_hash(user_row["password"], curr_pw):
                flash("Current password is incorrect.", "error")
            elif len(new_pw) < 6:
                flash("New password must be at least 6 characters.", "error")
            elif new_pw != confirm_pw:
                flash("New passwords do not match.", "error")
            else:
                cur.execute("UPDATE users SET password=%s WHERE username=%s", (generate_password_hash(new_pw), username))
                conn.commit()
                flash("Password changed successfully!")

    cur.execute("SELECT username, email, age, license FROM users WHERE username=%s", (username,))
    user = cur.fetchone()
    cur.execute("SELECT COUNT(*) as n, COALESCE(SUM(total_amount),0) as spent FROM bookings WHERE username=%s AND status='confirmed'", (username,))
    stats = cur.fetchone()
    cur.close(); conn.close()
    return render_template("profile.html", user=user, stats=stats)

@app.route("/booking/invoice/<int:booking_id>")
def booking_invoice(booking_id):
    is_admin = session.get("admin") is not None
    user = session.get("username")
    if not is_admin and not user:
        flash("Please log in to view this invoice.", "error")
        return redirect(url_for("login"))

    conn = get_connection(); cur = conn.cursor(dictionary=True)
    cur.execute(
        "SELECT b.*, c.specification, c.city, c.price_per_hour, u.email "
        "FROM bookings b "
        "JOIN car c ON c.car_id = b.car_id "
        "JOIN users u ON u.username = b.username "
        "WHERE b.booking_id = %s",
        (booking_id,)
    )
    b = cur.fetchone()
    cur.close(); conn.close()

    if not b:
        flash("Invoice not found.", "error")
        return redirect(url_for("index"))

    if not is_admin and b["username"] != user:
        flash("Unauthorized access to this invoice.", "error")
        return redirect(url_for("my_bookings"))

    start = datetime.combine(b["date_start"], (datetime.min + b["start_time"]).time())
    end = datetime.combine(b["date_end"], (datetime.min + b["end_time"]).time())
    hours = math.ceil((end - start).total_seconds() / 3600)
    b["hours"] = hours

    return render_template("invoice.html", b=b, is_admin=is_admin)

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

    # Enhanced users query
    cur.execute(
        "SELECT u.username, u.email, u.age, u.license, "
        "(SELECT COUNT(*) FROM bookings b WHERE b.username=u.username) AS total_bookings, "
        "COALESCE((SELECT SUM(total_amount) FROM bookings b WHERE b.username=u.username AND b.status='confirmed'), 0) AS total_spent "
        "FROM users u "
        "ORDER BY u.username"
    )
    users = cur.fetchall()

    # Enhanced cars query
    cur.execute(
        "SELECT c.car_id, c.model, c.specification, c.city, c.seats, c.price_per_hour, c.ac, c.electric, c.availability, c.rating, "
        "(c.image IS NOT NULL) AS has_image, "
        "(SELECT COUNT(*) FROM bookings b WHERE b.car_id=c.car_id) AS total_bookings, "
        "EXISTS(SELECT 1 FROM bookings b WHERE b.car_id=c.car_id AND b.status='confirmed' "
        "AND TIMESTAMP(b.date_start,b.start_time) <= NOW() AND TIMESTAMP(b.date_end,b.end_time) > NOW()) AS in_use "
        "FROM car c "
        "ORDER BY c.car_id"
    )
    cars = cur.fetchall()

    # Enhanced bookings query
    cur.execute(
        "SELECT b.booking_id, b.username, b.car_id, b.model, b.location, b.date_start, b.start_time, b.date_end, b.end_time, "
        "b.subtotal, b.discount_amount, b.total_amount, b.status, c.city "
        "FROM bookings b "
        "LEFT JOIN car c ON c.car_id = b.car_id "
        "ORDER BY b.booking_id DESC"
    )
    bookings = cur.fetchall()

    # Distinct cities
    cur.execute("SELECT DISTINCT city FROM car ORDER BY city")
    cities = [r["city"] for r in cur.fetchall()]

    cur.close(); conn.close()
    active_tab = request.args.get("tab", "users")
    return render_template("admin_dashboard.html", users_n=users_n, cars_n=cars_n, bk=bk, cancelled=cancelled,
                           users=users, cars=cars, bookings=bookings, cities=cities, active_tab=active_tab)

@app.route("/admin/car/add", methods=["POST"])
@admin_required
def admin_add_car():
    f = request.form
    model = f.get("model", "").strip()
    specification = f.get("specification", "").strip()
    city = f.get("city", "").strip()
    try:
        seats = int(f.get("seats", "5"))
        price_per_hour = Decimal(f.get("price_per_hour", "0"))
        rating = Decimal(f.get("rating", "4.5"))
    except (ValueError, TypeError):
        flash("Invalid numerical values for seats, price, or rating.", "error")
        return redirect(url_for("admin_dashboard", tab="cars"))

    if not model or not city or price_per_hour <= 0:
        flash("Model name, city, and positive price per hour are required.", "error")
        return redirect(url_for("admin_dashboard", tab="cars"))

    ac = 1 if f.get("ac") == "1" else 0
    electric = 1 if f.get("electric") == "1" else 0
    availability = 1 if f.get("availability", "1") == "1" else 0

    image_data = None
    image_mime = None
    if "image" in request.files:
        file = request.files["image"]
        if file and file.filename != "":
            image_data = file.read()
            image_mime = file.mimetype or "image/jpeg"

    conn = get_connection(); cur = conn.cursor(dictionary=True)
    try:
        if not image_data:
            photo = find_photo(model)
            if photo:
                with open(photo, "rb") as fh:
                    image_data = fh.read()
                image_mime = MIMES.get(os.path.splitext(photo)[1].lower(), "image/jpeg")

        cur.execute(
            "INSERT INTO car (model, specification, availability, seats, city, price_per_hour, ac, electric, rating, image, image_mime) "
            "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)",
            (model, specification, availability, seats, city, price_per_hour, ac, electric, rating, image_data, image_mime)
        )
        conn.commit()
        flash(f"Car '{model}' added successfully!")
    except mysql.connector.Error as e:
        conn.rollback()
        app.logger.error(e)
        flash("Database error while adding car.", "error")
    finally:
        cur.close(); conn.close()
    return redirect(url_for("admin_dashboard", tab="cars"))

@app.route("/admin/car/edit/<int:car_id>", methods=["POST"])
@admin_required
def admin_edit_car(car_id):
    f = request.form
    model = f.get("model", "").strip()
    specification = f.get("specification", "").strip()
    city = f.get("city", "").strip()
    try:
        seats = int(f.get("seats", "5"))
        price_per_hour = Decimal(f.get("price_per_hour", "0"))
        rating = Decimal(f.get("rating", "4.5"))
    except (ValueError, TypeError):
        flash("Invalid numerical values for seats, price, or rating.", "error")
        return redirect(url_for("admin_dashboard", tab="cars"))

    if not model or not city or price_per_hour <= 0:
        flash("Model name, city, and positive price per hour are required.", "error")
        return redirect(url_for("admin_dashboard", tab="cars"))

    ac = 1 if f.get("ac") == "1" else 0
    electric = 1 if f.get("electric") == "1" else 0
    availability = 1 if f.get("availability") == "1" else 0

    image_data = None
    image_mime = None
    if "image" in request.files:
        file = request.files["image"]
        if file and file.filename != "":
            image_data = file.read()
            image_mime = file.mimetype or "image/jpeg"

    conn = get_connection(); cur = conn.cursor(dictionary=True)
    try:
        if image_data:
            cur.execute(
                "UPDATE car SET model=%s, specification=%s, city=%s, seats=%s, price_per_hour=%s, "
                "ac=%s, electric=%s, availability=%s, rating=%s, image=%s, image_mime=%s WHERE car_id=%s",
                (model, specification, city, seats, price_per_hour, ac, electric, availability, rating, image_data, image_mime, car_id)
            )
        else:
            cur.execute(
                "UPDATE car SET model=%s, specification=%s, city=%s, seats=%s, price_per_hour=%s, "
                "ac=%s, electric=%s, availability=%s, rating=%s WHERE car_id=%s",
                (model, specification, city, seats, price_per_hour, ac, electric, availability, rating, car_id)
            )
        conn.commit()
        flash(f"Car #{car_id} ({model}) updated successfully!")
    except mysql.connector.Error as e:
        conn.rollback()
        app.logger.error(e)
        flash("Database error while updating car.", "error")
    finally:
        cur.close(); conn.close()
    return redirect(url_for("admin_dashboard", tab="cars"))

@app.route("/admin/car/toggle-status/<int:car_id>", methods=["POST"])
@admin_required
def admin_toggle_car_status(car_id):
    conn = get_connection(); cur = conn.cursor(dictionary=True)
    try:
        cur.execute("SELECT model, availability FROM car WHERE car_id=%s", (car_id,))
        car = cur.fetchone()
        if not car:
            flash("Car not found.", "error")
        else:
            new_status = 0 if car["availability"] else 1
            cur.execute("UPDATE car SET availability=%s WHERE car_id=%s", (new_status, car_id))
            conn.commit()
            state_text = "now available (in service)" if new_status else "now marked out of service"
            flash(f"Car '{car['model']}' is {state_text}.")
    except mysql.connector.Error as e:
        conn.rollback()
        app.logger.error(e)
        flash("Database error toggling car status.", "error")
    finally:
        cur.close(); conn.close()
    return redirect(url_for("admin_dashboard", tab="cars"))

@app.route("/admin/car/delete/<int:car_id>", methods=["POST"])
@admin_required
def admin_delete_car(car_id):
    conn = get_connection(); cur = conn.cursor(dictionary=True)
    try:
        cur.execute("SELECT model FROM car WHERE car_id=%s", (car_id,))
        car = cur.fetchone()
        if not car:
            flash("Car not found.", "error")
            return redirect(url_for("admin_dashboard", tab="cars"))

        cur.execute(
            "SELECT COUNT(*) AS active_count FROM bookings "
            "WHERE car_id=%s AND status='confirmed' AND TIMESTAMP(date_end, end_time) > NOW()",
            (car_id,)
        )
        active = cur.fetchone()["active_count"]
        if active > 0:
            flash(f"Cannot delete '{car['model']}': it has {active} active or upcoming confirmed booking(s). Deactivate it instead.", "error")
            return redirect(url_for("admin_dashboard", tab="cars"))

        cur.execute("DELETE FROM bookings WHERE car_id=%s", (car_id,))
        cur.execute("DELETE FROM car WHERE car_id=%s", (car_id,))
        conn.commit()
        flash(f"Car '{car['model']}' (ID #{car_id}) was successfully deleted.")
    except mysql.connector.Error as e:
        conn.rollback()
        app.logger.error(e)
        flash("Database error while deleting car.", "error")
    finally:
        cur.close(); conn.close()
    return redirect(url_for("admin_dashboard", tab="cars"))

@app.route("/admin/user/toggle-license/<username>", methods=["POST"])
@admin_required
def admin_toggle_user_license(username):
    conn = get_connection(); cur = conn.cursor(dictionary=True)
    try:
        cur.execute("SELECT license FROM users WHERE username=%s", (username,))
        user = cur.fetchone()
        if not user:
            flash("User not found.", "error")
        else:
            new_license = 0 if user["license"] else 1
            cur.execute("UPDATE users SET license=%s WHERE username=%s", (new_license, username))
            conn.commit()
            txt = "verified" if new_license else "revoked"
            flash(f"Driving license for '{username}' has been {txt}.")
    except mysql.connector.Error as e:
        conn.rollback()
        app.logger.error(e)
        flash("Database error updating license.", "error")
    finally:
        cur.close(); conn.close()
    return redirect(url_for("admin_dashboard", tab="users"))

@app.route("/admin/user/reset-password/<username>", methods=["POST"])
@admin_required
def admin_reset_user_password(username):
    new_pw = request.form.get("password", "")
    if len(new_pw) < 6:
        flash("Password must be at least 6 characters.", "error")
        return redirect(url_for("admin_dashboard", tab="users"))
    conn = get_connection(); cur = conn.cursor(dictionary=True)
    try:
        cur.execute("UPDATE users SET password=%s WHERE username=%s", (generate_password_hash(new_pw), username))
        conn.commit()
        flash(f"Password for user '{username}' has been reset successfully!")
    except mysql.connector.Error as e:
        conn.rollback()
        app.logger.error(e)
        flash("Database error resetting password.", "error")
    finally:
        cur.close(); conn.close()
    return redirect(url_for("admin_dashboard", tab="users"))

@app.route("/admin/user/delete/<username>", methods=["POST"])
@admin_required
def admin_delete_user(username):
    conn = get_connection(); cur = conn.cursor(dictionary=True)
    try:
        cur.execute("SELECT username FROM users WHERE username=%s", (username,))
        user = cur.fetchone()
        if not user:
            flash("User not found.", "error")
            return redirect(url_for("admin_dashboard", tab="users"))

        cur.execute(
            "SELECT COUNT(*) AS active_count FROM bookings "
            "WHERE username=%s AND status='confirmed' AND TIMESTAMP(date_end, end_time) > NOW()",
            (username,)
        )
        active = cur.fetchone()["active_count"]
        if active > 0:
            flash(f"Cannot delete user '{username}': they have {active} active or upcoming confirmed booking(s).", "error")
            return redirect(url_for("admin_dashboard", tab="users"))

        cur.execute("DELETE FROM bookings WHERE username=%s", (username,))
        cur.execute("DELETE FROM users WHERE username=%s", (username,))
        conn.commit()
        flash(f"User '{username}' was successfully deleted.")
    except mysql.connector.Error as e:
        conn.rollback()
        app.logger.error(e)
        flash("Database error deleting user.", "error")
    finally:
        cur.close(); conn.close()
    return redirect(url_for("admin_dashboard", tab="users"))

@app.route("/admin/booking/cancel/<int:booking_id>", methods=["POST"])
@admin_required
def admin_cancel_booking(booking_id):
    conn = get_connection(); cur = conn.cursor(dictionary=True)
    try:
        cur.execute("SELECT booking_id, status, username FROM bookings WHERE booking_id=%s", (booking_id,))
        b = cur.fetchone()
        if not b:
            flash("Booking not found.", "error")
        elif b["status"] == "cancelled":
            flash("Booking is already cancelled.", "error")
        else:
            cur.execute("UPDATE bookings SET status='cancelled' WHERE booking_id=%s", (booking_id,))
            conn.commit()
            flash(f"Booking #{booking_id} for '{b['username']}' was cancelled by admin.")
    except mysql.connector.Error as e:
        conn.rollback()
        app.logger.error(e)
        flash("Database error cancelling booking.", "error")
    finally:
        cur.close(); conn.close()
    return redirect(url_for("admin_dashboard", tab="bookings"))

@app.route("/admin/export/bookings")
@admin_required
def admin_export_bookings():
    conn = get_connection(); cur = conn.cursor(dictionary=True)
    cur.execute(
        "SELECT b.booking_id, b.username, b.car_id, b.model, b.location, b.date_start, b.start_time, "
        "b.date_end, b.end_time, b.subtotal, b.discount_amount, b.total_amount, b.status "
        "FROM bookings b ORDER BY b.booking_id DESC"
    )
    rows = cur.fetchall()
    cur.close(); conn.close()

    si = io.StringIO()
    writer = csv.writer(si)
    writer.writerow(["Booking ID", "Username", "Car ID", "Car Model", "Location", "Start Date", "Start Time",
                     "End Date", "End Time", "Subtotal (INR)", "Discount (INR)", "Total (INR)", "Status"])
    for r in rows:
        writer.writerow([r["booking_id"], r["username"], r["car_id"], r["model"], r["location"],
                         str(r["date_start"]), str(r["start_time"]), str(r["date_end"]), str(r["end_time"]),
                         r["subtotal"], r["discount_amount"], r["total_amount"], r["status"]])
    return Response(
        si.getvalue(),
        mimetype="text/csv",
        headers={"Content-Disposition": "attachment; filename=rentcar_bookings.csv"}
    )

@app.route("/admin/export/users")
@admin_required
def admin_export_users():
    conn = get_connection(); cur = conn.cursor(dictionary=True)
    cur.execute(
        "SELECT u.username, u.email, u.age, u.license, "
        "(SELECT COUNT(*) FROM bookings b WHERE b.username=u.username) AS total_bookings, "
        "COALESCE((SELECT SUM(total_amount) FROM bookings b WHERE b.username=u.username AND b.status='confirmed'), 0) AS total_spent "
        "FROM users u ORDER BY u.username"
    )
    rows = cur.fetchall()
    cur.close(); conn.close()

    si = io.StringIO()
    writer = csv.writer(si)
    writer.writerow(["Username", "Email", "Age", "License Verified", "Total Bookings", "Total Spent (INR)"])
    for r in rows:
        writer.writerow([r["username"], r["email"], r["age"], "Yes" if r["license"] else "No", r["total_bookings"], r["total_spent"]])
    return Response(
        si.getvalue(),
        mimetype="text/csv",
        headers={"Content-Disposition": "attachment; filename=rentcar_users.csv"}
    )

@app.route("/admin/export/cars")
@admin_required
def admin_export_cars():
    conn = get_connection(); cur = conn.cursor(dictionary=True)
    cur.execute(
        "SELECT car_id, model, specification, city, seats, price_per_hour, ac, electric, availability, rating "
        "FROM car ORDER BY car_id"
    )
    rows = cur.fetchall()
    cur.close(); conn.close()

    si = io.StringIO()
    writer = csv.writer(si)
    writer.writerow(["Car ID", "Model", "Specification", "City", "Seats", "Price Per Hour (INR)", "AC", "Electric", "In Service", "Rating"])
    for r in rows:
        writer.writerow([r["car_id"], r["model"], r["specification"], r["city"], r["seats"], r["price_per_hour"],
                         "AC" if r["ac"] else "Non-AC", "Electric" if r["electric"] else "Non-electric",
                         "Yes" if r["availability"] else "No", r["rating"]])
    return Response(
        si.getvalue(),
        mimetype="text/csv",
        headers={"Content-Disposition": "attachment; filename=rentcar_cars.csv"}
    )

if __name__ == "__main__":
    try:
        seed_images()
        ensure_admin()
    except mysql.connector.Error as e:
        print("MySQL error:", e, "\nCheck rentcar.sql was run and the password in database.py.")
    app.run(debug=True)
