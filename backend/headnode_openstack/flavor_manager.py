#!/usr/bin/env python3
import sys
import json
import requests
from openstack_sf import get_admin_token
import os
from dotenv import load_dotenv

load_dotenv()

ACCESS_NODE_IP = os.getenv("ACCESS_NODE_IP")
NOVA_PORT = os.getenv("NOVA_PORT")

NOVA_ENDPOINT = f'http://{ACCESS_NODE_IP}:{NOVA_PORT}/v2.1'

def list_flavors(token):
    """
    Lista todos los flavors disponibles en OpenStack
    """
    url = f"{NOVA_ENDPOINT}/flavors/detail"
    headers = {
        'Content-type': 'application/json',
        'X-Auth-Token': token
    }
    
    r = requests.get(url=url, headers=headers)
    if r.status_code == 200:
        return r.json().get('flavors', [])
    return []

def find_flavor_by_specs(token, cpus, ram_mb, disk_gb):
    """
    Busca un flavor existente que coincida con las especificaciones
    
    Args:
        cpus: Número de vCPUs
        ram_mb: RAM en MB
        disk_gb: Disco en GB
    
    Returns:
        flavor_id si existe, None si no
    """
    flavors = list_flavors(token)
    
    for flavor in flavors:
        if (flavor.get('vcpus') == cpus and 
            flavor.get('ram') == ram_mb and 
            flavor.get('disk') == disk_gb):
            print(f"✅ Flavor existente encontrado: {flavor['name']} (ID: {flavor['id']})")
            return flavor['id']
    
    return None

def create_flavor(token, name, cpus, ram_mb, disk_gb):
    """
    Crea un nuevo flavor en OpenStack
    
    Args:
        name: Nombre del flavor (ej: "custom_2cpu_4ram_20disk")
        cpus: Número de vCPUs
        ram_mb: RAM en MB
        disk_gb: Disco en GB
    
    Returns:
        flavor_id si se creó exitosamente, None si falló
    """
    url = f"{NOVA_ENDPOINT}/flavors"
    headers = {
        'Content-type': 'application/json',
        'X-Auth-Token': token
    }
    
    data = {
        "flavor": {
            "name": name,
            "ram": ram_mb,
            "vcpus": cpus,
            "disk": disk_gb,
            "OS-FLV-EXT-DATA:ephemeral": 0,
            #"swap": "",
            "rxtx_factor": 1.0,
            "os-flavor-access:is_public": True
        }
    }
    
    r = requests.post(url=url, headers=headers, data=json.dumps(data))
    
    if r.status_code == 200:
        flavor = r.json().get('flavor', {})
        flavor_id = flavor.get('id')
        print(f"✅ Flavor creado: {name} (ID: {flavor_id})")
        return flavor_id
    else:
        print(f"❌ Error creando flavor: HTTP {r.status_code}")
        print(f"   Respuesta: {r.text}")
        return None

def get_or_create_flavor(token, flavor_spec):
    """
    Obtiene un flavor existente o lo crea si no existe
    
    Args:
        flavor_spec: dict con {
            "cpus": int,
            "ram_gb": float,
            "disk_gb": float,
            "nombre": str (opcional)
        }
    
    Returns:
        dict: {"flavor_id": str, "created": bool, "name": str}
    """
    cpus = flavor_spec.get("cpus")
    ram_gb = flavor_spec.get("ram_gb")
    disk_gb = flavor_spec.get("disk_gb")
    nombre = flavor_spec.get("nombre")
    
    # Convertir RAM a MB (OpenStack usa MB)
    ram_mb = int(ram_gb * 1024)
    disk_gb_int = int(disk_gb)
    
    # Nombre del flavor si no se proporciona
    if not nombre:
        nombre = f"custom_{cpus}cpu_{int(ram_gb)}ram_{disk_gb_int}disk"
    
    print(f"🔍 Buscando flavor: {cpus} vCPUs, {ram_mb} MB RAM, {disk_gb_int} GB disco...")
    
    # Buscar flavor existente
    existing_flavor_id = find_flavor_by_specs(token, cpus, ram_mb, disk_gb_int)
    
    if existing_flavor_id:
        return {
            "flavor_id": existing_flavor_id,
            "created": False,
            "name": nombre
        }
    
    # Crear nuevo flavor
    print(f"🔧 Creando nuevo flavor: {nombre}...")
    new_flavor_id = create_flavor(token, nombre, cpus, ram_mb, disk_gb_int)
    
    if new_flavor_id:
        return {
            "flavor_id": new_flavor_id,
            "created": True,
            "name": nombre
        }
    else:
        return {
            "error": "No se pudo crear el flavor",
            "specs": flavor_spec
        }

def batch_get_or_create_flavors(flavors_specs):
    """
    Procesa múltiples especificaciones de flavors
    
    Args:
        flavors_specs: Lista de dicts con especificaciones de flavors
    
    Returns:
        Lista de resultados para cada flavor
    """
    token = get_admin_token()
    if not token:
        return {"error": "No se pudo obtener token de admin"}
    
    results = []
    
    for spec in flavors_specs:
        result = get_or_create_flavor(token, spec)
        results.append(result)
    
    return results

if __name__ == "__main__":
    """
    Uso:
    
    1. Obtener/crear un solo flavor:
       python3 flavor_manager.py '{"cpus": 2, "ram_gb": 4, "disk_gb": 20}'
    
    2. Procesar múltiples flavors:
       python3 flavor_manager.py '[
         {"cpus": 1, "ram_gb": 1, "disk_gb": 10},
         {"cpus": 2, "ram_gb": 4, "disk_gb": 20}
       ]'
    """
    
    if len(sys.argv) < 2:
        print("❌ Uso: python3 flavor_manager.py '<json_spec>'")
        print("   Ejemplo: python3 flavor_manager.py '{\"cpus\": 2, \"ram_gb\": 4, \"disk_gb\": 20}'")
        sys.exit(1)
    
    try:
        args_json = sys.argv[1]
        args = json.loads(args_json)
        
        token = get_admin_token()
        if not token:
            print(json.dumps({"error": "No se pudo obtener token de admin"}))
            sys.exit(1)
        
        # Detectar si es un solo flavor o una lista
        if isinstance(args, list):
            # Múltiples flavors
            results = batch_get_or_create_flavors(args)
            print(json.dumps({"flavors": results}, indent=2))
        else:
            # Un solo flavor
            result = get_or_create_flavor(token, args)
            print(json.dumps(result, indent=2))
        
    except json.JSONDecodeError as e:
        error_result = {"error": f"JSON inválido: {str(e)}"}
        print(json.dumps(error_result))
        sys.exit(1)
    except Exception as e:
        error_result = {"error": f"Excepción: {str(e)}"}
        print(json.dumps(error_result))
        sys.exit(1)
