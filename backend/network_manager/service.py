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

@app.put("/vlans/liberar/{vlan_id}")
def liberar_vlan(vlan_id: int, db: Session = Depends(get_db)):
    return svc.liberar_vlan(vlan_id, db)

# --- ENDPOINTS DE VNCs ---
@app.get("/vncs")
def listar_vncs(db: Session = Depends(get_db)):
    return svc.listar_vncs(db)

@app.post("/vncs/asignar")
def asignar_vnc(db: Session = Depends(get_db)):
    return svc.asignar_vnc(db)

@app.put("/vncs/liberar/{vnc_id}")
def liberar_vnc(vnc_id: int, db: Session = Depends(get_db)):
    return svc.liberar_vnc(vnc_id, db)