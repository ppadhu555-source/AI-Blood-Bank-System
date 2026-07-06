import os
import pandas as pd
import numpy as np
import logging
from sklearn.preprocessing import LabelEncoder
import joblib

# Setup logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

# Paths
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATASET_DIR = os.path.join(BASE_DIR, "dataset")
SAVED_MODELS_DIR = os.path.join(BASE_DIR, "saved_models")

os.makedirs(SAVED_MODELS_DIR, exist_ok=True)

class DataPreprocessor:
    def __init__(self):
        self.encoders = {}
        
    def clean_requests(self, df):
        """Cleans and validates the blood requests dataframe."""
        logger.info(f"Cleaning requests dataframe: {len(df)} initial rows.")
        
        # 1. Drop duplicates
        df = df.drop_duplicates()
        
        # 2. Date conversion
        df['request_date'] = pd.to_datetime(df['request_date'])
        
        # 3. Handle missing values
        df['event_type'] = df['event_type'].fillna('None')
        df['priority'] = df['priority'].fillna('Routine')
        df['status'] = df['status'].fillna('Pending')
        df['units_requested'] = df['units_requested'].fillna(1)
        
        # 4. Data validation
        # Keep only positive units requested
        df = df[df['units_requested'] > 0]
        # Keep only valid blood groups
        valid_groups = ['A+', 'A-', 'B+', 'B-', 'AB+', 'AB-', 'O+', 'O-']
        df = df[df['blood_group'].isin(valid_groups)]
        
        # 5. Outlier handling
        # Max limit check: cap requests at 30 units (extreme outlier filter)
        df['units_requested'] = df['units_requested'].clip(upper=30)
        
        logger.info(f"Requests cleaned: {len(df)} rows remain.")
        return df

    def clean_inventory(self, df):
        """Cleans and validates the blood inventory dataframe."""
        logger.info(f"Cleaning inventory dataframe: {len(df)} initial rows.")
        
        df = df.drop_duplicates()
        
        df['received_date'] = pd.to_datetime(df['received_date'])
        df['expiry_date'] = pd.to_datetime(df['expiry_date'])
        
        df['units_available'] = df['units_available'].fillna(0)
        df = df[df['units_available'] >= 0]
        
        valid_groups = ['A+', 'A-', 'B+', 'B-', 'AB+', 'AB-', 'O+', 'O-']
        df = df[df['blood_group'].isin(valid_groups)]
        
        logger.info(f"Inventory cleaned: {len(df)} rows remain.")
        return df

    def clean_donations(self, df):
        """Cleans and validates the blood donations dataframe."""
        logger.info(f"Cleaning donations dataframe: {len(df)} initial rows.")
        
        df = df.drop_duplicates()
        
        df['donation_date'] = pd.to_datetime(df['donation_date'])
        df['expiry_date'] = pd.to_datetime(df['expiry_date'])
        
        df['units_donated'] = df['units_donated'].fillna(1)
        df = df[df['units_donated'] > 0]
        
        valid_groups = ['A+', 'A-', 'B+', 'B-', 'AB+', 'AB-', 'O+', 'O-']
        df = df[df['blood_group'].isin(valid_groups)]
        
        logger.info(f"Donations cleaned: {len(df)} rows remain.")
        return df

    def fit_encoders(self, requests_df):
        """Fits label encoders for categorical columns to be used in ML."""
        logger.info("Fitting categorical label encoders...")
        
        # We need to encode: blood_group, event_type, priority
        categorical_cols = ['blood_group', 'priority', 'event_type']
        
        for col in categorical_cols:
            le = LabelEncoder()
            # Fit on unique values of request data to be robust
            le.fit(requests_df[col].astype(str).unique())
            self.encoders[col] = le
            # Save encoder to disk
            joblib.dump(le, os.path.join(SAVED_MODELS_DIR, f"{col}_encoder.joblib"))
            logger.info(f"Saved LabelEncoder for {col}.")
            
    def transform_categorical(self, df):
        """Transforms categorical variables using fitted label encoders."""
        df_encoded = df.copy()
        for col, le in self.encoders.items():
            if col in df_encoded.columns:
                # Handle unseen values by mapping them to first class if not matched
                classes = dict(zip(le.classes_, le.transform(le.classes_)))
                default_class = le.transform([le.classes_[0]])[0]
                df_encoded[col] = df_encoded[col].astype(str).map(classes).fillna(default_class).astype(int)
        return df_encoded

def main():
    logger.info("Starting preprocessing step...")
    
    # Load raw CSVs
    try:
        req_df = pd.read_csv(os.path.join(DATASET_DIR, "blood_requests.csv"))
        inv_df = pd.read_csv(os.path.join(DATASET_DIR, "blood_inventory.csv"))
        don_df = pd.read_csv(os.path.join(DATASET_DIR, "blood_donations.csv"))
        hosp_df = pd.read_csv(os.path.join(DATASET_DIR, "hospitals.csv"))
        comp_df = pd.read_csv(os.path.join(DATASET_DIR, "blood_components.csv"))
    except FileNotFoundError as e:
        logger.error(f"Raw CSV files not found. Please run dataset_generator.py first. Error: {e}")
        return
        
    preprocessor = DataPreprocessor()
    
    # Clean data
    clean_req = preprocessor.clean_requests(req_df)
    clean_inv = preprocessor.clean_inventory(inv_df)
    clean_don = preprocessor.clean_donations(don_df)
    
    # Fit and save encoders based on cleaned requests
    preprocessor.fit_encoders(clean_req)
    
    # Save cleaned files
    clean_req.to_csv(os.path.join(DATASET_DIR, "cleaned_requests.csv"), index=False)
    clean_inv.to_csv(os.path.join(DATASET_DIR, "cleaned_inventory.csv"), index=False)
    clean_don.to_csv(os.path.join(DATASET_DIR, "cleaned_donations.csv"), index=False)
    
    logger.info("Saved cleaned CSV files to dataset/ directory.")

if __name__ == "__main__":
    main()
