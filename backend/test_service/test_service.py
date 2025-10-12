from fastapi import FastAPI

app = FastAPI()

@app.get("/protected")
def protected_route():
    """
    Si puedes acceder a esta ruta, significa que Nginx y el servicio de auth
    validaron tu token JWT correctamente.
    """
    return {"message": "Autorizado, Daniel de mrd TKM, OWOWOW"}
