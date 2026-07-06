import os
import pandas as pd
import numpy as np
import logging
from datetime import datetime, timedelta
import joblib

# Setup logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

# Paths
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATASET_DIR = os.path.join(BASE_DIR, "dataset")
SAVED_MODELS_DIR = os.path.join(BASE_DIR, "saved_models")

def load_encoder(col_name):
    """Loads a saved LabelEncoder from saved_models directory."""
    path = os.path.join(SAVED_MODELS_DIR, f"{col_name}_encoder.joblib")
    if os.path.exists(path):
        return joblib.load(path)
    return None

def engineer_features():
    logger.info("Starting Feature Engineering...")
    
    # Load cleaned requests and support tables
    try:
        req_df = pd.read_csv(os.path.join(DATASET_DIR, "cleaned_requests.csv"))
        hosp_df = pd.read_csv(os.path.join(DATASET_DIR, "hospitals.csv"))
        comp_df = pd.read_csv(os.path.join(DATASET_DIR, "blood_components.csv"))
        events_df = pd.read_csv(os.path.join(DATASET_DIR, "emergency_events.csv"))
    except FileNotFoundError as e:
        logger.error(f"Required cleaned CSV files not found. Ensure preprocessing.py has run successfully. Error: {e}")
        return
        
    # Convert dates to datetime objects
    req_df['request_date'] = pd.to_datetime(req_df['request_date'])
    events_df['start_date'] = pd.to_datetime(events_df['start_date'])
    events_df['end_date'] = pd.to_datetime(events_df['end_date'])
    
    # Step 1: Create a full grid of all combinations of dates, hospitals, components, and blood groups
    # This prevents the forecasting model from only training on positive demand records
    dates = pd.date_range(start=req_df['request_date'].min(), end=req_df['request_date'].max(), freq='D')
    hospitals = hosp_df['hospital_id'].unique()
    components = comp_df['component_id'].unique()
    blood_groups = req_df['blood_group'].unique()
    
    logger.info("Generating complete time-series grid combinations...")
    grid = pd.MultiIndex.from_product(
        [dates, hospitals, components, blood_groups], 
        names=['date', 'hospital_id', 'component_id', 'blood_group']
    ).to_frame().reset_index(drop=True)
    
    # Step 2: Aggregate historical daily requests
    # Sum the requested units by date, hospital, component, and blood group
    agg_req = req_df.groupby(['request_date', 'hospital_id', 'component_id', 'blood_group'])['units_requested'].sum().reset_index()
    agg_req.rename(columns={'request_date': 'date', 'units_requested': 'daily_demand'}, inplace=True)
    
    # Step 3: Merge grid with aggregated demand, filling NaNs with 0 (no request = zero demand)
    data = pd.merge(grid, agg_req, on=['date', 'hospital_id', 'component_id', 'blood_group'], how='left')
    data['daily_demand'] = data['daily_demand'].fillna(0)
    
    # Step 4: Extract Date Features
    logger.info("Extracting basic date and seasonality features...")
    data['dayofweek'] = data['date'].dt.dayofweek
    data['month'] = data['date'].dt.month
    data['year'] = data['date'].dt.year
    
    # Step 5: Incorporate Emergency and Holiday Flags
    # Map events to grid dates
    logger.info("Mapping emergency and holiday events...")
    events_list = []
    for _, evt in events_df.iterrows():
        evt_dates = pd.date_range(start=evt['start_date'], end=evt['end_date'], freq='D')
        for d in evt_dates:
            events_list.append({
                'date': d,
                'event_type': evt['event_type'],
                'demand_multiplier': evt['demand_multiplier']
            })
    
    if events_list:
        ev_df = pd.DataFrame(events_list).groupby('date').agg({
            'event_type': 'first',
            'demand_multiplier': 'max'
        }).reset_index()
        data = pd.merge(data, ev_df, on='date', how='left')
    else:
        data['event_type'] = 'None'
        data['demand_multiplier'] = 1.0
        
    data['event_type'] = data['event_type'].fillna('None')
    data['demand_multiplier'] = data['demand_multiplier'].fillna(1.0)
    
    # Binary flags
    data['emergency_flag'] = data['event_type'].apply(lambda x: 1 if x in ['Accident', 'Disaster', 'Mass Casualty'] else 0)
    data['holiday_flag'] = data['event_type'].apply(lambda x: 1 if x == 'Festival' else 0)
    
    # Step 6: Merge Hospital features
    logger.info("Merging hospital capacities...")
    data = pd.merge(data, hosp_df[['hospital_id', 'capacity_beds']], on='hospital_id', how='left')
    
    # Step 7: Time-series lag and rolling statistics
    # Sort dataset to calculate lags and rolling means correctly within each combination group
    logger.info("Sorting and computing lag and rolling window features (this might take a moment)...")
    data = data.sort_values(by=['hospital_id', 'component_id', 'blood_group', 'date']).reset_index(drop=True)
    
    group_cols = ['hospital_id', 'component_id', 'blood_group']
    
    # Lags (shift demand by days)
    data['lag_1'] = data.groupby(group_cols)['daily_demand'].shift(1)
    data['lag_7'] = data.groupby(group_cols)['daily_demand'].shift(7)
    data['lag_30'] = data.groupby(group_cols)['daily_demand'].shift(30)
    
    # Rolling averages (min_periods=1 allows calculation even if there aren't enough preceding days at the start)
    data['rolling_mean_7'] = data.groupby(group_cols)['daily_demand'].transform(
        lambda x: x.shift(1).rolling(window=7, min_periods=1).mean()
    )
    data['rolling_mean_30'] = data.groupby(group_cols)['daily_demand'].transform(
        lambda x: x.shift(1).rolling(window=30, min_periods=1).mean()
    )
    
    # Fill remaining shift NaNs with 0
    lag_cols = ['lag_1', 'lag_7', 'lag_30', 'rolling_mean_7', 'rolling_mean_30']
    data[lag_cols] = data[lag_cols].fillna(0)
    
    # Demand Trend: diff between short and long term rolling average
    data['demand_trend'] = data['rolling_mean_7'] - data['rolling_mean_30']
    
    # Step 8: Encode categorical variables for ML (e.g. blood_group, event_type)
    logger.info("Applying Label Encoding for ML modeling...")
    bg_le = load_encoder('blood_group')
    et_le = load_encoder('event_type')
    
    if bg_le:
        data['blood_group_encoded'] = bg_le.transform(data['blood_group'].astype(str))
    else:
        # Fallback if encoder not found
        data['blood_group_encoded'] = pd.factorize(data['blood_group'])[0]
        
    if et_le:
        data['event_type_encoded'] = et_le.transform(data['event_type'].astype(str))
    else:
        # Fallback if encoder not found
        data['event_type_encoded'] = pd.factorize(data['event_type'])[0]
        
    # Write feature engineered dataset to file
    output_path = os.path.join(DATASET_DIR, "features_demand.csv")
    data.to_csv(output_path, index=False)
    logger.info(f"Feature engineering complete. Saved to: {output_path}")

if __name__ == "__main__":
    engineer_features()
