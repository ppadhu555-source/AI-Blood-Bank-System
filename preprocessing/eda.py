import os
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import seaborn as sns
import logging

# Setup logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

# Paths
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATASET_DIR = os.path.join(BASE_DIR, "dataset")
GRAPHS_DIR = os.path.join(BASE_DIR, "graphs")

os.makedirs(GRAPHS_DIR, exist_ok=True)

# Set style for plots
sns.set_theme(style="whitegrid")
plt.rcParams['font.family'] = 'sans-serif'
plt.rcParams['font.size'] = 11

def generate_visualizations():
    logger.info("Generating EDA visualizations...")
    
    # Load files
    try:
        features_df = pd.read_csv(os.path.join(DATASET_DIR, "features_demand.csv"))
        inv_df = pd.read_csv(os.path.join(DATASET_DIR, "cleaned_inventory.csv"))
        req_df = pd.read_csv(os.path.join(DATASET_DIR, "cleaned_requests.csv"))
        hosp_df = pd.read_csv(os.path.join(DATASET_DIR, "hospitals.csv"))
        comp_df = pd.read_csv(os.path.join(DATASET_DIR, "blood_components.csv"))
    except FileNotFoundError as e:
        logger.error(f"Cleaned datasets not found. Run dataset_generator.py, preprocessing.py, features.py first. Error: {e}")
        return

    # Convert dates
    features_df['date'] = pd.to_datetime(features_df['date'])
    inv_df['expiry_date'] = pd.to_datetime(inv_df['expiry_date'])
    req_df['request_date'] = pd.to_datetime(req_df['request_date'])
    
    # Merge names for hospitals and components in features for readability
    hosp_map = dict(zip(hosp_df['hospital_id'], hosp_df['name']))
    comp_map = dict(zip(comp_df['component_id'], comp_df['name']))
    
    features_df['hospital_name'] = features_df['hospital_id'].map(hosp_map)
    features_df['component_name'] = features_df['component_id'].map(comp_map)
    req_df['hospital_name'] = req_df['hospital_id'].map(hosp_map)
    req_df['component_name'] = req_df['component_id'].map(comp_map)
    inv_df['hospital_name'] = inv_df['hospital_id'].map(hosp_map)
    inv_df['component_name'] = inv_df['component_id'].map(comp_map)

    # --- 1. Daily Demand Trend ---
    plt.figure(figsize=(12, 6))
    daily_demand = features_df.groupby('date')['daily_demand'].sum().reset_index()
    # Apply rolling average for smoothing
    daily_demand['7_day_ma'] = daily_demand['daily_demand'].rolling(window=7).mean()
    
    plt.plot(daily_demand['date'], daily_demand['daily_demand'], alpha=0.4, label='Daily Total Demand', color='salmon')
    plt.plot(daily_demand['date'], daily_demand['7_day_ma'], label='7-Day Moving Avg', color='firebrick', linewidth=2)
    plt.title('Regional Daily Blood Demand Over Time')
    plt.xlabel('Date')
    plt.ylabel('Units Demanded')
    plt.legend()
    plt.tight_layout()
    plt.savefig(os.path.join(GRAPHS_DIR, "daily_demand.png"), dpi=150)
    plt.close()
    logger.info("Saved daily_demand.png")

    # --- 2. Monthly Demand Pattern ---
    plt.figure(figsize=(10, 6))
    features_df['month_name'] = features_df['date'].dt.strftime('%B')
    monthly_avg = features_df.groupby(['month', 'month_name'])['daily_demand'].sum().reset_index()
    monthly_avg = monthly_avg.sort_values(by='month')
    
    sns.barplot(data=monthly_avg, x='month_name', y='daily_demand', palette='Oranges_r')
    plt.title('Aggregate Monthly Blood Demand')
    plt.xlabel('Month')
    plt.ylabel('Total Units Demanded (2-Yr Period)')
    plt.xticks(rotation=45)
    plt.tight_layout()
    plt.savefig(os.path.join(GRAPHS_DIR, "monthly_demand.png"), dpi=150)
    plt.close()
    logger.info("Saved monthly_demand.png")

    # --- 3. Blood Group Distribution ---
    plt.figure(figsize=(8, 8))
    bg_dist = req_df.groupby('blood_group')['units_requested'].sum().reset_index()
    
    colors = sns.color_palette('pastel')[0:8]
    plt.pie(bg_dist['units_requested'], labels=bg_dist['blood_group'], autopct='%1.1f%%', startangle=140, colors=colors)
    plt.title('Blood Group Demand Distribution')
    plt.tight_layout()
    plt.savefig(os.path.join(GRAPHS_DIR, "blood_group_distribution.png"), dpi=150)
    plt.close()
    logger.info("Saved blood_group_distribution.png")

    # --- 4. Component Demand Distribution ---
    plt.figure(figsize=(8, 5))
    comp_dist = req_df.groupby('component_name')['units_requested'].sum().reset_index()
    
    sns.barplot(data=comp_dist, x='component_name', y='units_requested', palette='Blues_r')
    plt.title('Blood Component Demand Breakdown')
    plt.xlabel('Blood Component')
    plt.ylabel('Total Units Demanded')
    plt.tight_layout()
    plt.savefig(os.path.join(GRAPHS_DIR, "component_distribution.png"), dpi=150)
    plt.close()
    logger.info("Saved component_distribution.png")

    # --- 5. Hospital-wise Demand ---
    plt.figure(figsize=(10, 6))
    hosp_demand = req_df.groupby('hospital_name')['units_requested'].sum().reset_index().sort_values(by='units_requested', ascending=False)
    
    sns.barplot(data=hosp_demand, x='units_requested', y='hospital_name', palette='Reds_r')
    plt.title('Total Historical Blood Demand by Hospital')
    plt.xlabel('Total Units Demanded')
    plt.ylabel('Hospital')
    plt.tight_layout()
    plt.savefig(os.path.join(GRAPHS_DIR, "hospital_wise_demand.png"), dpi=150)
    plt.close()
    logger.info("Saved hospital_wise_demand.png")

    # --- 6. Hospital-wise Current Stock ---
    plt.figure(figsize=(10, 6))
    # Available units in stock (filtering out expired ones)
    active_inv = inv_df[inv_df['status'] != 'Expired']
    hosp_stock = active_inv.groupby('hospital_name')['units_available'].sum().reset_index().sort_values(by='units_available', ascending=False)
    
    sns.barplot(data=hosp_stock, x='units_available', y='hospital_name', palette='Purples_r')
    plt.title('Current Blood Stock Levels by Hospital')
    plt.xlabel('Available Units in Stock')
    plt.ylabel('Hospital')
    plt.tight_layout()
    plt.savefig(os.path.join(GRAPHS_DIR, "hospital_wise_stock.png"), dpi=150)
    plt.close()
    logger.info("Saved hospital_wise_stock.png")

    # --- 7. Expiry Trend Timeline ---
    plt.figure(figsize=(10, 6))
    # Filter for active inventory expiring in the next 15 days
    today = pd.Timestamp(2026, 7, 5)
    expiring_soon = inv_df[(inv_df['expiry_date'] >= today) & (inv_df['expiry_date'] <= today + pd.Timedelta(days=15))]
    exp_timeline = expiring_soon.groupby('expiry_date')['units_available'].sum().reset_index()
    
    plt.bar(exp_timeline['expiry_date'], exp_timeline['units_available'], color='darkred', alpha=0.8)
    plt.title('Upcoming Expirations in the Next 15 Days')
    plt.xlabel('Expiry Date')
    plt.ylabel('Units Expiring')
    plt.xticks(rotation=45)
    plt.tight_layout()
    plt.savefig(os.path.join(GRAPHS_DIR, "expiry_trend.png"), dpi=150)
    plt.close()
    logger.info("Saved expiry_trend.png")

    # --- 8. Correlation Matrix Heatmap ---
    plt.figure(figsize=(10, 8))
    # Select feature columns to check correlation
    feature_cols = ['daily_demand', 'dayofweek', 'month', 'year', 'lag_1', 'lag_7', 'lag_30', 
                    'rolling_mean_7', 'rolling_mean_30', 'demand_trend', 'emergency_flag', 'holiday_flag']
    corr_matrix = features_df[feature_cols].corr()
    
    sns.heatmap(corr_matrix, annot=True, cmap='coolwarm', fmt=".2f", linewidths=0.5)
    plt.title('Forecasting Feature Correlation Matrix')
    plt.tight_layout()
    plt.savefig(os.path.join(GRAPHS_DIR, "correlation_matrix.png"), dpi=150)
    plt.close()
    logger.info("Saved correlation_matrix.png")
    
    logger.info("EDA visualizations generated successfully.")

if __name__ == "__main__":
    generate_visualizations()
