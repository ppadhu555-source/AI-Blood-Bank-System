import os
import sys
import logging
from datetime import datetime, date, timedelta
from sqlalchemy import text

# Setup logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

# Add parent directory to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from database.db_manager import SessionLocal

def get_expiry_alerts(anchor_date=None):
    """
    Scans the blood_inventory table for expired units and units expiring in 1, 3, 5, or 7 days.
    Generates alerts and saves them to the database.
    """
    if anchor_date is None:
        # Default to the simulation anchor date if today is before 2026
        today = date.today()
        if today < date(2026, 7, 5):
            anchor_date = date(2026, 7, 5)
        else:
            anchor_date = today
    elif isinstance(anchor_date, str):
        anchor_date = datetime.strptime(anchor_date, "%Y-%m-%d").date()

    session = SessionLocal()
    try:
        # 1. Update status of units that have expired in the database
        session.execute(
            text("""
                UPDATE blood_inventory 
                SET status = 'Expired' 
                WHERE expiry_date < :anchor_date AND status != 'Expired'
            """),
            {"anchor_date": anchor_date}
        )
        # Update units that are expiring (within 5 days) but marked as Available
        session.execute(
            text("""
                UPDATE blood_inventory 
                SET status = 'Expiring' 
                WHERE expiry_date >= :anchor_date 
                  AND expiry_date <= :expiring_limit 
                  AND status = 'Available'
            """),
            {
                "anchor_date": anchor_date,
                "expiring_limit": anchor_date + timedelta(days=5)
            }
        )
        session.commit()

        # 2. Fetch inventory records to build alerts
        query = text("""
            SELECT i.inventory_id, i.hospital_id, h.name as hospital_name, 
                   i.component_id, c.name as component_name, 
                   i.blood_group, i.units_available, i.expiry_date, i.status
            FROM blood_inventory i
            JOIN hospitals h ON i.hospital_id = h.hospital_id
            JOIN blood_components c ON i.component_id = c.component_id
            WHERE i.units_available > 0 AND i.status != 'Transferred' AND i.status != 'Allocated'
        """)
        
        result = session.execute(query).fetchall()
        
        alerts_to_insert = []
        expiry_details = []
        
        for row in result:
            exp_date = datetime.strptime(str(row.expiry_date), "%Y-%m-%d").date() if isinstance(row.expiry_date, str) else row.expiry_date
            days_to_expiry = (exp_date - anchor_date).days
            
            alert_type = None
            severity = None
            message = ""
            
            if days_to_expiry < 0:
                alert_type = "Expiry Risk"
                severity = "Critical"
                message = f"{row.units_available} units of {row.blood_group} {row.component_name} at {row.hospital_name} have EXPIRED on {row.expiry_date}."
            elif days_to_expiry == 0:
                alert_type = "Expiry Risk"
                severity = "Critical"
                message = f"{row.units_available} units of {row.blood_group} {row.component_name} at {row.hospital_name} expire TODAY!"
            elif days_to_expiry == 1:
                alert_type = "Expiry Risk"
                severity = "Critical"
                message = f"{row.units_available} units of {row.blood_group} {row.component_name} at {row.hospital_name} expire tomorrow (1 day remaining)."
            elif days_to_expiry <= 3:
                alert_type = "Expiry Risk"
                severity = "Critical"
                message = f"{row.units_available} units of {row.blood_group} {row.component_name} at {row.hospital_name} expire in {days_to_expiry} days."
            elif days_to_expiry <= 5:
                alert_type = "Expiry Risk"
                severity = "Medium"
                message = f"{row.units_available} units of {row.blood_group} {row.component_name} at {row.hospital_name} expire in {days_to_expiry} days."
            elif days_to_expiry <= 7:
                alert_type = "Expiry Risk"
                severity = "Medium"
                message = f"{row.units_available} units of {row.blood_group} {row.component_name} at {row.hospital_name} expire in 7 days."
                
            if alert_type:
                # Add to detailed report list
                expiry_details.append({
                    "inventory_id": row.inventory_id,
                    "hospital_id": row.hospital_id,
                    "hospital_name": row.hospital_name,
                    "component_id": row.component_id,
                    "component_name": row.component_name,
                    "blood_group": row.blood_group,
                    "units": row.units_available,
                    "expiry_date": row.expiry_date,
                    "days_remaining": days_to_expiry,
                    "severity": severity,
                    "message": message
                })
                
                # Prepare DB Alert entry
                alerts_to_insert.append({
                    "hospital_id": row.hospital_id,
                    "component_id": row.component_id,
                    "blood_group": row.blood_group,
                    "alert_type": "Expiry Risk",
                    "severity": severity,
                    "message": message
                })
        
        # 3. Seed alerts into database table
        if alerts_to_insert:
            # Delete old Expiry Risk alerts to avoid clutter
            session.execute(text("DELETE FROM alerts WHERE alert_type = 'Expiry Risk'"))
            
            for alert in alerts_to_insert:
                session.execute(
                    text("""
                        INSERT INTO alerts (hospital_id, component_id, blood_group, alert_type, severity, message)
                        VALUES (:hospital_id, :component_id, :blood_group, :alert_type, :severity, :message)
                    """),
                    alert
                )
            session.commit()
            
        logger.info(f"Processed {len(expiry_details)} expiry alerts.")
        return expiry_details
    except Exception as e:
        session.rollback()
        logger.error(f"Error checking expiry alerts: {e}")
        return []
    finally:
        session.close()

if __name__ == "__main__":
    alerts = get_expiry_alerts()
    for a in alerts[:5]:
        print(f"[{a['severity']}] {a['message']}")
