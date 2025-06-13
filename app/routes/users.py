from fastapi import APIRouter, HTTPException, Depends
from fastapi.security import APIKeyHeader

from .. import schemas, crud
from ..security import verify_password
from ..auth import create_access_token, verify_access_token

router = APIRouter()

# Simplified token injection for Swagger UI
oauth2_scheme = APIKeyHeader(name="Authorization")

@router.post("/registerUser", response_model=schemas.UserOut)
async def register_user(user: schemas.UserIn):
    existing_user = await crud.get_user_by_email(user.email)
    if existing_user:
        raise HTTPException(status_code=400, detail="User already exists")

    await crud.create_user(user)
    return {"message": "User registered successfully"}

@router.post("/loginUser", response_model=schemas.Token)
async def login_user(user: schemas.UserIn):
    existing_user = await crud.get_user_by_email(user.email)
    if not existing_user or not verify_password(user.password, existing_user["password"]):
        raise HTTPException(status_code=401, detail="Invalid credentials")

    access_token = create_access_token({"sub": user.email})
    return {"access_token": access_token, "token_type": "bearer"}

@router.get("/protected")
async def protected_route(token: str = Depends(oauth2_scheme)):
    # Remove Bearer prefix if present
    token_value = token.split(" ")[1] if token.startswith("Bearer ") else token

    payload = verify_access_token(token_value)
    if not payload:
        raise HTTPException(status_code=401, detail="Invalid token")
    return {"message": f"Welcome, {payload['sub']}!"}
