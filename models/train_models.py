import os
import json
import pandas as pd
import numpy as np
import logging
import joblib

# ML models
from sklearn.linear_model import LinearRegression
from sklearn.tree import DecisionTreeRegressor
from sklearn.ensemble import RandomForestRegressor, GradientBoostingRegressor
from xgboost import XGBRegressor

# Metrics
from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score

# Setup logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

# Paths
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATASET_DIR = os.path.join(BASE_DIR, "dataset")
SAVED_MODELS_DIR = os.path.join(BASE_DIR, "saved_models")

os.makedirs(SAVED_MODELS_DIR, exist_ok=True)

def train_and_evaluate():
    logger.info("Loading feature-engineered demand dataset...")
    
    # Load dataset
    filepath = os.path.join(DATASET_DIR, "features_demand.csv")
    if not os.path.exists(filepath):
        logger.error(f"Dataset not found at {filepath}. Run feature engineering first.")
        return
        
    df = pd.read_csv(filepath)
    df['date'] = pd.to_datetime(df['date'])
    
    # Define features and target
    feature_cols = [
        'hospital_id', 'component_id', 'blood_group_encoded', 
        'dayofweek', 'month', 'year', 'demand_multiplier', 
        'emergency_flag', 'holiday_flag', 'capacity_beds', 
        'lag_1', 'lag_7', 'lag_30', 'rolling_mean_7', 
        'rolling_mean_30', 'demand_trend'
    ]
    target_col = 'daily_demand'
    
    # Chronological Split (Time-Series Cross Validation pattern)
    # Train on first 85% dates, test on last 15% dates
    unique_dates = sorted(df['date'].unique())
    split_idx = int(len(unique_dates) * 0.85)
    split_date = unique_dates[split_idx]
    
    logger.info(f"Splitting data chronologically at date: {split_date}")
    
    train_df = df[df['date'] < split_date]
    test_df = df[df['date'] >= split_date]
    
    X_train = train_df[feature_cols]
    y_train = train_df[target_col]
    X_test = test_df[feature_cols]
    y_test = test_df[target_col]
    
    logger.info(f"Train shapes: {X_train.shape}, Test shapes: {X_test.shape}")
    
    # Define models
    models = {
        "Linear Regression": LinearRegression(),
        "Decision Tree": DecisionTreeRegressor(max_depth=10, random_state=42),
        "Random Forest": RandomForestRegressor(n_estimators=50, max_depth=12, random_state=42, n_jobs=-1),
        "Gradient Boosting": GradientBoostingRegressor(n_estimators=50, max_depth=6, random_state=42),
        "XGBoost": XGBRegressor(n_estimators=50, max_depth=6, learning_rate=0.1, random_state=42, n_jobs=-1)
    }
    
    results = {}
    best_rmse = float('inf')
    best_model_name = None
    best_model = None
    
    # Train and evaluate each model
    for name, model in models.items():
        logger.info(f"Training {name}...")
        model.fit(X_train, y_train)
        
        # Predictions
        y_pred = model.predict(X_test)
        # Demand cannot be negative, clip predictions at 0
        y_pred = np.clip(y_pred, a_min=0, a_max=None)
        
        # Metrics
        mae = mean_absolute_error(y_test, y_pred)
        rmse = np.sqrt(mean_squared_error(y_test, y_pred))
        r2 = r2_score(y_test, y_pred)
        
        results[name] = {
            "MAE": round(float(mae), 4),
            "RMSE": round(float(rmse), 4),
            "R2": round(float(r2), 4)
        }
        
        logger.info(f"{name} Results - MAE: {mae:.4f}, RMSE: {rmse:.4f}, R2: {r2:.4f}")
        
        # Keep track of the best model (using RMSE)
        if rmse < best_rmse:
            best_rmse = rmse
            best_model_name = name
            best_model = model
            
    logger.info(f"\nBest Model: {best_model_name} (RMSE: {best_rmse:.4f})")
    
    # Save the best model
    model_path = os.path.join(SAVED_MODELS_DIR, "best_demand_model.joblib")
    joblib.dump(best_model, model_path)
    logger.info(f"Saved best model to: {model_path}")
    
    # Save features list
    features_path = os.path.join(SAVED_MODELS_DIR, "feature_columns.joblib")
    joblib.dump(feature_cols, features_path)
    
    # Save metrics JSON for the dashboard
    metrics_path = os.path.join(SAVED_MODELS_DIR, "model_metrics.json")
    metrics_payload = {
        "best_model": best_model_name,
        "features": feature_cols,
        "comparison": results
    }
    with open(metrics_path, "w") as f:
        json.dump(metrics_payload, f, indent=4)
    logger.info(f"Saved evaluation metrics to: {metrics_path}")

if __name__ == "__main__":
    train_and_evaluate()
