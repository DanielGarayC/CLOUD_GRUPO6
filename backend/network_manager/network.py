from sqlalchemy.orm import Session
from sqlalchemy import text
from fastapi import HTTPException

# --- Listar VLANs ---
def listar_vlans(db: Session):
    result = db.execute(text("SELECT * FROM vlan")).fetchall()
    return [dict(zip(r.keys(), r)) for r in result]

# --- Asignar VLAN reservada para Internet ---
def obtener_vlan_internet(db: Session):
    vlan = db.execute(text("""
        SELECT idvlan, numero FROM vlan
        WHERE estado='reservada'
        ORDER BY idvlan LIMIT 1
    """)).fetchone()

    if not vlan:
        raise HTTPException(status_code=404, detail="No hay VLAN reservada para Internet")

    return {"idvlan": vlan.idvlan, "numero": vlan.numero}

# --- Asignar VLAN disponible ---
def asignar_vlan(db: Session):
    vlan = db.execute(text("""
        SELECT idvlan, numero FROM vlan
        WHERE estado='disponible'
        ORDER BY idvlan LIMIT 1
    """)).fetchone()

    if not vlan:
        raise HTTPException(status_code=400, detail="No hay VLANs disponibles")

    db.execute(text("""
        UPDATE vlan
        SET estado='ocupada'
        WHERE idvlan=:idvlan
    """), {"idvlan": vlan.idvlan})
    db.commit()

    return {"idvlan": vlan.idvlan, "numero": vlan.numero}

# --- Liberar VLAN ---
def liberar_vlan(numero: str, db: Session):
    """Libera una VLAN usando su número."""
    result = db.execute(text("""
        UPDATE vlan
        SET estado='disponible'
        WHERE numero=:numero
    """), {"numero": numero})
    db.commit()

    if result.rowcount == 0:
        raise HTTPException(status_code=404, detail=f"No existe la VLAN {numero}")

    return {"mensaje": f"VLAN {numero} liberada correctamente"}

# --- Listar VNCs ---
def listar_vncs(db: Session):
    result = db.execute(text("SELECT * FROM vnc")).fetchall()
    return [dict(zip(r.keys(), r)) for r in result]

# --- Asignar VNC libre ---
def asignar_vnc(db: Session):
    vnc = db.execute(text("""
        SELECT idvnc, puerto FROM vnc
        WHERE estado='disponible'
        ORDER BY idvnc LIMIT 1
    """)).fetchone()

    if not vnc:
        raise HTTPException(status_code=400, detail="No hay VNCs disponibles")

    db.execute(text("""
        UPDATE vnc
        SET estado='ocupado'
        WHERE idvnc=:idvnc
    """), {"idvnc": vnc.idvnc})
    db.commit()

    return {"idvnc": vnc.idvnc, "puerto": vnc.puerto}

# --- Liberar VNC ---
def liberar_vnc(puerto: str, db: Session):
    """Libera un puerto VNC usando su número de puerto."""
    result = db.execute(text("""
        UPDATE vnc
        SET estado='disponible'
        WHERE puerto=:puerto
    """), {"puerto": puerto})
    db.commit()

    if result.rowcount == 0:
        raise HTTPException(status_code=404, detail=f"No existe el puerto VNC {puerto}")

    return {"mensaje": f"VNC {puerto} liberado correctamente"}
# ============================
#   CREAR NUEVA VLAN / VNC
# ============================

def crear_vlan(numero: str, estado: str, db: Session):
    """Crea una nueva VLAN en la tabla vlan."""
    existe = db.execute(
        text("SELECT * FROM vlan WHERE numero = :numero"),
        {"numero": numero}
    ).fetchone()

    if existe:
        raise HTTPException(status_code=400, detail=f"La VLAN {numero} ya existe")

    db.execute(text("""
        INSERT INTO vlan (numero, estado)
        VALUES (:numero, :estado)
    """), {"numero": numero, "estado": estado})
    db.commit()

    return {"mensaje": f"VLAN {numero} creada correctamente", "estado": estado}


def crear_vnc(puerto: str, estado: str, db: Session):
    """Crea un nuevo puerto VNC en la tabla vnc."""
    existe = db.execute(
        text("SELECT * FROM vnc WHERE puerto = :puerto"),
        {"puerto": puerto}
    ).fetchone()

    if existe:
        raise HTTPException(status_code=400, detail=f"El puerto VNC {puerto} ya existe")

    db.execute(text("""
        INSERT INTO vnc (puerto, estado)
        VALUES (:puerto, :estado)
    """), {"puerto": puerto, "estado": estado})
    db.commit()

    return {"mensaje": f"VNC {puerto} creado correctamente", "estado": estado}
