import os
import random
import logging
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from sqlalchemy import text
import sys

# Setup logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

# Add database parent to path to allow import
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from database.db_manager import engine, SessionLocal, init_db

# Set seed for reproducibility
np.random.seed(42)
random.seed(42)

# Helper configurations
BLOOD_GROUPS = ['A+', 'A-', 'B+', 'B-', 'AB+', 'AB-', 'O+', 'O-']
COMPONENTS = {
    'Whole Blood': {'shelf_life': 35, 'temp': '2-6 C'},
    'Red Blood Cells': {'shelf_life': 42, 'temp': '2-6 C'},
    'Fresh Frozen Plasma': {'shelf_life': 365, 'temp': '-18 C or colder'},
    'Platelets': {'shelf_life': 5, 'temp': '20-24 C'}
}

# Distribution of blood groups in general population (approximate)
BLOOD_GROUP_DIST = [0.35, 0.07, 0.25, 0.05, 0.08, 0.02, 0.15, 0.03] # sum = 1.0

# 8 Hospitals in New York/Brooklyn metro area (close enough for blood transfer)
HOSPITAL_DATA = [
    {"name": "City General Hospital", "lat": 40.7128, "lng": -74.0060, "beds": 450, "safety": 0.20},
    {"name": "St. Jude Medical Center", "lat": 40.7250, "lng": -74.0100, "beds": 350, "safety": 0.15},
    {"name": "Memorial Hospital", "lat": 40.7306, "lng": -73.9352, "beds": 500, "safety": 0.25},
    {"name": "Regional Trauma Center", "lat": 40.7589, "lng": -73.9851, "beds": 600, "safety": 0.30},
    {"name": "Valley Health Clinic", "lat": 40.7061, "lng": -73.9969, "beds": 120, "safety": 0.15},
    {"name": "Metro Medical", "lat": 40.7484, "lng": -73.9857, "beds": 400, "safety": 0.20},
    {"name": "Hope Children's Hospital", "lat": 40.7829, "lng": -73.9654, "beds": 250, "safety": 0.15},
    {"name": "Mercy Medical Center", "lat": 40.7000, "lng": -74.0500, "beds": 300, "safety": 0.20}
]

DATASET_DIR = os.path.dirname(os.path.abspath(__file__))

def generate_hospitals():
    """Generates hospital records and returns a DataFrame."""
    df = pd.DataFrame(HOSPITAL_DATA)
    df.index += 1
    df.index.name = 'hospital_id'
    df = df.reset_index()
    # rename columns to match SQL
    df.rename(columns={'lng': 'longitude', 'lat': 'latitude', 'beds': 'capacity_beds', 'safety': 'safety_stock_ratio'}, inplace=True)
    return df

def generate_components():
    """Generates blood component categories."""
    records = []
    for idx, (name, info) in enumerate(COMPONENTS.items(), start=1):
        records.append({
            'component_id': idx,
            'name': name,
            'shelf_life_days': info['shelf_life'],
            'storage_temp_celsius': info['temp']
        })
    return pd.DataFrame(records)

def generate_users(hospital_df):
    """Generates users (Admin and staff for each hospital)."""
    # Using simple plaintext/hashed passwords (we'll hash them in python during import/use simple hashes)
    # Common hash for 'password123': 'pbkdf2:sha256:260000$...' we can use simple SHA256 hashes or plain text for easy seeding,
    # but let's use pbkdf2_sha256 or bcrypt mock or direct sha256. For simplicity, we can do SHA256 of the password.
    import hashlib
    def get_sha256(pwd):
        return hashlib.sha256(pwd.encode()).hexdigest()

    records = [
        {"username": "admin", "password_hash": get_sha256("admin123"), "role": "Admin", "hospital_id": None}
    ]
    for idx, row in hospital_df.iterrows():
        username = row['name'].lower().replace(" ", "_").replace("'", "") + "_staff"
        records.append({
            "username": username,
            "password_hash": get_sha256("staff123"),
            "role": "Hospital Staff",
            "hospital_id": int(row['hospital_id'])
        })
    df = pd.DataFrame(records)
    df.index += 1
    df.index.name = 'user_id'
    return df.reset_index()

