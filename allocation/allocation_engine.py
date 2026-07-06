import os
import sys
import math
import pandas as pd
from datetime import datetime, date, timedelta
from sqlalchemy import text

# Add parent directory to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from database.db_manager import SessionLocal

# Compatibility map: Key can donate to Values
BLOOD_COMPATIBILITY = {
    'O-': ['O-', 'O+', 'A-', 'A+', 'B-', 'B+', 'AB-', 'AB+'],
    'O+': ['O+', 'A+', 'B+', 'AB+'],
    'A-': ['A-', 'A+', 'AB-', 'AB+'],
    'A+': ['A+', 'AB+'],
    'B-': ['B-', 'B+', 'AB-', 'AB+'],
    'B+': ['B+', 'AB+'],
    'AB-': ['AB-', 'AB+'],
    'AB+': ['AB+']
}

def haversine_distance(lat1, lon1, lat2, lon2):
    """
    Calculates the great-circle distance between two points on the Earth
    in miles using the Haversine formula.
    """
    # Earth radius in miles
    R = 3958.8
    
    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    delta_phi = math.radians(lat2 - lat1)
    delta_lambda = math.radians(lon2 - lon1)
    
    a = (math.sin(delta_phi / 2) ** 2 +
         math.cos(phi1) * math.cos(phi2) *
         math.sin(delta_lambda / 2) ** 2)
         
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    return R * c

