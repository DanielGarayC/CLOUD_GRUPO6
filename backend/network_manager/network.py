from sqlalchemy.orm import Session
from fastapi import HTTPException

# --- Listar VLANs ---
def listar_vlans(db: Session):
    result = db.execute("SELECT * FROM vlan").fetchall()
    return [dict(zip(r.keys(), r)) for r in result]

# --- Asignar VLAN libre ---
def obtener_vlan_internet(db: Session):
    vlan = db.execute("""
        SELECT idvlan, numero FROM vlan
        WHERE estado='reservada'
        ORDER BY idvlan LIMIT 1
    """).fetchone()

    if not vlan:
        raise HTTPException(status_code=404, detail="No hay VLAN reservada para Internet")

    return {
        "vlan_id": vlan.idvlan,
        "numero": vlan.numero,
        "mensaje": f"VLAN {vlan.numero} corresponde a la red de Internet"
    }


# --- Liberar VLAN ---
def liberar_vlan(vlan_id: int, db: Session):
    result = db.execute("""
        UPDATE vlan
        SET estado='disponible'
        WHERE idvlan=:idvlan
    """, {"idvlan": vlan_id})
    db.commit()

    if result.rowcount == 0:
        raise HTTPException(status_code=404, detail="VLAN no encontrada")

    return {"mensaje": f"VLAN {vlan_id} liberada correctamente"}