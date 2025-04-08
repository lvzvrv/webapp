from sqlalchemy import create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
import os

db_host = os.getenv('POSTGRES_HOST')
db_user = os.getenv('POSTGRES_USER')
db_dbname = os.getenv('POSTGRES_DB')
db_password = os.getenv('POSTGRES_PASSWORD')

DATABASE_URL = f"postgresql://{db_user}:{db_password}@{db_host}:5432/{db_dbname}"

engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()
