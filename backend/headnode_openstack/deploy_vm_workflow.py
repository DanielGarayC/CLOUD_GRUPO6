#!/usr/bin/env python3
import sys
import json
import time
import os
import requests

from openstack_sf import (
    get_admin_token,
    get_token_for_project,
    create_os_project,
    assign_admin_role_over_os_project,
    create_os_network,
    create_os_subnet,
    create_os_port,
    create_os_instance,
    get_console_url,
    get_or_create_router_for_project,
    connect_router_to_subnet
)
from flavor_manager import get_or_create_flavor


def verify_ports_attached(instance_id, project_token, expected_port_count):
    """
    Verifica que la instancia tenga todos los puertos esperados
    """
    import requests
    
    ACCESS_NODE_IP = os.getenv("ACCESS_NODE_IP")
    NOVA_PORT = os.getenv("NOVA_PORT")
    NOVA_ENDPOINT = f'http://{ACCESS_NODE_IP}:{NOVA_PORT}/v2.1'
    
    url = f"{NOVA_ENDPOINT}/servers/{instance_id}"
    headers = {
        'Content-type': 'application/json',
        'X-Auth-Token': project_token
    }
    
    try:
        r = requests.get(url=url, headers=headers, timeout=10)
        if r.status_code == 200:
            server = r.json().get('server', {})
            addresses = server.get('addresses', {})
            
            # Contar puertos totales
            total_ports = sum(len(ips) for ips in addresses.values())
            
            print(f"🔍 Puertos detectados: {total_ports}/{expected_port_count}")
            
            if total_ports != expected_port_count:
                return {
                    "valid": False,
                    "error": f"Puertos incorrectos: esperados {expected_port_count}, encontrados {total_ports}",
                    "details": addresses
                }
            
            return {
                "valid": True,
                "ports_count": total_ports,
                "networks": list(addresses.keys())
            }
    except Exception as e:
        return {
            "valid": False,
            "error": f"Error verificando puertos: {str(e)}"
        }
    
    return {"valid": False, "error": "No se pudo verificar"}

def wait_for_instance_active(instance_id, project_token, max_wait=60, check_interval=3):
    """
    Espera a que una instancia esté en estado ACTIVE
    Detecta errores de placement y recursos
    """

    import requests
    import os

    ACCESS_NODE_IP = os.getenv("ACCESS_NODE_IP")
    NOVA_PORT = os.getenv("NOVA_PORT")
    NOVA_ENDPOINT = f'http://{ACCESS_NODE_IP}:{NOVA_PORT}/v2.1'

    url = f"{NOVA_ENDPOINT}/servers/{instance_id}"
    headers = {
        'Content-type': 'application/json',
        'X-Auth-Token': project_token
    }

    start_time = time.time()
    elapsed = 0

    print(f"⏳ Esperando a que instancia {instance_id[:8]}... esté ACTIVE...")

    while elapsed < max_wait:
        try:
            r = requests.get(url=url, headers=headers, timeout=5)

            if r.status_code == 200:
                server_info = r.json().get('server', {})
                status = server_info.get('status', 'UNKNOWN')
                fault = server_info.get('fault', {})

                print(f"   └─ Estado actual: {status} (esperado: {elapsed:.1f}s)")

                if status == 'ACTIVE':
                    print(f"✅ Instancia lista en {elapsed:.1f}s")
                    return {
                        "ready": True,
                        "status": status,
                        "elapsed": elapsed
                    }
                    
                elif status == 'ERROR':
                    # 🔥 DETECTAR TIPO DE ERROR
                    error_message = fault.get('message', 'Unknown error')
                    error_code = fault.get('code', 0)
                    
                    print(f"❌ Instancia en ERROR: {error_message}")
                    
                    # Detectar errores comunes
                    is_no_valid_host = any(phrase in error_message.lower() for phrase in [
                        'no valid host',
                        'no conductor found',
                        'insufficient resources',
                        'not enough hosts'
                    ])
                    
                    return {
                        "ready": False,
                        "status": status,
                        "elapsed": elapsed,
                        "error": error_message,
                        "error_code": error_code,
                        "is_placement_error": is_no_valid_host,
                        "fault": fault
                    }

                time.sleep(check_interval)
                elapsed = time.time() - start_time
            else:
                print(f"⚠️ Error consultando estado: HTTP {r.status_code}")
                time.sleep(check_interval)
                elapsed = time.time() - start_time

        except Exception as e:
            print(f"⚠️ Excepción consultando estado: {e}")
            time.sleep(check_interval)
            elapsed = time.time() - start_time

    print(f"⏱️ Timeout esperando instancia ({max_wait}s)")
    return {
        "ready": False,
        "status": "TIMEOUT",
        "elapsed": elapsed,
        "error": f"Instance not ready after {max_wait}s"
    }

