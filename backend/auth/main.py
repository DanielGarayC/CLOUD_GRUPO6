from fastapi import FastAPI, HTTPException, Depends, Request, Response
from fastapi.security import OAuth2PasswordRequestForm
import mysql.connector, bcrypt, jwt, datetime, os

app = FastAPI()

SECRET_KEY = os.getenv("SECRET_KEY", "supersecreto")

def get_db():
    return mysql.connector.connect(
        host=os.getenv("DB_HOST", "slice_db"),  
        user=os.getenv("DB_USER", "root"),      
        password=os.getenv("DB_PASSWORD", "root"),
        database=os.getenv("DB_NAME", "slice_db")  
    )

@app.post("/login")
def login(form_data: OAuth2PasswordRequestForm = Depends()):
    conn = get_db()
    cursor = conn.cursor(dictionary=True)
    cursor.execute("SELECT * FROM usuario WHERE nombre=%s", (form_data.username,))
    user = cursor.fetchone()
    conn.close()

    if not user or not bcrypt.checkpw(form_data.password.encode(), user["contrasenia"].encode()):
        raise HTTPException(status_code=401, detail="Credenciales inválidas")

    payload = {
        "sub": user["idusuario"],
        "role": user["rol_idrol"],
        "exp": datetime.datetime.utcnow() + datetime.timedelta(hours=1)
    }
    token = jwt.encode(payload, SECRET_KEY, algorithm="HS256")

    return {"access_token": token, "token_type": "bearer"}

@app.get('/verify')
def verify_and_authorize_token(request: Request):
    auth_header = request.headers.get('Authorization')
    original_uri = request.headers.get('X-Original-URI')

    if not auth_header:
        raise HTTPException(status_code=401, detail="Missing token")

    try:
        token = auth_header.split(" ")[1]
        decoded_token = jwt.decode(token, SECRET_KEY, algorithms=["HS256"])
        user_role = decoded_token.get('role')
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Token has expired")
    except (jwt.InvalidTokenError, IndexError):
        raise HTTPException(status_code=401, detail="Invalid token")

    # Reglas de autorización
    if original_uri and original_uri.startswith('/api/sliceManager/') and user_role not in [1, 2]:
        raise HTTPException(status_code=403, detail="Forbidden: Insufficient permissions")

    if original_uri and original_uri.startswith('/api/test/') and user_role not in [1, 2]:
        raise HTTPException(status_code=403, detail="No autorizado: solo Admins")

    return {
        "sub": decoded_token.get("sub"),
        "role": decoded_token.get("role"),
        "exp": decoded_token.get("exp"),
        "authorized": True
    }
