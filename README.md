# AI-Powered Blood Bank Demand Forecasting and Smart Blood Allocation System (RedFlow AI)

This is a production-quality, modular, and scalable software system designed as a final year engineering project. The platform uses machine learning to forecast regional blood demand, identifies inventory shortages/expiry risks, and recommends optimal inter-hospital transfers to reduce waste and save lives.

---

## 🚀 Key Features

1. **Dual Database Architecture**: Fully normalized MySQL schemas with a seamless automated SQLite fallback (`blood_bank.db`) for zero-configuration testing.
2. **Realistic Time-Series Generator**: Simulates 2 years of granular clinical records (5,000+ requests, 2,000+ inventory items, 1,000+ donations) across 8 regional hospitals.
3. **ML Forecasting Engine**: Compares Linear Regression, Decision Trees, Random Forests, Gradient Boosting, and XGBoost to predict future demand and serialize the best-performing model.
4. **Smart Allocation Algorithm**: Uses Haversine distance, blood compatibility matrices, urgency markers, and safety stock thresholds to rank optimal hospital transfers.
5. **Expiry Risk Tracker**: Flags units expiring in 1, 3, 5, or 7 days and triggers alerts.
6. **Premium Streamlit Dashboard**: Offers a beautiful, responsive user interface with session authentication (Admin/Staff roles), analytics tabs, manual logging forms, and PDF/CSV report downloads.

---

## 📁 Project Structure

```text
Blood_Bank_System/
│
├── dataset/                     # Generated CSV files (raw & preprocessed)
│   └── dataset_generator.py     # Script to generate raw mock data & seed database
│
├── database/                    # Database models and schema scripts
│   ├── schema.sql               # MySQL/SQLite normalized schema definition
│   └── db_manager.py            # SQLAlchemy manager & dual DB setup
│
├── preprocessing/               # Preprocessing pipelines and EDA scripts
│   ├── preprocessing.py         # Missing value, duplicate, and date cleaning
│   └── eda.py                   # Generation of 8 distinct static analysis plots
│
├── feature_engineering/         # Feature engineering routines
│   └── features.py              # Rolling averages, lags, holiday/emergency flags
│
├── forecasting/                 # Demand prediction modules
│   └── demand_forecast.py       # ML inference wrapper and DB predictor
│
├── allocation/                  # Smart allocation transfer engines
│   └── allocation_engine.py     # Transfer scorer and transfer transaction executor
│
├── expiry/                      # Expiry alerts tracking
│   └── expiry_tracker.py        # Expiry auditor and alerts cataloger
│
├── dashboard/                   # Web interface
│   └── app.py                   # Multi-page Streamlit portal
│
├── saved_models/                # Serialized models and label encoders
│   ├── best_demand_model.joblib
│   └── model_metrics.json       # Training comparison metrics
│
├── graphs/                      # Static EDA charts (populated by eda.py)
│   ├── daily_demand.png
│   └── correlation_matrix.png
│
├── reports/                     # Report generation logic
│   └── reports.py               # PDF (via fpdf2) and CSV compiler
│
├── outputs/                     # Temporary report files & pdf exports
│   └── ...
│
├── tests/                       # Automated unit tests
│   └── test_all.py              # Test suite for DB, ML, distance, compatibility
│
├── requirements.txt             # Project library list
├── main.py                      # Main entry CLI orchestrator
└── README.md                    # Documentation
```

---

## 🛠️ Installation & Setup

### 1. Prerequisites
Ensure you have **Python 3.10+** installed on your Windows machine.

### 2. Environment Setup
Clone the repository folder or navigate to it in VS Code:
```powershell
cd C:\Users\djyot\.gemini\antigravity\scratch\Blood_Bank_System
```

Create a virtual environment and install the required dependencies:
```powershell
python -m venv venv
.\venv\Scripts\activate
pip install -r requirements.txt
```

### 3. Database Configuration (MySQL / SQLite Fallback)
By default, the system will automatically fall back to **SQLite** if it cannot connect to a local MySQL server, creating `database/blood_bank.db` automatically. 

To configure a local MySQL instance:
1. Create a `.env` file in the root directory:
   ```env
   DB_HOST=localhost
   DB_PORT=3306
   DB_USER=your_mysql_user
   DB_PASS=your_mysql_password
   DB_NAME=blood_bank_db
   FORCE_SQLITE=false
   ```
2. Make sure your MySQL service is running.

---

## 💻 How to Run the Application

You can execute the entire pipeline using the orchestrator script `main.py`:

### Step 1: Database Schema Initialization & Seeding
This generates the mock CSV files and seeds the SQL database tables with 8,000+ total rows:
```powershell
python main.py --init
```

### Step 2: Run ML Pipeline & Train Models
This cleans the data, engineers lag/rolling features, generates static charts, and trains the regressors (selecting the best model):
```powershell
python main.py --train
```

### Step 3: Run Future Demand Forecasts
This runs predictions for the upcoming week and stores them in the database:
```powershell
python main.py --forecast
```

### Step 4: Launch Web Dashboard
Starts the Streamlit application on local port 8501:
```powershell
python main.py --dashboard
```

*(Alternatively, you can run all steps sequentially using `python main.py --run-all`)*

---

## 🔒 Session Login Credentials

Use the following seeded accounts to log in to the dashboard:

| Username | Password | Role | Scope |
| :--- | :--- | :--- | :--- |
| `admin` | `admin123` | Admin | Full Access (All Hospitals) |
| `city_general_hospital_staff` | `staff123` | Hospital Staff | Scoped access for City General Hospital |
| `regional_trauma_center_staff` | `staff123` | Hospital Staff | Scoped access for Regional Trauma Center |

---

## 🧪 Testing
To execute the automated unit and integration tests:
```powershell
python -m unittest tests/test_all.py
```

---

## 🔮 Future Scope
- **Blockchain Ledger**: Recording transfers on a private blockchain to prevent tampering and ensure safety tracking.
- **Drone Delivery Routing**: Integrating vehicle routing algorithms for drone dispatching in emergency blood allocation.
- **Deep Learning Models**: Implementing LSTM or Transformer networks for multi-step time-series forecasting.