def check_stock_shortages(anchor_date=None):
    """
    Compares current inventory with predictions/demand to detect shortages.
    Returns a list of shortage details per hospital, component, and blood group.
    """
    if anchor_date is None:
        today = date.today()
        anchor_date = date(2026, 7, 5) if today < date(2026, 7, 5) else today
    elif isinstance(anchor_date, str):
        anchor_date = datetime.strptime(anchor_date, "%Y-%m-%d").date()

    session = SessionLocal()
    try:
        # Fetch hospitals list
        hosp_query = text("SELECT hospital_id, name, capacity_beds, safety_stock_ratio, latitude, longitude FROM hospitals")
        hospitals = session.execute(hosp_query).fetchall()
        
        # Fetch components
        comp_query = text("SELECT component_id, name FROM blood_components")
        components = session.execute(comp_query).fetchall()
        
        # We will check shortages for each hospital, component, and blood group combination
        shortages = []
        
        for hosp in hospitals:
            for comp in components:
                for bg in BLOOD_COMPATIBILITY.keys():
                    # 1. Calculate available stock (status='Available' or 'Expiring')
                    stock_query = text("""
                        SELECT SUM(units_available) 
                        FROM blood_inventory 
                        WHERE hospital_id = :hospital_id 
                          AND component_id = :component_id 
                          AND blood_group = :blood_group 
                          AND status IN ('Available', 'Expiring')
                    """)
                    stock_res = session.execute(stock_query, {
                        "hospital_id": hosp.hospital_id,
                        "component_id": comp.component_id,
                        "blood_group": bg
                    }).scalar()
                    
                    available_units = int(stock_res) if stock_res else 0
                    
                    # 2. Get predicted demand for next 3 days
                    pred_query = text("""
                        SELECT SUM(predicted_demand) 
                        FROM predictions 
                        WHERE hospital_id = :hospital_id 
                          AND component_id = :component_id 
                          AND blood_group = :blood_group 
                          AND prediction_date >= :start_date 
                          AND prediction_date <= :end_date
                    """)
                    pred_res = session.execute(pred_query, {
                        "hospital_id": hosp.hospital_id,
                        "component_id": comp.component_id,
                        "blood_group": bg,
                        "start_date": anchor_date,
                        "end_date": anchor_date + timedelta(days=2)
                    }).scalar()
                    
                    # Fallback to historical daily requests if predictions table is empty
                    if pred_res is None or pred_res == 0:
                        hist_query = text("""
                            SELECT SUM(units_requested) / 14.0 * 3.0
                            FROM blood_requests
                            WHERE hospital_id = :hospital_id
                              AND component_id = :component_id
                              AND blood_group = :blood_group
                              AND request_date >= :start_date
                              AND request_date <= :end_date
                        """)
                        hist_res = session.execute(hist_query, {
                            "hospital_id": hosp.hospital_id,
                            "component_id": comp.component_id,
                            "blood_group": bg,
                            "start_date": anchor_date - timedelta(days=14),
                            "end_date": anchor_date
                        }).scalar()
                        # Default baseline if still None
                        predicted_demand = float(hist_res) if hist_res else 2.0
                    else:
                        predicted_demand = float(pred_res)
                        
                    predicted_demand = max(1.0, predicted_demand) # make sure it's at least 1 unit
                    
                    # 3. Calculate safety stock threshold
                    safety_ratio = float(hosp.safety_stock_ratio)
                    safety_threshold = predicted_demand * (1.0 + safety_ratio)
                    
                    # 4. Assess risk level
                    status = "Safe"
                    severity = "Info"
                    if available_units == 0:
                        status = "Critical"
                        severity = "Critical"
                    elif available_units < 0.5 * safety_threshold:
                        status = "Critical"
                        severity = "Critical"
                    elif available_units < safety_threshold:
                        status = "Medium Risk"
                        severity = "Medium"
                        
                    if status != "Safe":
                        shortages.append({
                            "hospital_id": hosp.hospital_id,
                            "hospital_name": hosp.name,
                            "component_id": comp.component_id,
                            "component_name": comp.name,
                            "blood_group": bg,
                            "available_units": available_units,
                            "safety_threshold": round(safety_threshold, 1),
                            "predicted_demand_3d": round(predicted_demand, 1),
                            "status": status,
                            "severity": severity
                        })
                        
        # Save Shortage Alerts in the Database
        if shortages:
            # Delete old Shortage alerts to avoid duplication
            session.execute(text("DELETE FROM alerts WHERE alert_type = 'Shortage'"))
            
            for s in shortages:
                msg = f"{s['status']} shortage of {s['blood_group']} {s['component_name']} at {s['hospital_name']}. Available: {s['available_units']}, Safe Level: {s['safety_threshold']}"
                session.execute(
                    text("""
                        INSERT INTO alerts (hospital_id, component_id, blood_group, alert_type, severity, message)
                        VALUES (:hospital_id, :component_id, :blood_group, 'Shortage', :severity, :message)
                    """),
                    {
                        "hospital_id": s['hospital_id'],
                        "component_id": s['component_id'],
                        "blood_group": s['blood_group'],
                        "severity": s['severity'],
                        "message": msg
                    }
                )
            session.commit()
            
        return shortages
    except Exception as e:
        session.rollback()
        raise e
    finally:
        session.close()

