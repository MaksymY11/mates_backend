from pydantic import BaseModel

class UserIn(BaseModel):
    email: str
    password: str

class UserOut(BaseModel):
    message: str

class Token(BaseModel):
    access_token: str
    token_type: str
