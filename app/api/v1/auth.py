from fastapi import APIRouter, HTTPException, Response
from authx import AuthX, AuthXConfig

from app.schemas.auth import UserLoginSchema


router = APIRouter()

config = AuthXConfig()
config.JWT_SECRET_KEY = "SECRET_KEY"
config.JWT_ACCESS_COOKIE_NAME = "my_access_token"
config.JWT_TOKEN_LOCATION = ["cookies"]

security = AuthX(config=config)


@router.post("/auth/register")
async def create_user():
    ...

@router.post("/auth/login")
async def login(creds: UserLoginSchema, response: Response):
    if creds.password == "test" and creds.username == "test":
        token = security.create_access_token(uid="1234")
        response.set_cookie(config.JWT_ACCESS_COOKIE_NAME, token, secure=True)
        return {"access_token": token}
    raise HTTPException(status_code=401, detail="Incorrect username or password")



@router.post("/auth/refresh")
async def refresh_token():
    ...


@router.post("/auth/logout")
async def logout_user():
    ...


@router.get("/users/me")
async def current_user():
    ...

