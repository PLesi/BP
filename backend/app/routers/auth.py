#login logout endpointy
from fastapi import APIRouter, FastAPI
from argon2 import PasswordHasher
    
app = FastAPI()
router = APIRouter()
ph = PasswordHasher()

@router.post("/login")
    #autentifikacia uzivatela
    

@router.post("/register")
    