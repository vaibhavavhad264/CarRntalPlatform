# RentCar – Online Car Rental Platform
Flask + MySQL + HTML/CSS/JS college project. Light theme with orange accent (from the supplied DriveLux design) plus a dark mode.

## Features
- Register / login (hashed passwords), **license stored as Yes/No (boolean)** – only users with a license can book.
- Browse cars with a **vertical filter sidebar**: search, city, seats, AC, fuel type (**electric / non-electric**), price range, and sorting (price, rating, seats, model, **electric first / non-electric first**). All filtering is server-side with parameterized SQL.
- Car images are stored in MySQL (`car.image` MEDIUMBLOB) and served by `/car-image/<id>`.
- A car that is **booked right now shows "Unavailable now"**, but you can still book it for later dates (overlap check blocks only clashing times).
- Booking with server-side validation, overlap prevention, transactional confirmation, **30% discount on a user's first booking** (cancelled bookings count, so it can only be used once).
- **My Bookings** page: "No bookings yet" if empty; an animated **running car** when the user has bookings; status (Upcoming / Ongoing / Completed / Cancelled); **Cancel booking** only before the start time.
- **Admin**: `admins` table, admin login, dashboard with registered users, revenue, cars and bookings.
- **Account dropdown** (Login / Register / Logout / My Bookings / Admin), **light/dark toggle** (remembered), **car-running intro animation** on the home page (once per browser tab session).

## Setup
1. `python --version` (3.8+)
2. `python -m venv venv` then `venv\Scripts\activate`
3. `pip install -r requirements.txt`
4. Start MySQL and run `rentcar.sql` (it **drops and recreates** the `rentcar` database – needed because the schema changed: new columns `electric`, `status`, `subtotal`, `discount_amount`, boolean `license`, and the `admins` table).
   In the MySQL shell: `source C:/path/to/RentCar/rentcar.sql`
5. Put your MySQL password in `database.py` (`YOUR_MYSQL_PASSWORD`).
6. `python app.py` → http://127.0.0.1:5000

**Default admin:** username `admin`, password `admin123` (created by `rentcar.sql`; change it for real use). Admin login is in the Account dropdown.

## Business rules
- Charge = price per hour × hours; partial hours round up. The server recalculates everything; JavaScript is only a preview.
- First booking: 30% off the subtotal. Total = subtotal − discount.
- Overlap: `new_start < existing_end AND new_end > existing_start`, counting only **confirmed** bookings.
- `availability` is a manual "in service" flag (admin-level); "currently booked" is computed from bookings at the current time.
- Revenue = sum of `total_amount` of confirmed bookings (cancelled ones are excluded).
- Transaction: BEGIN → lock user and car rows (`FOR UPDATE`) → validate → INSERT → COMMIT; any error → ROLLBACK.
- Passwords: `generate_password_hash` / `check_password_hash`. Secret key should come from an environment variable in production.

## Test cases
| # | Test | Input | Expected |
|---|---|---|---|
|1|Register|Age 25, license Yes|Success, go to login|
|2|Register|Age 17|Rejected|
|3|Register|Duplicate username/email|Rejected|
|4|Register|License = No|Account created, but booking is refused|
|5|Login|Wrong password|"Invalid username or password."|
|6|Dropdown|Logged out / in|Login+Register / My Bookings+Logout|
|7|Filter|Electric|Only electric cars|
|8|Sort|Electric first|Electric cars at the top|
|9|Filter|City Mumbai + AC|Matching cars only|
|10|Booking|First booking, 8 h at ₹500|Subtotal 4,000, discount 1,200, total 2,800|
|11|Booking|Second booking|No discount|
|12|Booking|Past date / end before start|Rejected|
|13|Booking|Overlapping time on same car|Rejected|
|14|Car now booked|Open Rent a Car|"Unavailable now" label, "Book Later" still works|
|15|My Bookings|New user|"No bookings yet"|
|16|My Bookings|User with bookings|Running-car animation + list|
|17|Cancel|Upcoming booking|Status Cancelled; car free again; revenue drops|
|18|Cancel|Ongoing/completed booking|No cancel button; server also refuses|
|19|Admin|Wrong password|Rejected|
|20|Admin|Correct login|Dashboard with users, cars, bookings, revenue|
|21|Theme|Click moon/sun|Switches and persists after reload|
|22|Intro|First home visit in a tab|Car runs across screen, then home appears|

## Common errors
- `Access denied for user 'root'` → wrong password in database.py.
- `Unknown column ...` or `Unknown database` → re-run the new `rentcar.sql`.
- `ModuleNotFoundError` → activate the venv and reinstall requirements.
- Intro animation not showing again → it plays once per tab session; open a new tab or clear `sessionStorage`.
- Fonts look plain → the Google font loads from the internet; it needs a connection.
