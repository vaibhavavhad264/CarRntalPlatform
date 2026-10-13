-- RentCar database (simple version)
DROP DATABASE IF EXISTS rentcar;
CREATE DATABASE rentcar;
USE rentcar;

-- Customers (license: 1 = yes, 0 = no)
CREATE TABLE users (
    username VARCHAR(50) PRIMARY KEY,
    password VARCHAR(255) NOT NULL,
    email    VARCHAR(100) UNIQUE NOT NULL,
    age      INT NOT NULL,
    license  BOOLEAN NOT NULL,
    CHECK (age >= 18)
);

-- Admins (password is stored hashed)
CREATE TABLE admins (
    admin_username VARCHAR(50) PRIMARY KEY,
    password       VARCHAR(255) NOT NULL
);

-- Cars (ac: 1 = AC, 0 = Non-AC | electric: 1 = Electric, 0 = Non-electric)
CREATE TABLE car (
    car_id         INT AUTO_INCREMENT PRIMARY KEY,
    model          VARCHAR(100) NOT NULL,
    specification  VARCHAR(255),
    availability   BOOLEAN DEFAULT TRUE,
    seats          INT NOT NULL,
    city           VARCHAR(100) NOT NULL,
    price_per_hour DECIMAL(10,2) NOT NULL,
    ac             BOOLEAN NOT NULL,
    electric       BOOLEAN NOT NULL DEFAULT 0,
    rating         DECIMAL(2,1),
    image          MEDIUMBLOB,
    image_mime     VARCHAR(50) DEFAULT 'image/svg+xml'
);

-- Bookings (status: confirmed / cancelled)
CREATE TABLE bookings (
    booking_id      INT AUTO_INCREMENT PRIMARY KEY,
    location        VARCHAR(100) NOT NULL,
    username        VARCHAR(50) NOT NULL,
    car_id          INT NOT NULL,
    model           VARCHAR(100) NOT NULL,
    date_start      DATE NOT NULL,
    start_time      TIME NOT NULL,
    date_end        DATE NOT NULL,
    end_time        TIME NOT NULL,
    subtotal        DECIMAL(10,2) NOT NULL,
    discount_amount DECIMAL(10,2) NOT NULL DEFAULT 0,
    total_amount    DECIMAL(10,2) NOT NULL,
    status          ENUM('confirmed','cancelled') NOT NULL DEFAULT 'confirmed',
    FOREIGN KEY (username) REFERENCES users(username),
    FOREIGN KEY (car_id)   REFERENCES car(car_id)
);


-- Admin login:  ID = admin   Password = admin123
INSERT INTO admins (admin_username, password) VALUES
('admin', 'pbkdf2:sha256:1000000$Q3lytM4WBmBoC46A$42b4817a86c44475e58a82f4c1d8e0b2ef147c5108a85ea267e5846f4f5cfe8d');

-- Sample cars (images are added automatically when app.py starts)
INSERT INTO car (model, specification, availability, seats, city, price_per_hour, ac, electric, rating) VALUES
('Hyundai Creta',   '1.5L Petrol, Automatic SUV',   1, 5, 'Mumbai',    500,  1, 0, 4.5),
('Tata Nexon EV',   'Electric, Compact SUV',        1, 5, 'Pune',      480,  1, 1, 4.3),
('Maruti Swift',    '1.2L Petrol, Hatchback',       1, 5, 'Delhi',     250,  1, 0, 4.1),
('Kia Seltos',      '1.5L Diesel, Automatic SUV',   1, 5, 'Bangalore', 520,  1, 0, 4.6),
('Toyota Innova',   '2.4L Diesel, Family MPV',      1, 7, 'Hyderabad', 700,  1, 0, 4.7),
('Mahindra XUV700', '2.0L Petrol, Premium SUV',     1, 7, 'Mumbai',    750,  1, 0, 4.8),
('Honda City',      '1.5L Petrol, Sedan',           1, 5, 'Pune',      450,  1, 0, 4.4),
('Tata Punch',      '1.2L Petrol, Micro SUV',       1, 5, 'Delhi',     280,  0, 0, 3.9),
('Hyundai i20',     '1.2L Petrol, Hatchback',       0, 5, 'Bangalore', 300,  1, 0, 4.2),
('Maruti Baleno',   '1.2L Petrol, Hatchback',       1, 5, 'Hyderabad', 270,  0, 0, 4.0),
('Mahindra Thar',   '2.2L Diesel, 4x4 Off-roader',  1, 4, 'Mumbai',    650,  0, 0, 4.6),
('BMW M3',          '3.0L Petrol, Performance Sedan',1, 5, 'Mumbai',   1500, 1, 0, 4.9),
('MG ZS EV',        'Electric, Premium SUV',        1, 5, 'Delhi',     600,  1, 1, 4.5),
('Tata Tiago EV',   'Electric, City Hatchback',     1, 4, 'Bangalore', 350,  1, 1, 4.2);