def generate_transfer_recommendations(anchor_date=None):
    """
    Finds hospitals with stock shortages (destination) and pairs them with 
    hospitals that have surplus stock of compatible blood groups (sources).
    Calculates a transfer suitability score and outputs sorted suggestions.
    """
    if anchor_date is None:
        today = date.today()
        anchor_date = date(2026, 7, 5) if today < date(2026, 7, 5) else today
    elif isinstance(anchor_date, str):
        anchor_date = datetime.strptime(anchor_date, "%Y-%m-%d").date()

    session = SessionLocal()
    try:
        # Load shortages
        shortages = check_stock_shortages(anchor_date)
        if not shortages:
            return []
            
        # Get all hospital info (coordinates, safety stock)
        hosp_query = text("SELECT hospital_id, name, latitude, longitude, safety_stock_ratio FROM hospitals")
        hosp_list = session.execute(hosp_query).fetchall()
        hosp_dict = {h.hospital_id: h for h in hosp_list}
        
        recommendations = []
        
        # Iterate over each shortage (destination)
        for dest in shortages:
            dest_hosp_id = dest['hospital_id']
            dest_hosp = hosp_dict[dest_hosp_id]
            component_id = dest['component_id']
            dest_bg = dest['blood_group']
            
            shortage_qty = int(math.ceil(dest['safety_threshold'] - dest['available_units']))
            if shortage_qty <= 0:
                continue
                
            # Scan other hospitals for compatible donor stock
            for src_hosp in hosp_list:
                if src_hosp.hospital_id == dest_hosp_id:
                    continue # cannot transfer to itself
                    
                # Calculate distance between source and destination
                dist = haversine_distance(
                    float(src_hosp.latitude), float(src_hosp.longitude),
                    float(dest_hosp.latitude), float(dest_hosp.longitude)
                )
                
                # Check all compatible donor blood groups
                for src_bg, targets in BLOOD_COMPATIBILITY.items():
                    if dest_bg not in targets:
                        continue # blood group not compatible
                        
                    # Fetch inventory at source hospital for this group & component
                    # We also want to know if there are expiring units in this batch
                    stock_query = text("""
                        SELECT inventory_id, units_available, expiry_date, status
                        FROM blood_inventory
                        WHERE hospital_id = :hospital_id
                          AND component_id = :component_id
                          AND blood_group = :blood_group
                          AND status IN ('Available', 'Expiring')
                          AND units_available > 0
                    """)
                    src_batches = session.execute(stock_query, {
                        "hospital_id": src_hosp.hospital_id,
                        "component_id": component_id,
                        "blood_group": src_bg
                    }).fetchall()
                    
                    if not src_batches:
                        continue
                        
                    total_src_stock = sum(b.units_available for b in src_batches)
                    if total_src_stock <= 0:
                        continue
                        
                    # Calculate safety threshold for the source hospital's own needs
                    # to make sure we don't drain the source hospital dangerously
                    pred_query = text("""
                        SELECT SUM(predicted_demand) 
                        FROM predictions 
                        WHERE hospital_id = :hospital_id 
                          AND component_id = :component_id 
                          AND blood_group = :blood_group 
                          AND prediction_date >= :start_date 
                          AND prediction_date <= :end_date
                    """)
                    src_pred_res = session.execute(pred_query, {
                        "hospital_id": src_hosp.hospital_id,
                        "component_id": component_id,
                        "blood_group": src_bg,
                        "start_date": anchor_date,
                        "end_date": anchor_date + timedelta(days=2)
                    }).scalar()
                    
                    if src_pred_res is None or src_pred_res == 0:
                        # Fallback to historical average
                        hist_query = text("""
                            SELECT SUM(units_requested) / 14.0 * 3.0
                            FROM blood_requests
                            WHERE hospital_id = :hospital_id
                              AND component_id = :component_id
                              AND blood_group = :blood_group
                              AND request_date >= :start_date
                              AND request_date <= :end_date
                        """)
                        src_hist_res = session.execute(hist_query, {
                            "hospital_id": src_hosp.hospital_id,
                            "component_id": component_id,
                            "blood_group": src_bg,
                            "start_date": anchor_date - timedelta(days=14),
                            "end_date": anchor_date
                        }).scalar()
                        src_demand_3d = float(src_hist_res) if src_hist_res else 2.0
                    else:
                        src_demand_3d = float(src_pred_res)
                        
                    src_demand_3d = max(1.0, src_demand_3d)
                    src_safety_threshold = src_demand_3d * (1.0 + float(src_hosp.safety_stock_ratio))
                    
                    # Available surplus at source hospital
                    surplus = total_src_stock - src_safety_threshold
                    
                    # Determine how many units we can transfer
                    # We can transfer up to the shortage amount, but we prefer not to violate source safety stock
                    # unless destination is Critical.
                    transfer_cap = int(total_src_stock)
                    if dest['status'] == 'Medium Risk':
                        # Preserve source safety stock
                        transfer_cap = max(0, int(math.floor(surplus)))
                        
                    if transfer_cap <= 0:
                        continue
                        
                    transfer_units = min(shortage_qty, transfer_cap)
                    if transfer_units <= 0:
                        continue
                        
                    # Calculate matching score
                    # Base score is 100
                    score = 100
                    
                    # Distance penalty: -3 points per mile
                    dist_penalty = dist * 3.0
                    score -= dist_penalty
                    
                    # Compatibility penalty: exact group matches are preferred
                    group_match = (src_bg == dest_bg)
                    if not group_match:
                        # e.g., O- given to A+ gets a penalty to prevent wasting O- blood
                        score -= 20.0
                        
                    # Expiry bonus: if source has expiring units, prioritize transferring them
                    # to prevent waste
                    has_expiring_units = False
                    for batch in src_batches:
                        b_exp = datetime.strptime(str(batch.expiry_date), "%Y-%m-%d").date() if isinstance(batch.expiry_date, str) else batch.expiry_date
                        days_left = (b_exp - anchor_date).days
                        if 0 <= days_left <= 5:
                            has_expiring_units = True
                            
                    if has_expiring_units:
                        score += 30.0 # big bonus for saving expiring units
                        
                    # Safety stock penalty
                    # If we dip below source safety stock, apply a heavy penalty
                    if total_src_stock - transfer_units < src_safety_threshold:
                        score -= 40.0
                        
                    # Urgency bonus
                    if dest['status'] == 'Critical':
                        score += 25.0
                        
                    # Descriptions and details
                    reason = f"Transfer {transfer_units} units of {src_bg} -> {dest_bg} compatible blood from {src_hosp.name} to {dest_hosp.name}."
                    if has_expiring_units:
                        reason += " Prioritizes units nearing expiry to minimize wastage."
                    if dist_penalty > 30:
                        reason += " Note: Higher geographical distance."
                    if total_src_stock - transfer_units < src_safety_threshold:
                        reason += " WARNING: Transfer dips source stock below safety margin."
                        
                    recommendations.append({
                        "source_hospital_id": src_hosp.hospital_id,
                        "source_hospital_name": src_hosp.name,
                        "destination_hospital_id": dest_hosp.hospital_id,
                        "destination_hospital_name": dest_hosp.name,
                        "component_id": component_id,
                        "component_name": dest['component_name'],
                        "source_blood_group": src_bg,
                        "target_blood_group": dest_bg,
                        "units_to_transfer": transfer_units,
                        "distance_miles": round(dist, 2),
                        "transfer_score": round(score, 1),
                        "reason": reason
                    })
                    
        # Sort recommendations by transfer score descending
        recommendations = sorted(recommendations, key=lambda x: x['transfer_score'], reverse=True)
        return recommendations
    except Exception as e:
        logger.error(f"Error generating transfer recommendations: {e}")
        return []
    finally:
        session.close()

