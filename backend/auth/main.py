from fastapi import FastAPI, HTTPException, Depends, Request
from fastapi.security import OAuth2PasswordRequestForm
import mysql.connector, bcrypt, jwt, datetime, os

app = FastAPI()

SECRET_KEY = os.getenv("SECRET_KEY", "supersecreto")

def get_db():
    return mysql.connector.connect(
        host=os.getenv("DB_HOST", "auth_db"),
        user=os.getenv("DB_USER", "user"),
        password=os.getenv("DB_PASSWORD", "root"),
        database=os.getenv("DB_NAME", "auth_db")
    )

@app.post("/login")
def login(form_data: OAuth2PasswordRequestForm = Depends()):
    conn = get_db()
    cursor = conn.cursor(dictionary=True)
    cursor.execute("SELECT * FROM usuario WHERE nombre=%s", (form_data.username,))
    user = cursor.fetchone()
    conn.close()

    if not user or not bcrypt.checkpw(form_data.password.encode(), user["contrasenha"].encode()):
        raise HTTPException(status_code=401, detail="Credenciales inválidas")

    payload = {
        "sub": user["idusuario"],
        "role": user["rol_idrol"],
        "exp": datetime.datetime.utcnow() + datetime.timedelta(hours=1)
    }
    token = jwt.encode(payload, SECRET_KEY, algorithm="HS256")

    return {"access_token": token, "token_type": "bearer"}

@app.get("/verify")
def verify_token(request: Request):
    auth_header = request.headers.get("authorization")
    if not auth_header or not auth_header.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Token faltante")

    token = auth_header.split(" ")[1]
    try:
        decoded = jwt.decode(token, SECRET_KEY, algorithms=["HS256"])
        return decoded
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Token expirado")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="Token inválido")
