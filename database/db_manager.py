import os
import re
import logging
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker, scoped_session
from dotenv import load_dotenv

# Set up logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

# Load environment variables
load_dotenv()

# Database credentials
DB_HOST = os.getenv("DB_HOST", "localhost")
DB_PORT = os.getenv("DB_PORT", "3306")
DB_USER = os.getenv("DB_USER", "root")
DB_PASS = os.getenv("DB_PASS", "")
DB_NAME = os.getenv("DB_NAME", "blood_bank_db")

# Construct URLs
MYSQL_URL = f"mysql+mysqlconnector://{DB_USER}:{DB_PASS}@{DB_HOST}:{DB_PORT}/{DB_NAME}"
SQLITE_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "blood_bank.db")
SQLITE_URL = f"sqlite:///{SQLITE_PATH}"

# Check environment variable to force SQLite
FORCE_SQLITE = os.getenv("FORCE_SQLITE", "false").lower() == "true"

def get_engine():
    """
    Attempts to connect to MySQL database as configured.
    Falls back to SQLite database if MySQL fails or if configured to do so.
    """
    if FORCE_SQLITE:
        logger.info(f"Using SQLite database by force configuration: {SQLITE_PATH}")
        return create_engine(SQLITE_URL, connect_args={"check_same_thread": False})
    
    try:
        # First, try to connect to the MySQL server (without DB name) to create DB if not exists
        temp_url = f"mysql+mysqlconnector://{DB_USER}:{DB_PASS}@{DB_HOST}:{DB_PORT}"
        temp_engine = create_engine(temp_url)
        with temp_engine.connect() as conn:
            conn.execute(text(f"CREATE DATABASE IF NOT EXISTS {DB_NAME}"))
        temp_engine.dispose()
        
        # Try full connection
        engine = create_engine(MYSQL_URL)
        # Test connection
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        logger.info(f"Successfully connected to MySQL database: {DB_NAME} on {DB_HOST}")
        return engine
    except Exception as e:
        logger.warning(f"Could not connect to MySQL ({e}). Falling back to SQLite.")
        # Ensure database directory exists for SQLite
        os.makedirs(os.path.dirname(SQLITE_PATH), exist_ok=True)
        logger.info(f"Using SQLite database: {SQLITE_PATH}")
        return create_engine(SQLITE_URL, connect_args={"check_same_thread": False})

# Initialize Engine and Session Factory
engine = get_engine()
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
db_session = scoped_session(SessionLocal)

def get_db():
    """
    Dependency helper to yield database sessions.
    """
    db = db_session()
    try:
        yield db
    finally:
        db.close()

def init_db():
    """
    Reads the schema.sql file and executes it to initialize the database structure.
    Handles compatibility adjustments for SQLite if fallback is active.
    """
    schema_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "schema.sql")
    if not os.path.exists(schema_path):
        logger.error(f"Schema file not found at: {schema_path}")
        return False
    
    with open(schema_path, "r", encoding="utf-8") as f:
        schema_sql = f.read()

    is_sqlite = engine.url.drivername == "sqlite"
    
    # Split queries by semicolon, handling comments
    # Remove single line comments
    clean_sql = re.sub(r"--.*", "", schema_sql)
    queries = clean_sql.split(";")
    
    with engine.begin() as conn:
        for query in queries:
            query = query.strip()
            if not query:
                continue
            
            if is_sqlite:
                # SQLite syntax adaptations
                query = query.replace("AUTO_INCREMENT", "")
                query = query.replace("INT PRIMARY KEY", "INTEGER PRIMARY KEY")
                query = query.replace("INT AUTO_INCREMENT PRIMARY KEY", "INTEGER PRIMARY KEY")
                query = query.replace("DECIMAL(9, 6)", "REAL")
                query = query.replace("DECIMAL(3, 2)", "REAL")
                query = query.replace("DECIMAL(10, 2)", "REAL")
                # Drop TIMESTAMP triggers/defaults adjustments if needed
                query = re.sub(r"ON DELETE SET NULL", "", query, flags=re.IGNORECASE)
                
            try:
                conn.execute(text(query))
            except Exception as e:
                logger.error(f"Failed to execute query: {query}\nError: {e}")
                raise e
    logger.info("Database schema initialized successfully.")
    return True

if __name__ == "__main__":
    init_db()