def check_network_exists(project_token, network_name):
    """
    Verifica si una red ya existe en el proyecto
    
    Returns:
        dict con network_id y subnet_id o None si no existe
    """
    import requests
    import os

    ACCESS_NODE_IP = os.getenv("ACCESS_NODE_IP")
    NEUTRON_PORT = os.getenv("NEUTRON_PORT")
    NEUTRON_ENDPOINT = f'http://{ACCESS_NODE_IP}:{NEUTRON_PORT}/v2.0'

    url = f"{NEUTRON_ENDPOINT}/networks?name={network_name}"
    headers = {
        'Content-type': 'application/json',
        'X-Auth-Token': project_token
    }

    r = requests.get(url=url, headers=headers)
    if r.status_code == 200:
        networks = r.json().get('networks', [])
        if networks:
            network_id = networks[0]['id']

            subnet_url = f"{NEUTRON_ENDPOINT}/subnets?network_id={network_id}"
            r2 = requests.get(url=subnet_url, headers=headers)
            if r2.status_code == 200:
                subnets = r2.json().get('subnets', [])
                if subnets:
                    subnet_id = subnets[0]['id']
                    return {
                        "network_id": network_id,
                        "subnet_id": subnet_id
                    }

    return None

def deploy_vm_complete(args):
    """
    Workflow completo de despliegue en OpenStack con soporte para Internet
    
    CORRECCIÓN CLAVE: Ahora SIEMPRE crea las redes locales, incluso con internet
    """
    slice_id = args.get("slice_id")
    vm_name = args.get("vm_name")
    vm_id = args.get("vm_id")
    imagen_id = args.get("imagen_id")
    flavor_spec = args.get("flavor_spec")
    redes = args.get("redes", [])
    salida_internet = args.get("salidainternet", False)
    target_host = args.get("target_host")

    result = {
        "success": False,
        "slice_id": slice_id,
        "vm_name": vm_name,
        "vm_id": vm_id,
        "steps_completed": []
    }

    try:
        # ================================
        # PASO 1: OBTENER TOKEN DE ADMIN
        # ================================
        print("🔑 Obteniendo token de admin...")
        admin_token = get_admin_token()
        if not admin_token:
            result["error"] = "No se pudo obtener token de admin"
            return result

        result["steps_completed"].append("admin_token_obtained")
        print("✅ Token de admin obtenido")

        # ================================
        # PASO 2: CREAR/OBTENER PROYECTO
        # ================================
        project_name = f"slice_{slice_id}"
        print(f"📦 Creando/obteniendo proyecto {project_name}...")
        
        project_id = create_os_project(admin_token, project_name, f"Proyecto para slice {slice_id}")

        if not project_id:
            result["error"] = f"No se pudo crear proyecto {project_name}"
            return result

        result["project_id"] = project_id
        result["steps_completed"].append("project_created")
        print(f"✅ Proyecto: {project_id}")

        # ================================
        # PASO 3: ASIGNAR ROL ADMIN
        # ================================
        print("👤 Asignando rol admin al proyecto...")
        role_status = assign_admin_role_over_os_project(admin_token, project_id)
        if not role_status:
            result["error"] = "No se pudo asignar rol admin"
            return result

        result["steps_completed"].append("admin_role_assigned")
        print("✅ Rol admin asignado")

        # ================================
        # PASO 4: OBTENER TOKEN DEL PROYECTO
        # ================================
        print("🔑 Obteniendo token del proyecto...")
        project_token = get_token_for_project(project_id, admin_token)
        if not project_token:
            result["error"] = "No se pudo obtener token del proyecto"
            return result

        result["steps_completed"].append("project_token_obtained")
        print("✅ Token del proyecto obtenido")

        # ================================
        # PASO 5: OBTENER/CREAR FLAVOR
        # ================================
        print(f"🔧 Gestionando flavor: {flavor_spec.get('nombre', 'custom')}...")
        flavor_result = get_or_create_flavor(admin_token, flavor_spec)

        if "error" in flavor_result:
            result["error"] = f"Error con flavor: {flavor_result['error']}"
            return result

        flavor_id = flavor_result["flavor_id"]
        result["flavor_id"] = flavor_id
        result["flavor_created"] = flavor_result.get("created", False)
        result["steps_completed"].append(f"flavor_{'created' if result['flavor_created'] else 'found'}")
        print(f"✅ Flavor: {flavor_id}")

        # ================================
        # PASO 6: 🔥 CREAR REDES Y PUERTOS PRIMERO
        # ================================
        # 🔑 CORRECCIÓN: Crear redes ANTES de configurar router
        ports = []
        networks_created = []
        networks_cache = {}
        subnets_to_connect = []

        if not redes:
            print("ℹ️ No hay redes definidas, creando red por defecto...")
            network_name = f"net_slice_{slice_id}_default"
            cidr_default = "10.0.1.0/24"

            existing = check_network_exists(project_token, network_name)
            if existing:
                print(f"♻️ Red {network_name} ya existe, reutilizando...")
                network_id = existing["network_id"]
                subnet_id = existing["subnet_id"]
            else:
                print(f"🌐 Creando red {network_name}...")
                network_id = create_os_network(project_token, network_name)
                if not network_id:
                    result["error"] = "No se pudo crear red por defecto"
                    return result

                subnet_name = f"subnet_slice_{slice_id}_default"
                subnet_id = create_os_subnet(project_token, subnet_name, network_id, cidr_default)

                if not subnet_id:
                    result["error"] = "No se pudo crear subnet por defecto"
                    return result

            port_name = f"port_{vm_name}_default"
            port_id = create_os_port(project_token, port_name, network_id, project_id)

            if not port_id:
                result["error"] = "No se pudo crear puerto por defecto"
                return result

            ports.append(port_id)
            networks_created.append({
                "network_id": network_id,
                "subnet_id": subnet_id,
                "cidr": cidr_default,
                "tipo": "default"
            })
            
            subnets_to_connect.append(subnet_id)
            
        else:
            print(f"🌐 Creando {len(redes)} red(es) según topología...")
            
            for red_info in redes:
                network_name = red_info["nombre"]
                cidr = red_info["cidr"]
                enlace_id = red_info["enlace_id"]

                if network_name in networks_cache:
                    print(f"♻️ Reutilizando red existente {network_name}")
                    network_id, subnet_id = networks_cache[network_name]
                else:
                    print(f"🔍 Verificando red {network_name} (CIDR: {cidr})...")

                    existing = check_network_exists(project_token, network_name)

                    if existing:
                        print(f"♻️ Red {network_name} ya existe, reutilizando...")
                        network_id = existing["network_id"]
                        subnet_id = existing["subnet_id"]
                    else:
                        print(f"🌐 Creando red {network_name}...")
                        network_id = create_os_network(project_token, network_name)
                        if not network_id:
                            result["error"] = f"No se pudo crear red {network_name}"
                            return result

                        subnet_name = f"subnet_{enlace_id}"
                        subnet_id = create_os_subnet(project_token, subnet_name, network_id, cidr)

                        if not subnet_id:
                            result["error"] = f"No se pudo crear subnet {subnet_name}"
                            return result

                    networks_cache[network_name] = (network_id, subnet_id)

                port_name = f"port_{vm_name}_link_{enlace_id}"
                port_id = create_os_port(project_token, port_name, network_id, project_id)

                if not port_id:
                    result["error"] = f"No se pudo crear puerto {port_name}"
                    return result

                ports.append(port_id)

                if not any(n["network_id"] == network_id for n in networks_created):
                    networks_created.append({
                        "network_id": network_id,
                        "subnet_id": subnet_id,
                        "cidr": cidr,
                        "enlace_id": enlace_id,
                        "tipo": "enlace"
                    })
                    
                    if subnet_id not in subnets_to_connect:
                        subnets_to_connect.append(subnet_id)

        result["networks"] = networks_created
        result["ports"] = ports
        result["steps_completed"].append(f"networks_created_{len(networks_created)}")
        print(f"✅ {len(networks_created)} red(es) creada(s), {len(ports)} puerto(s) creado(s)")
	
	# ================================
        # PASO 7 y 8: CONECTIVIDAD EXTERNA (MODO DIRECTO VLAN 6)
        # ================================
        # Reemplazamos Routers por conexión directa a la red externa
        
        if salida_internet:
            print("\n🌐 ========== CONFIGURANDO ACCESO DIRECTO A INTERNET ==========")
            
            # 1. Buscar la red externa (ahora se llama external_vlan6 o la que creamos)
            # Buscamos cualquier red que sea router:external=True
            import requests
            ACCESS_NODE_IP = os.getenv("ACCESS_NODE_IP")
            NEUTRON_PORT = os.getenv("NEUTRON_PORT")
            NEUTRON_ENDPOINT = f'http://{ACCESS_NODE_IP}:{NEUTRON_PORT}/v2.0'
            
            url_ext = f"{NEUTRON_ENDPOINT}/networks?router:external=true"
            r_ext = requests.get(url_ext, headers={'X-Auth-Token': admin_token})
            
            external_net_id = None
            if r_ext.status_code == 200:
                nets = r_ext.json().get('networks', [])
                if nets:
                    external_net_id = nets[0]['id']
                    print(f"✅ Red externa encontrada: {nets[0]['name']} ({external_net_id})")
            
            if external_net_id:
                # 2. Crear un puerto directo en esa red para esta VM
                from openstack_sf import create_os_external_port
                ext_port_id = create_os_external_port(admin_token, external_net_id, project_id, vm_name)
                
                if ext_port_id:
                    # AGREGAMOS EL PUERTO A LA LISTA DE PUERTOS DE LA VM
                    ports.append(ext_port_id)
                    result["steps_completed"].append("external_port_attached")
                    print(f"✅ Puerto externo {ext_port_id} agregado a la VM")
                    
                    result["internet_access"] = {
                        "enabled": True,
                        "mode": "direct_attachment",
                        "network_id": external_net_id
                    }
                else:
                    print("⚠️ Falló la creación del puerto externo")
            else:
                print("⚠️ No se encontró ninguna red externa (router:external=True)")
            
            print("========================================================\n")

        # ================================
        # PASO 9: CREAR INSTANCIA
        # ================================
        print(f"\n🖥️ Creando instancia {vm_name}...")
        print(f"   • Imagen: {imagen_id}")
        print(f"   • Flavor: {flavor_id}")
        print(f"   • Puertos: {len(ports)}")
        if target_host:
                print(f"   • Target Host: {target_host} (Forzando placement)")	

        instance_info = create_os_instance(imagen_id, flavor_id, vm_name, ports, project_token, target_host)        

        if not instance_info or "server" not in instance_info:
            result["error"] = "No se pudo crear instancia"
            return result
	
        instance_id = instance_info["server"]["id"]
        result["instance_id"] = instance_id
        result["instance_info"] = instance_info
        result["steps_completed"].append("instance_created")
        print(f"✅ Instancia creada: {instance_id}")

        # ================================
        # PASO 10: ESPERAR A QUE ESTÉ ACTIVA
        # ================================
        wait_result = wait_for_instance_active(instance_id, project_token, max_wait=90, check_interval=3)

        # 🔥 VALIDACIÓN CRÍTICA DE ERRORES
        if not wait_result["ready"]:
            error_msg = wait_result.get('error', 'Unknown error')
        
            # Detectar error de placement
            if wait_result.get("is_placement_error", False):
                result["error"] = f"PLACEMENT_ERROR: {error_msg}"
                result["error_type"] = "NO_VALID_HOST"
                result["should_rollback"] = True
                print(f"🚨 ERROR DE PLACEMENT DETECTADO: {error_msg}")
            else:
                result["error"] = f"INSTANCE_ERROR: {error_msg}"
                result["error_type"] = "DEPLOYMENT_FAILED"
                result["should_rollback"] = True
                print(f"❌ Error desplegando instancia: {error_msg}")
        
            result["instance_status"] = wait_result
            result["instance_id"] = instance_id  # Importante para rollback
            return result

        result["instance_status"] = wait_result
        result["steps_completed"].append("instance_active")

        # ================================
        # PASO 10.5: VALIDAR TOPOLOGÍA
        # ================================
        expected_ports = len(ports)
        print(f"🔍 Validando topología de red ({expected_ports} puertos esperados)...")

        topology_check = verify_ports_attached(instance_id, project_token, expected_ports)

        if not topology_check["valid"]:
            result["error"] = f"TOPOLOGY_ERROR: {topology_check['error']}"
            result["error_type"] = "INVALID_TOPOLOGY"
            result["should_rollback"] = True
            result["topology_validation"] = topology_check	
            print(f"❌ Topología incorrecta: {topology_check['error']}")
            return result

        result["topology_validation"] = topology_check
        result["steps_completed"].append("topology_validated")
        print(f"✅ Topología validada correctamente")

        # ================================
        # PASO 11: OBTENER CONSOLE URL
        # ================================
        if wait_result["ready"]:
            print(f"🖥️ Obteniendo URL de consola...")
            console_url = get_console_url(instance_id, admin_token)

            if console_url:
                result["console_url"] = console_url
                result["steps_completed"].append("console_url_obtained")
                print(f"✅ Console URL obtenida")
            else:
                result["console_url"] = None
                result["warning"] = "No se pudo obtener URL de consola"
                print("⚠️ No se pudo obtener console_url")
        else:
            result["console_url"] = None
            result["warning"] = "Console URL no disponible - instancia no está ACTIVE"
            print("⚠️ Saltando obtención de console URL (instancia no lista)")

        # ================================
        # PASO 12: ÉXITO
        # ================================
        result["success"] = True
        result["message"] = f"VM {vm_name} desplegada exitosamente en OpenStack"
        
        # Información de Internet
        if salida_internet:
            result["internet_access"] = {
                "enabled": True,
                "router_id": router_info.get("router_id") if router_info else None,
                "external_network_id": router_info.get("external_network_id") if router_info else None,
                "subnets_connected": result.get("subnets_connected_to_router", 0)
            }
            print("\n✅ Acceso a Internet configurado:")
            print(f"   • Router: {result['internet_access']['router_id'][:8] if result['internet_access']['router_id'] else 'N/A'}...")
            print(f"   • Red externa: {result['internet_access']['external_network_id'][:8] if result['internet_access']['external_network_id'] else 'N/A'}...")
            print(f"   • Subnets conectadas: {result['internet_access']['subnets_connected']}")

        print(f"\n🎉 Despliegue completado exitosamente")
        print(f"   Pasos completados: {len(result['steps_completed'])}")

    except Exception as e:
        result["error"] = f"Excepción durante despliegue: {str(e)}"
        result["exception"] = str(type(e).__name__)
        import traceback
        result["traceback"] = traceback.format_exc()
        print(f"\n❌ ERROR: {result['error']}")
        print(result["traceback"])

    return result

# ================================
# MAIN - PUNTO DE ENTRADA
# ================================
if __name__ == "__main__":
    """
    Punto de entrada del script
    Acepta JSON por argumento o stdin
    """
    if len(sys.argv) > 1:
        args_json = sys.argv[1]
    else:
        args_json = sys.stdin.read()

    try:
        args = json.loads(args_json)
        result = deploy_vm_complete(args)
        
        # Imprimir resultado como JSON limpio
        print(json.dumps(result))
        
    except json.JSONDecodeError as e:
        error_result = {
            "success": False,
            "error": f"Invalid JSON input: {str(e)}"
        }
        print(json.dumps(error_result))
        sys.exit(1)
        
    except Exception as e:
        error_result = {
            "success": False,
            "error": f"Unhandled exception: {str(e)}"
        }
        print(json.dumps(error_result))
        sys.exit(1)
