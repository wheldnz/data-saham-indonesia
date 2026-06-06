from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base

from app.core.config import settings

from sqlalchemy import event

# SQLite configuration
engine = create_engine(
    settings.SQLALCHEMY_DATABASE_URI, 
    connect_args={
        "check_same_thread": False,
        "timeout": 30  # 30-second timeout to prevent database is locked errors
    }
)

# Keep default SQLite journal mode (DELETE) to avoid disk I/O errors on Windows/OneDrive directories
# Connection timeout of 30 seconds is set in connect_args to handle transient concurrent locks


SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