def generate_emergency_events(start_date, end_date):
    """Generates historical emergency events that impact blood demand."""
    events = []
    current_date = start_date
    event_id = 1
    
    # Pre-defined types of events
    event_templates = [
        {"name": "Major Highway Pileup", "type": "Accident", "duration": 1, "severity": "High", "multiplier": 1.8},
        {"name": "Regional Flooding", "type": "Disaster", "duration": 5, "severity": "High", "multiplier": 1.5},
        {"name": "Summer Music Festival", "type": "Festival", "duration": 3, "severity": "Medium", "multiplier": 1.3},
        {"name": "New Year Celebrations", "type": "Festival", "duration": 2, "severity": "High", "multiplier": 1.4},
        {"name": "Winter Flu Outbreak", "type": "Outbreak", "duration": 14, "severity": "Medium", "multiplier": 1.25},
        {"name": "Industrial Plant Explosion", "type": "Mass Casualty", "duration": 2, "severity": "High", "multiplier": 2.0},
        {"name": "Seasonal Dengue Spike", "type": "Outbreak", "duration": 21, "severity": "Medium", "multiplier": 1.3},
        {"name": "Independence Day Parade", "type": "Festival", "duration": 1, "severity": "Medium", "multiplier": 1.2}
    ]
    
    # Distribute events over the 2-year range
    delta_days = (end_date - start_date).days
    num_events = 15
    event_days = sorted(random.sample(range(10, delta_days - 30), num_events))
    
    for day_offset in event_days:
        evt_day = start_date + timedelta(days=day_offset)
        template = random.choice(event_templates)
        
        events.append({
            "event_id": event_id,
            "event_name": template["name"],
            "event_type": template["type"],
            "start_date": evt_day.strftime("%Y-%m-%d"),
            "end_date": (evt_day + timedelta(days=template["duration"] - 1)).strftime("%Y-%m-%d"),
            "severity": template["severity"],
            "demand_multiplier": template["multiplier"]
        })
        event_id += 1
        
    return pd.DataFrame(events)

def generate_requests(hospital_df, component_df, events_df, start_date, end_date):
    """Generates 5000+ realistic blood requests with time-series trends."""
    records = []
    current_date = start_date
    delta_days = (end_date - start_date).days
    
    request_id = 1
    
    # Map events to quickly check multipliers
    event_multipliers = {}
    for _, evt in events_df.iterrows():
        evt_start = datetime.strptime(evt['start_date'], "%Y-%m-%d").date()
        evt_end = datetime.strptime(evt['end_date'], "%Y-%m-%d").date()
        curr = evt_start
        while curr <= evt_end:
            event_multipliers[curr] = (evt['event_type'], float(evt['demand_multiplier']))
            curr += timedelta(days=1)

    # Generate daily requests for 2 years (approx 730 days)
    # Average 7-8 requests per day across all hospitals
    for day_idx in range(delta_days + 1):
        curr_date = start_date + timedelta(days=day_idx)
        curr_date_str = curr_date.strftime("%Y-%m-%d")
        
        # Seasonality factors
        month_factor = 1.0 + 0.15 * np.sin(2 * np.pi * curr_date.month / 12)  # seasonal cycle
        day_factor = 1.2 if curr_date.weekday() in [4, 5] else 0.95        # weekend bump
        
        # Check for active emergency event
        active_event_type = 'None'
        event_mult = 1.0
        if curr_date in event_multipliers:
            active_event_type, event_mult = event_multipliers[curr_date]
            
        # Determine number of requests today
        base_requests = int(np.random.poisson(lam=7.5 * month_factor * day_factor * event_mult))
        
        for _ in range(max(1, base_requests)):
            hospital = hospital_df.sample(1).iloc[0]
            component = component_df.sample(1).iloc[0]
            
            # Select blood group based on population distribution
            blood_grp = np.random.choice(BLOOD_GROUPS, p=BLOOD_GROUP_DIST)
            
            # Determine quantity
            # Trauma centers require more units on average
            base_qty = 2.0
            if hospital['name'] == 'Regional Trauma Center':
                base_qty = 4.0
            
            # Emergency/urgent request multiplier
            priority = 'Routine'
            rand_prio = random.random()
            if active_event_type != 'None':
                priority = 'Emergency' if rand_prio > 0.3 else 'Urgent'
            else:
                if rand_prio > 0.92:
                    priority = 'Emergency'
                elif rand_prio > 0.75:
                    priority = 'Urgent'
            
            qty_mult = 2.5 if priority == 'Emergency' else (1.5 if priority == 'Urgent' else 1.0)
            units = int(np.random.lognormal(mean=np.log(base_qty * qty_mult), sigma=0.4))
            units = max(1, min(units, 20)) # clip to realistic range
            
            # Request status
            status = 'Fulfilled'
            if priority == 'Emergency' and random.random() > 0.95:
                status = 'Cancelled'
            elif priority == 'Routine' and random.random() > 0.97:
                status = 'Cancelled'
                
            records.append({
                "request_id": request_id,
                "hospital_id": int(hospital['hospital_id']),
                "component_id": int(component['component_id']),
                "blood_group": blood_grp,
                "units_requested": units,
                "request_date": curr_date_str,
                "status": status,
                "priority": priority,
                "event_type": active_event_type
            })
            request_id += 1
            
    df = pd.DataFrame(records)
    # Ensure we meet minimum 5000 records
    logger.info(f"Generated {len(df)} requests.")
    return df

