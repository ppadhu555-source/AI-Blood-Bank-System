import os
import sys
import argparse
import subprocess
import logging

# Set up logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

def run_script(script_path, cwd=None):
    """Utility to run a python script as a subprocess."""
    abs_path = os.path.join(BASE_DIR, script_path)
    logger.info(f"Executing script: {abs_path}")
    
    result = subprocess.run([sys.executable, abs_path], cwd=cwd or BASE_DIR)
    if result.returncode != 0:
        logger.error(f"Script failed with exit code: {result.returncode}")
        return False
    return True

def init_database():
    """Initializes and seeds database with realistic mock data."""
    logger.info("--- Phase 1: Database & Dataset Seeding ---")
    return run_script("dataset/dataset_generator.py")

def train_forecasting_pipeline():
    """Runs data preprocessing, feature engineering, and model training."""
    logger.info("--- Phase 2: Pipeline - Data Preprocessing ---")
    if not run_script("preprocessing/preprocessing.py"):
        return False
        
    logger.info("--- Phase 3: Pipeline - Feature Engineering ---")
    if not run_script("feature_engineering/features.py"):
        return False
        
    logger.info("--- Phase 4: Pipeline - Generating Exploratory Plots ---")
    if not run_script("preprocessing/eda.py"):
        return False
        
    logger.info("--- Phase 5: Pipeline - Machine Learning Model Training ---")
    return run_script("models/train_models.py")

def run_predictions():
    """Generates demand predictions for the next week and stores them in SQL."""
    logger.info("--- Phase 6: Running Demand Predictions ---")
    return run_script("forecasting/demand_forecast.py")

def _python_has_streamlit(python_executable):
    try:
        subprocess.run(
            [
                python_executable,
                "-c",
                "import importlib.util, sys; sys.exit(0 if importlib.util.find_spec('streamlit') else 1)",
            ],
            check=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        return True
    except (subprocess.CalledProcessError, FileNotFoundError):
        return False


def _find_streamlit_python():
    if _python_has_streamlit(sys.executable):
        return sys.executable

    venv_python = os.path.join(BASE_DIR, ".venv", "Scripts", "python.exe") if os.name == "nt" else os.path.join(BASE_DIR, ".venv", "bin", "python")
    if os.path.isfile(venv_python) and _python_has_streamlit(venv_python):
        return venv_python

    return sys.executable


def start_dashboard():
    """Launches the Streamlit Web Application."""
    logger.info("--- Phase 7: Launching Streamlit Dashboard ---")
    app_path = os.path.join(BASE_DIR, "dashboard", "app.py")

    python_executable = _find_streamlit_python()
    logger.info(f"Selected Python executable for Streamlit: {python_executable}")

    try:
        subprocess.run([python_executable, "-m", "streamlit", "run", app_path], check=True)
    except KeyboardInterrupt:
        logger.info("Dashboard stopped by user.")
    except FileNotFoundError:
        logger.error("Failed to launch Streamlit dashboard: Streamlit is not installed in the selected Python environment.")
    except subprocess.CalledProcessError as e:
        logger.error(f"Failed to launch Streamlit dashboard: {e}")

def main():
    parser = argparse.ArgumentParser(description="RedFlow AI - Blood Bank Allocation System Management CLI")
    
    parser.add_argument("--init", action="store_true", help="Initialize the database schema and seed mock data.")
    parser.add_argument("--train", action="store_true", help="Run the preprocessing, feature engineering, and ML training pipeline.")
    parser.add_argument("--forecast", action="store_true", help="Execute forecasting engine to predict next week's demand.")
    parser.add_argument("--dashboard", action="store_true", help="Launch the Streamlit web dashboard application.")
    parser.add_argument("--run-all", action="store_true", help="Run DB init, pipeline training, forecast, and launch the dashboard sequentially.")
    
    args = parser.parse_args()
    
    # If no arguments provided, print help
    if not any(vars(args).values()):
        parser.print_help()
        return
        
    if args.init or args.run_all:
        if not init_database():
            sys.exit(1)
            
    if args.train or args.run_all:
        if not train_forecasting_pipeline():
            sys.exit(1)
            
    if args.forecast or args.run_all:
        if not run_predictions():
            sys.exit(1)
            
    if args.dashboard or args.run_all:
        start_dashboard()

if __name__ == "__main__":
    main()
