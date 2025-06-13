from .models import users
from .database import database
from .security import hash_password

async def create_user(user_in):
    hashed_pw = hash_password(user_in.password)
    query = users.insert().values(email=user_in.email, password=hashed_pw)
    await database.execute(query)

async def get_user_by_email(email: str):
    query = users.select().where(users.c.email == email)
    return await database.fetch_one(query)
