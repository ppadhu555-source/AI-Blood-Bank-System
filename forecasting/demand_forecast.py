import os
import sys
import pandas as pd
import numpy as np
from datetime import datetime, date, timedelta
from sqlalchemy import text
import joblib

# Add parent directory to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from database.db_manager import SessionLocal

# Paths
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SAVED_MODELS_DIR = os.path.join(BASE_DIR, "saved_models")

def load_forecaster():
    """Loads the serialized model, encoders, and feature column list."""
    model_path = os.path.join(SAVED_MODELS_DIR, "best_demand_model.joblib")
    features_path = os.path.join(SAVED_MODELS_DIR, "feature_columns.joblib")
    
    if not os.path.exists(model_path) or not os.path.exists(features_path):
        return None, None
        
    model = joblib.load(model_path)
    features = joblib.load(features_path)
    
    # Load encoders
    encoders = {}
    for col in ['blood_group', 'event_type']:
        enc_path = os.path.join(SAVED_MODELS_DIR, f"{col}_encoder.joblib")
        if os.path.exists(enc_path):
            encoders[col] = joblib.load(enc_path)
            
    return model, features, encoders

def generate_forecasts_for_range(start_date, end_date):
    """
    Constructs features and generates demand predictions for all hospital, 
    component, and blood group combinations for the specified date range.
    Saves generated predictions to the database.
    """
    model, feature_cols, encoders = load_forecaster()
    if model is None:
        return False, "Model files not trained or found."
        
    session = SessionLocal()
    try:
        # 1. Fetch hospitals and components
        hospitals = session.execute(text("SELECT hospital_id, capacity_beds FROM hospitals")).fetchall()
        components = session.execute(text("SELECT component_id FROM blood_components")).fetchall()
        
        bg_encoder = encoders.get('blood_group')
        blood_groups = bg_encoder.classes_ if bg_encoder else ['A+', 'A-', 'B+', 'B-', 'AB+', 'AB-', 'O+', 'O-']
        
        # We will loop day-by-day to simulate lag updates correctly
        curr_date = start_date
        while curr_date <= end_date:
            curr_date_str = curr_date.strftime("%Y-%m-%d")
            
            # Check for emergency/holiday events on this day
            evt_query = text("""
                SELECT event_type, demand_multiplier 
                FROM emergency_events 
                WHERE start_date <= :d AND end_date >= :d 
                LIMIT 1
            """)
            evt_res = session.execute(evt_query, {"d": curr_date}).fetchone()
            
            event_type = 'None'
            demand_multiplier = 1.0
            if evt_res:
                event_type = evt_res.event_type
                demand_multiplier = float(evt_res.demand_multiplier)
                
            emergency_flag = 1 if event_type in ['Accident', 'Disaster', 'Mass Casualty'] else 0
            holiday_flag = 1 if event_type == 'Festival' else 0
            
            # Label encode event_type
            et_encoder = encoders.get('event_type')
            et_encoded = et_encoder.transform([event_type])[0] if et_encoder else 0
            
            # Construct feature vectors for all combinations on this day
            rows = []
            
            # Delete any existing predictions for this day to keep it clean
            session.execute(text("DELETE FROM predictions WHERE prediction_date = :d"), {"d": curr_date})
            
            for hosp in hospitals:
                for comp in components:
                    for bg in blood_groups:
                        bg_encoded = bg_encoder.transform([bg])[0] if bg_encoder else 0
                        
                        # --- Compute Lags dynamically from blood_requests in Database ---
                        # Lag 1: Demand yesterday
                        lag_1_val = session.execute(text("""
                            SELECT COALESCE(SUM(units_requested), 0) 
                            FROM blood_requests 
                            WHERE hospital_id = :h AND component_id = :c AND blood_group = :bg 
                              AND request_date = :d
                        """), {"h": hosp.hospital_id, "c": comp.component_id, "bg": bg, "d": curr_date - timedelta(days=1)}).scalar() or 0
                        
                        # Lag 7: Demand 7 days ago
                        lag_7_val = session.execute(text("""
                            SELECT COALESCE(SUM(units_requested), 0) 
                            FROM blood_requests 
                            WHERE hospital_id = :h AND component_id = :c AND blood_group = :bg 
                              AND request_date = :d
                        """), {"h": hosp.hospital_id, "c": comp.component_id, "bg": bg, "d": curr_date - timedelta(days=7)}).scalar() or 0
                        
                        # Lag 30: Demand 30 days ago
                        lag_30_val = session.execute(text("""
                            SELECT COALESCE(SUM(units_requested), 0) 
                            FROM blood_requests 
                            WHERE hospital_id = :h AND component_id = :c AND blood_group = :bg 
                              AND request_date = :d
                        """), {"h": hosp.hospital_id, "c": comp.component_id, "bg": bg, "d": curr_date - timedelta(days=30)}).scalar() or 0
                        
                        # Rolling averages (using simple averages of actual requests)
                        roll_7_val = session.execute(text("""
                            SELECT COALESCE(SUM(units_requested), 0) / 7.0
                            FROM blood_requests 
                            WHERE hospital_id = :h AND component_id = :c AND blood_group = :bg 
                              AND request_date >= :s AND request_date < :d
                        """), {
                            "h": hosp.hospital_id, "c": comp.component_id, "bg": bg, 
                            "s": curr_date - timedelta(days=7), "d": curr_date
                        }).scalar() or 0.0
                        
                        roll_30_val = session.execute(text("""
                            SELECT COALESCE(SUM(units_requested), 0) / 30.0
                            FROM blood_requests 
                            WHERE hospital_id = :h AND component_id = :c AND blood_group = :bg 
                              AND request_date >= :s AND request_date < :d
                        """), {
                            "h": hosp.hospital_id, "c": comp.component_id, "bg": bg, 
                            "s": curr_date - timedelta(days=30), "d": curr_date
                        }).scalar() or 0.0
                        
                        demand_trend = roll_7_val - roll_30_val
                        
                        # Create feature dictionary
                        feat_dict = {
                            'hospital_id': hosp.hospital_id,
                            'component_id': comp.component_id,
                            'blood_group_encoded': bg_encoded,
                            'dayofweek': curr_date.weekday(),
                            'month': curr_date.month,
                            'year': curr_date.year,
                            'demand_multiplier': demand_multiplier,
                            'emergency_flag': emergency_flag,
                            'holiday_flag': holiday_flag,
                            'capacity_beds': hosp.capacity_beds,
                            'lag_1': float(lag_1_val),
                            'lag_7': float(lag_7_val),
                            'lag_30': float(lag_30_val),
                            'rolling_mean_7': float(roll_7_val),
                            'rolling_mean_30': float(roll_30_val),
                            'demand_trend': float(demand_trend)
                        }
                        
                        # Predict
                        feat_row = pd.DataFrame([feat_dict])[feature_cols]
                        pred_demand = model.predict(feat_row)[0]
                        pred_demand = max(0.0, float(pred_demand))
                        
                        # Add a small random variation to mock confidence intervals
                        std_err = 0.15 * pred_demand + 0.5
                        low_ci = max(0.0, pred_demand - 1.96 * std_err)
                        high_ci = pred_demand + 1.96 * std_err
                        
                        session.execute(
                            text("""
                                INSERT INTO predictions (hospital_id, component_id, blood_group, prediction_date, 
                                                         predicted_demand, confidence_interval_low, confidence_interval_high)
                                VALUES (:h, :c, :bg, :pred_date, :pred_demand, :low_ci, :high_ci)
                            """),
                            {
                                "h": hosp.hospital_id,
                                "c": comp.component_id,
                                "bg": bg,
                                "pred_date": curr_date_str,
                                "pred_demand": round(pred_demand, 2),
                                "low_ci": round(low_ci, 2),
                                "high_ci": round(high_ci, 2)
                            }
                        )
                        
            session.commit()
            curr_date += timedelta(days=1)
            
        return True, "Forecasts generated and stored successfully."
    except Exception as e:
        session.rollback()
        return False, f"Failed during forecast generation: {e}"
    finally:
        session.close()

if __name__ == "__main__":
    # Generate 7 days of predictions starting tomorrow
    start = date(2026, 7, 6)
    end = date(2026, 7, 12)
    success, msg = generate_forecasts_for_range(start, end)
    print(f"Status: {success} | Message: {msg}")
