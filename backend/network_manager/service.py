from fastapi import FastAPI, Depends
from sqlalchemy.orm import Session
from database import get_db
import network as svc

app = FastAPI(
    title="Network & Security Manager",
    version="1.0.0",
    description="Servicio responsable de VLANs, NAT y seguridad de red."
)


@app.get("/")
def root():
    return {"status": "Network Manager activo"}

# --- ENDPOINTS DEL SERVICIO ---
@app.get("/vlans")
def listar_vlans(db: Session = Depends(get_db)):
    return svc.listar_vlans(db)

@app.post("/vlans/asignar")
def asignar_vlan(db: Session = Depends(get_db)):
    return svc.asignar_vlan(db)

@app.get("/vlans/internet")
def obtener_vlan_internet(db: Session = Depends(get_db)):
    return svc.obtener_vlan_internet(db)

@app.put("/vlans/liberar/{numero}")
def liberar_vlan(numero: str, db: Session = Depends(get_db)):
    return svc.liberar_vlan(numero, db)

# --- ENDPOINTS DE VNCs ---
@app.get("/vncs")
def listar_vncs(db: Session = Depends(get_db)):
    return svc.listar_vncs(db)

@app.post("/vncs/asignar")
def asignar_vnc(db: Session = Depends(get_db)):
    return svc.asignar_vnc(db)

@app.put("/vncs/liberar/{puerto}")
def liberar_vnc(puerto: str, db: Session = Depends(get_db)):
    return svc.liberar_vnc(puerto, db)
@app.post("/vlans/crear")
def crear_vlan(payload: dict, db: Session = Depends(get_db)):
    """
    Crea una nueva VLAN.
    Body JSON:
    {
      "numero": "111",
      "estado": "disponible"
    }
    """
    numero = payload.get("numero")
    estado = payload.get("estado", "disponible")
    if not numero:
        raise HTTPException(status_code=400, detail="Debe indicar el número de VLAN")

    return svc.crear_vlan(numero, estado, db)


@app.post("/vncs/crear")
def crear_vnc(payload: dict, db: Session = Depends(get_db)):
    """
    Crea un nuevo puerto VNC.
    Body JSON:
    {
      "puerto": "5921",
      "estado": "disponible"
    }
    """
    puerto = payload.get("puerto")
    estado = payload.get("estado", "disponible")
    if not puerto:
        raise HTTPException(status_code=400, detail="Debe indicar el puerto VNC")

    return svc.crear_vnc(puerto, estado, db)