def generate_inventory(hospital_df, component_df, anchor_date):
    """Generates 2000+ active blood inventory records representing current stock."""
    records = []
    inventory_id = 1
    
    # We want around 2000 active inventory records distributed across hospitals
    # Each record represents a batch/unit of blood
    for idx, hospital in hospital_df.iterrows():
        # Large hospitals have more stock
        cap = hospital['capacity_beds']
        target_records = int(cap * 0.8) # e.g. 600 beds -> 480 inventory records
        
        for _ in range(target_records):
            component = component_df.sample(1).iloc[0]
            blood_grp = np.random.choice(BLOOD_GROUPS, p=BLOOD_GROUP_DIST)
            
            # Received date is within component shelf life before the anchor date
            shelf_life = int(component['shelf_life_days'])
            days_ago = random.randint(0, shelf_life + 5) # some already expired
            received = anchor_date - timedelta(days=days_ago)
            expiry = received + timedelta(days=shelf_life)
            
            units = random.randint(1, 10)
            
            # Status based on expiry relative to anchor_date
            if expiry < anchor_date:
                status = 'Expired'
            elif expiry <= anchor_date + timedelta(days=5):
                status = 'Expiring'
            else:
                status = 'Available'
                
            # Randomly flag some as allocated
            if status == 'Available' and random.random() > 0.90:
                status = 'Allocated'
                
            records.append({
                "inventory_id": inventory_id,
                "hospital_id": int(hospital['hospital_id']),
                "component_id": int(component['component_id']),
                "blood_group": blood_grp,
                "units_available": units,
                "received_date": received.strftime("%Y-%m-%d"),
                "expiry_date": expiry.strftime("%Y-%m-%d"),
                "status": status
            })
            inventory_id += 1
            
    df = pd.DataFrame(records)
    logger.info(f"Generated {len(df)} inventory records.")
    return df

