from sqlalchemy import create_engine, MetaData
from databases import Database

DATABASE_URL = "postgresql://mates_db_user:7m8lP4Xx6G58F4Eg38CPxRcDWXkdaL5o@dpg-d165nu63jp1c73fbags0-a.oregon-postgres.render.com/mates_db"

database = Database(DATABASE_URL)
metadata = MetaData()

engine = create_engine(
    DATABASE_URL, connect_args={"check_same_thread": False}
)