def process_allocation_transfer(source_hosp_id, dest_hosp_id, component_id, src_bg, dest_bg, units, anchor_date=None):
    """
    Executes a transfer of blood units in the database.
    Reduces inventory at source hospital and inserts/updates inventory at destination.
    Logs transaction in allocation_history.
    """
    if anchor_date is None:
        today = date.today()
        anchor_date = date(2026, 7, 5) if today < date(2026, 7, 5) else today
        
    session = SessionLocal()
    try:
        # Find matching inventory units at source hospital
        # Order by expiry date ascending to transfer the oldest (but still valid) blood first
        query = text("""
            SELECT inventory_id, units_available, expiry_date, received_date
            FROM blood_inventory
            WHERE hospital_id = :hospital_id
              AND component_id = :component_id
              AND blood_group = :blood_group
              AND status IN ('Available', 'Expiring')
              AND units_available > 0
            ORDER BY expiry_date ASC
        """)
        src_units = session.execute(query, {
            "hospital_id": source_hosp_id,
            "component_id": component_id,
            "blood_group": src_bg
        }).fetchall()
        
        if not src_units:
            return False, "No inventory available at source hospital."
            
        total_available = sum(u.units_available for u in src_units)
        if total_available < units:
            return False, f"Insufficient stock. Requested {units} but only {total_available} available."
            
        units_left_to_transfer = units
        transferred_batches = []
        
        for batch in src_units:
            if units_left_to_transfer <= 0:
                break
                
            batch_units = batch.units_available
            transfer_qty = min(units_left_to_transfer, batch_units)
            
            # Reduce stock in source batch
            if batch_units == transfer_qty:
                # Mark as transferred or delete if it goes to 0
                session.execute(
                    text("UPDATE blood_inventory SET units_available = 0, status = 'Transferred' WHERE inventory_id = :id"),
                    {"id": batch.inventory_id}
                )
            else:
                session.execute(
                    text("UPDATE blood_inventory SET units_available = units_available - :qty WHERE inventory_id = :id"),
                    {"qty": transfer_qty, "id": batch.inventory_id}
                )
                
            transferred_batches.append({
                "qty": transfer_qty,
                "expiry_date": batch.expiry_date,
                "received_date": batch.received_date
            })
            
            units_left_to_transfer -= transfer_qty
            
        # Add inventory at destination hospital (split by their original batch dates)
        for batch in transferred_batches:
            # Check if matching batch already exists at destination (same component, bg, dates)
            dest_query = text("""
                SELECT inventory_id FROM blood_inventory
                WHERE hospital_id = :hospital_id
                  AND component_id = :component_id
                  AND blood_group = :blood_group
                  AND expiry_date = :expiry_date
                  AND status IN ('Available', 'Expiring')
                LIMIT 1
            """)
            existing_id = session.execute(dest_query, {
                "hospital_id": dest_hosp_id,
                "component_id": component_id,
                "blood_group": dest_bg, # notice the blood group becomes the destination blood group (compatible group mapping)
                "expiry_date": batch["expiry_date"]
            }).scalar()
            
            if existing_id:
                session.execute(
                    text("UPDATE blood_inventory SET units_available = units_available + :qty WHERE inventory_id = :id"),
                    {"qty": batch["qty"], "id": existing_id}
                )
            else:
                session.execute(
                    text("""
                        INSERT INTO blood_inventory (hospital_id, component_id, blood_group, units_available, received_date, expiry_date, status)
                        VALUES (:hospital_id, :component_id, :blood_group, :units, :received_date, :expiry_date, 'Available')
                    """),
                    {
                        "hospital_id": dest_hosp_id,
                        "component_id": component_id,
                        "blood_group": dest_bg,
                        "units": batch["qty"],
                        "received_date": batch["received_date"],
                        "expiry_date": batch["expiry_date"]
                    }
                )
                
        # Insert record into allocation history
        session.execute(
            text("""
                INSERT INTO allocation_history (source_hospital_id, destination_hospital_id, component_id, blood_group, units_transferred, transfer_date, status)
                VALUES (:source_hospital_id, :destination_hospital_id, :component_id, :blood_group, :units_transferred, :transfer_date, 'Completed')
            """),
            {
                "source_hospital_id": source_hosp_id,
                "destination_hospital_id": dest_hosp_id,
                "component_id": component_id,
                "blood_group": src_bg,
                "units_transferred": units,
                "transfer_date": anchor_date
            }
        )
        
        session.commit()
        return True, "Transfer executed and logged successfully."
    except Exception as e:
        session.rollback()
        return False, f"Database error during transfer execution: {e}"
    finally:
        session.close()

if __name__ == "__main__":
    recs = generate_transfer_recommendations()
    print(f"Generated {len(recs)} transfer recommendations.")
    for r in recs[:3]:
        print(f"Score: {r['transfer_score']} | {r['reason']}")
