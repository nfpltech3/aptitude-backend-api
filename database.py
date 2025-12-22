import os
from sqlalchemy import create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker

# 1. Get the DB URL from the environment (Render will provide this)
# If it's not found (like on your laptop), fall back to SQLite
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./test.db")

# 2. Fix the URL for SQLAlchemy (Postgres requires 'postgresql://', not 'postgres://')
if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)

# 3. Create Engine
if "sqlite" in DATABASE_URL:
    # SQLite settings (Local)
    engine = create_engine(
        DATABASE_URL, connect_args={"check_same_thread": False}
    )
else:
    # Postgres settings (Cloud)
    engine = create_engine(DATABASE_URL)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()