-- Database Schema for AI-Powered Blood Bank System
-- Compatible with MySQL and SQLite (via standard ANSI SQL patterns)

-- 1. Hospitals Table
CREATE TABLE IF NOT EXISTS hospitals (
    hospital_id INT AUTO_INCREMENT PRIMARY KEY,
    name VARCHAR(150) NOT NULL UNIQUE,
    latitude DECIMAL(9, 6) NOT NULL,
    longitude DECIMAL(9, 6) NOT NULL,
    capacity_beds INT NOT NULL DEFAULT 100,
    safety_stock_ratio DECIMAL(3, 2) DEFAULT 0.20, -- 20% of peak weekly demand
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 2. Blood Components Table
CREATE TABLE IF NOT EXISTS blood_components (
    component_id INT AUTO_INCREMENT PRIMARY KEY,
    name VARCHAR(100) NOT NULL UNIQUE,
    shelf_life_days INT NOT NULL,
    storage_temp_celsius VARCHAR(50) DEFAULT '2-6 C'
);

-- 3. Users Table
CREATE TABLE IF NOT EXISTS users (
    user_id INT AUTO_INCREMENT PRIMARY KEY,
    username VARCHAR(100) NOT NULL UNIQUE,
    password_hash VARCHAR(255) NOT NULL,
    role VARCHAR(50) NOT NULL CHECK (role IN ('Admin', 'Hospital Staff')),
    hospital_id INT DEFAULT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (hospital_id) REFERENCES hospitals(hospital_id) ON DELETE SET NULL
);

-- 4. Blood Inventory Table
CREATE TABLE IF NOT EXISTS blood_inventory (
    inventory_id INT AUTO_INCREMENT PRIMARY KEY,
    hospital_id INT NOT NULL,
    component_id INT NOT NULL,
    blood_group VARCHAR(10) NOT NULL CHECK (blood_group IN ('A+', 'A-', 'B+', 'B-', 'AB+', 'AB-', 'O+', 'O-')),
    units_available INT NOT NULL DEFAULT 0,
    received_date DATE NOT NULL,
    expiry_date DATE NOT NULL,
    status VARCHAR(50) NOT NULL DEFAULT 'Available' CHECK (status IN ('Available', 'Expiring', 'Expired', 'Allocated', 'Transferred')),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (hospital_id) REFERENCES hospitals(hospital_id) ON DELETE CASCADE,
    FOREIGN KEY (component_id) REFERENCES blood_components(component_id) ON DELETE CASCADE
);

-- 5. Blood Requests Table
CREATE TABLE IF NOT EXISTS blood_requests (
    request_id INT AUTO_INCREMENT PRIMARY KEY,
    hospital_id INT NOT NULL,
    component_id INT NOT NULL,
    blood_group VARCHAR(10) NOT NULL CHECK (blood_group IN ('A+', 'A-', 'B+', 'B-', 'AB+', 'AB-', 'O+', 'O-')),
    units_requested INT NOT NULL,
    request_date DATE NOT NULL,
    status VARCHAR(50) NOT NULL DEFAULT 'Pending' CHECK (status IN ('Pending', 'Fulfilled', 'Cancelled')),
    priority VARCHAR(50) NOT NULL DEFAULT 'Routine' CHECK (priority IN ('Routine', 'Urgent', 'Emergency')),
    event_type VARCHAR(100) DEFAULT 'None',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (hospital_id) REFERENCES hospitals(hospital_id) ON DELETE CASCADE,
    FOREIGN KEY (component_id) REFERENCES blood_components(component_id) ON DELETE CASCADE
);

-- 6. Blood Donations Table
CREATE TABLE IF NOT EXISTS blood_donations (
    donation_id INT AUTO_INCREMENT PRIMARY KEY,
    hospital_id INT NOT NULL,
    donor_name VARCHAR(150) NOT NULL,
    blood_group VARCHAR(10) NOT NULL CHECK (blood_group IN ('A+', 'A-', 'B+', 'B-', 'AB+', 'AB-', 'O+', 'O-')),
    component_id INT NOT NULL,
    units_donated INT NOT NULL DEFAULT 1,
    donation_date DATE NOT NULL,
    expiry_date DATE NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (hospital_id) REFERENCES hospitals(hospital_id) ON DELETE CASCADE,
    FOREIGN KEY (component_id) REFERENCES blood_components(component_id) ON DELETE CASCADE
);

-- 7. Emergency Events Table
CREATE TABLE IF NOT EXISTS emergency_events (
    event_id INT AUTO_INCREMENT PRIMARY KEY,
    event_name VARCHAR(150) NOT NULL,
    event_type VARCHAR(100) NOT NULL CHECK (event_type IN ('Accident', 'Disaster', 'Festival', 'Outbreak', 'Mass Casualty')),
    start_date DATE NOT NULL,
    end_date DATE NOT NULL,
    severity VARCHAR(50) NOT NULL CHECK (severity IN ('Low', 'Medium', 'High')),
    demand_multiplier DECIMAL(3, 2) NOT NULL DEFAULT 1.00
);

-- 8. Predictions Table
CREATE TABLE IF NOT EXISTS predictions (
    prediction_id INT AUTO_INCREMENT PRIMARY KEY,
    hospital_id INT NOT NULL,
    component_id INT NOT NULL,
    blood_group VARCHAR(10) NOT NULL CHECK (blood_group IN ('A+', 'A-', 'B+', 'B-', 'AB+', 'AB-', 'O+', 'O-')),
    prediction_date DATE NOT NULL,
    predicted_demand DECIMAL(10, 2) NOT NULL,
    confidence_interval_low DECIMAL(10, 2) NOT NULL,
    confidence_interval_high DECIMAL(10, 2) NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (hospital_id) REFERENCES hospitals(hospital_id) ON DELETE CASCADE,
    FOREIGN KEY (component_id) REFERENCES blood_components(component_id) ON DELETE CASCADE
);

-- 9. Allocation History Table
CREATE TABLE IF NOT EXISTS allocation_history (
    allocation_id INT AUTO_INCREMENT PRIMARY KEY,
    source_hospital_id INT NOT NULL,
    destination_hospital_id INT NOT NULL,
    component_id INT NOT NULL,
    blood_group VARCHAR(10) NOT NULL CHECK (blood_group IN ('A+', 'A-', 'B+', 'B-', 'AB+', 'AB-', 'O+', 'O-')),
    units_transferred INT NOT NULL,
    transfer_date DATE NOT NULL,
    status VARCHAR(50) NOT NULL DEFAULT 'Pending' CHECK (status IN ('Pending', 'In Transit', 'Completed', 'Cancelled')),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (source_hospital_id) REFERENCES hospitals(hospital_id) ON DELETE CASCADE,
    FOREIGN KEY (destination_hospital_id) REFERENCES hospitals(hospital_id) ON DELETE CASCADE,
    FOREIGN KEY (component_id) REFERENCES blood_components(component_id) ON DELETE CASCADE
);

-- 10. Alerts Table
CREATE TABLE IF NOT EXISTS alerts (
    alert_id INT AUTO_INCREMENT PRIMARY KEY,
    hospital_id INT NOT NULL,
    component_id INT NOT NULL,
    blood_group VARCHAR(10) NOT NULL CHECK (blood_group IN ('A+', 'A-', 'B+', 'B-', 'AB+', 'AB-', 'O+', 'O-')),
    alert_type VARCHAR(100) NOT NULL CHECK (alert_type IN ('Shortage', 'Expiry Risk')),
    severity VARCHAR(50) NOT NULL CHECK (severity IN ('Medium', 'Critical')),
    message TEXT NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (hospital_id) REFERENCES hospitals(hospital_id) ON DELETE CASCADE,
    FOREIGN KEY (component_id) REFERENCES blood_components(component_id) ON DELETE CASCADE
);

-- Creating Indexes for Performance
CREATE INDEX IF NOT EXISTS idx_inventory_expiry ON blood_inventory(expiry_date);
CREATE INDEX IF NOT EXISTS idx_requests_date ON blood_requests(request_date);
CREATE INDEX IF NOT EXISTS idx_predictions_date ON predictions(prediction_date);
CREATE INDEX IF NOT EXISTS idx_allocation_date ON allocation_history(transfer_date);
CREATE INDEX IF NOT EXISTS idx_inventory_composite ON blood_inventory(hospital_id, component_id, blood_group);
CREATE INDEX IF NOT EXISTS idx_requests_composite ON blood_requests(hospital_id, component_id, blood_group);