def generate_donations(hospital_df, component_df, start_date, end_date):
    """Generates 1000+ historical and current blood donation records."""
    records = []
    donation_id = 1
    delta_days = (end_date - start_date).days
    
    donor_firstnames = ["John", "Mary", "Robert", "Patricia", "Michael", "Jennifer", "William", "Elizabeth", "David", "Linda", "Richard", "Barbara", "Joseph", "Susan", "Thomas", "Jessica"]
    donor_lastnames = ["Smith", "Johnson", "Williams", "Brown", "Jones", "Garcia", "Miller", "Davis", "Rodriguez", "Martinez", "Hernandez", "Lopez", "Gonzalez", "Wilson", "Anderson", "Thomas"]
    
    # Distribute 1200 donations over the period
    donation_dates = [start_date + timedelta(days=random.randint(0, delta_days)) for _ in range(1200)]
    donation_dates.sort()
    
    for don_date in donation_dates:
        hospital = hospital_df.sample(1).iloc[0]
        component = component_df.sample(1).iloc[0]
        blood_grp = np.random.choice(BLOOD_GROUPS, p=BLOOD_GROUP_DIST)
        
        donor_name = f"{random.choice(donor_firstnames)} {random.choice(donor_lastnames)}"
        units = random.randint(1, 2) # usually 1 or 2 units per donor
        shelf_life = int(component['shelf_life_days'])
        expiry = don_date + timedelta(days=shelf_life)
        
        records.append({
            "donation_id": donation_id,
            "hospital_id": int(hospital['hospital_id']),
            "donor_name": donor_name,
            "blood_group": blood_grp,
            "component_id": int(component['component_id']),
            "units_donated": units,
            "donation_date": don_date.strftime("%Y-%m-%d"),
            "expiry_date": expiry.strftime("%Y-%m-%d")
        })
        donation_id += 1
        
    df = pd.DataFrame(records)
    logger.info(f"Generated {len(df)} donation records.")
    return df

def seed_database(dfs):
    """Seeds the SQL database using pandas dataframes and SQLAlchemy."""
    logger.info("Initializing database schema...")
    init_db()
    
    try:
        # Tables to seed, in correct dependency order
        tables = [
            ("hospitals", dfs["hospitals"]),
            ("blood_components", dfs["components"]),
            ("users", dfs["users"]),
            ("emergency_events", dfs["emergency_events"]),
            ("blood_requests", dfs["requests"]),
            ("blood_inventory", dfs["inventory"]),
            ("blood_donations", dfs["donations"])
        ]
        
        with engine.begin() as conn:
            for table_name, df in tables:
                # Clear existing data first
                logger.info(f"Seeding table: {table_name} ({len(df)} records)...")
                conn.execute(text(f"DELETE FROM {table_name}"))
                # Write to SQL using the active connection
                df.to_sql(table_name, con=conn, if_exists='append', index=False)
                
        logger.info("Database seeded successfully with generated datasets!")
    except Exception as e:
        logger.error(f"Failed to seed database: {e}")
        raise e

def main():
    """Main execution block to generate data and save to CSV."""
    os.makedirs(DATASET_DIR, exist_ok=True)
    
    # Anchor date is "today" in local time context
    anchor_date = datetime(2026, 7, 5).date()
    start_date = anchor_date - timedelta(days=730) # 2 years historical data
    end_date = anchor_date
    
    logger.info(f"Generating datasets with anchor date: {anchor_date}")
    
    # Generate dataframes
    hospitals = generate_hospitals()
    components = generate_components()
    users = generate_users(hospitals)
    emergency_events = generate_emergency_events(start_date, end_date)
    requests = generate_requests(hospitals, components, emergency_events, start_date, end_date)
    inventory = generate_inventory(hospitals, components, anchor_date)
    donations = generate_donations(hospitals, components, start_date, end_date)
    
    # Save CSVs
    hospitals.to_csv(os.path.join(DATASET_DIR, "hospitals.csv"), index=False)
    components.to_csv(os.path.join(DATASET_DIR, "blood_components.csv"), index=False)
    users.to_csv(os.path.join(DATASET_DIR, "users.csv"), index=False)
    emergency_events.to_csv(os.path.join(DATASET_DIR, "emergency_events.csv"), index=False)
    requests.to_csv(os.path.join(DATASET_DIR, "blood_requests.csv"), index=False)
    inventory.to_csv(os.path.join(DATASET_DIR, "blood_inventory.csv"), index=False)
    donations.to_csv(os.path.join(DATASET_DIR, "blood_donations.csv"), index=False)
    
    logger.info("Saved CSV datasets to dataset/ folder.")
    
    # Seeding database
    dfs = {
        "hospitals": hospitals,
        "components": components,
        "users": users,
        "emergency_events": emergency_events,
        "requests": requests,
        "inventory": inventory,
        "donations": donations
    }
    
    seed_database(dfs)

if __name__ == "__main__":
    main()
