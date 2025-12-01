from openstack_sdk import password_authentication_with_scoped_authorization, token_authentication_with_scoped_authorization, create_server, get_server_console, create_project, assign_role_to_user_on_project, create_network, create_subnet, create_port, create_router, add_router_interface, set_router_gateway, remove_router_interface
from dotenv import load_dotenv
from openstack_sdk import create_port_custom
import os

load_dotenv()
ACCESS_NODE_IP = os.getenv("ACCESS_NODE_IP")
KEYSTONE_PORT = os.getenv("KEYSTONE_PORT")
NOVA_PORT = os.getenv("NOVA_PORT")
NEUTRON_PORT = os.getenv("NEUTRON_PORT")
DOMAIN_ID = os.getenv("DOMAIN_ID")
ADMIN_PROJECT_ID = os.getenv("ADMIN_PROJECT_ID")
ADMIN_USER_ID = os.getenv("ADMIN_USER_ID")
ADMIN_USER_PASSWORD = os.getenv("ADMIN_USER_PASSWORD")
COMPUTE_API_VERSION = os.getenv("COMPUTE_API_VERSION")
ADMIN_ROLE_ID = os.getenv("ADMIN_ROLE_ID")
EXTERNAL_NETWORK_NAME = os.getenv("EXTERNAL_NETWORK_NAME", "external")
EXTERNAL_NETWORK_ID = os.getenv("EXTERNAL_NETWORK_ID", None)

KEYSTONE_ENDPOINT = 'http://' + ACCESS_NODE_IP + ':' + KEYSTONE_PORT + '/v3'
NOVA_ENDPOINT = 'http://' + ACCESS_NODE_IP + ':' + NOVA_PORT + '/v2.1'
NEUTRON_ENDPOINT = 'http://' + ACCESS_NODE_IP + ':' + NEUTRON_PORT + '/v2.0'

def get_admin_token():
    """
    INPUT:

    OUTPUT:
        admin_project_token = token with scope authorization over the admin project (clod_admin) | '' if something wrong
    
    """
    resp1 = password_authentication_with_scoped_authorization(KEYSTONE_ENDPOINT, ADMIN_USER_ID, ADMIN_USER_PASSWORD, DOMAIN_ID, ADMIN_PROJECT_ID)
    admin_project_token = ''
    if resp1.status_code == 201:
        admin_project_token = resp1.headers['X-Subject-Token']
    
    return admin_project_token

def get_token_for_project(project_id, admin_project_token):
    """
    INPUT:
        project_id = project identifier you need scoped authorization over
        admin_project_token = token with scope authorization over the admin project (cloud_admin)
    
    OUTPUT:
        token_for_project = token with scope authorization over the project identified by project_id | '' if something wrong
    
    """
    r = token_authentication_with_scoped_authorization(KEYSTONE_ENDPOINT, admin_project_token, DOMAIN_ID, project_id)
    token_for_project = ''
    if r.status_code == 201:
        token_for_project = r.headers['X-Subject-Token']
    
    return token_for_project

def create_os_instance(image_id, flavor_id, name, port_list, token_for_project, target_host=None):
    """
    INPUT:
        image_id = (string) identifier of image that instance will use
        flavor_id = (string) identifier of flavor that instance will use
        name = (string) name of the instance you will create
        port_list = (string list) list of port id that will be attached to instance
        token_for_project = token with scope authorization over the project identified by project_id
    
    OUTPUT:
        instance_info = dictionary with information about vm just created | {} if something wrong
    
    """
    ports = [ { "port" : port } for port in port_list ]
    az_string = None
    if target_host:
        # Asumimos que la zona por defecto es "nova"
        az_string = f"nova:{target_host}"	
    r = create_server(NOVA_ENDPOINT, token_for_project, name, flavor_id, image_id, ports, availability_zone=az_string)
    instance_info = {}
    if r.status_code == 202:
        instance_info = r.json()
    else:
        print(f"❌ Error creando instancia: {r.status_code} - {r.text}")

    return instance_info

def get_console_url(instance_id, admin_project_token):
    """
    INPUT:
        instance_id = identifier of instance whose console url you need
        admin_project_token = toker with scoped authorization over admin project (cloud_admin)
    
    OUTPUT:
        console_url =  console url of the intance identified by instance_id | '' if something wrong
    
    """
    r = get_server_console(NOVA_ENDPOINT, admin_project_token, instance_id, COMPUTE_API_VERSION)
    print(f"[DEBUG] get_console_url - Status: {r.status_code}")
    print(f"[DEBUG] Response: {r.text[:200]}")
    console_url = ''
    if r.status_code == 200:
        console_url = r.json()['remote_console']['url']
    return console_url

def create_os_project(admin_project_token, slice_name, slice_description = ''):
    """
    Crea un proyecto o retorna el ID si ya existe
    """
    r = create_project(KEYSTONE_ENDPOINT, admin_project_token, DOMAIN_ID, slice_name, slice_description)

    slice_id = ''
    if r.status_code == 201:
        # Proyecto creado exitosamente
        slice_id = r.json()['project']['id']
        print(f"✅ Proyecto {slice_name} creado: {slice_id}")
    elif r.status_code == 409:
        # Proyecto ya existe (conflict)
        print(f"ℹ️ Proyecto {slice_name} ya existe, buscando ID...")
        # Buscar el proyecto existente
        slice_id = get_project_id_by_name(admin_project_token, slice_name)
        if slice_id:
            print(f"✅ Proyecto encontrado: {slice_id}")
    
    return slice_id

def get_project_id_by_name(admin_project_token, project_name):
    """
    Busca un proyecto por nombre y retorna su ID
    """
    import requests
    url = f"{KEYSTONE_ENDPOINT}/projects?name={project_name}"
    headers = {
        'Content-type': 'application/json',
        'X-Auth-Token': admin_project_token
    }
    
    r = requests.get(url=url, headers=headers)
    if r.status_code == 200:
        projects = r.json().get('projects', [])
        if projects:
            return projects[0]['id']
    
    return None

def assign_admin_role_over_os_project(admin_project_token, target_project_id):
    r = assign_role_to_user_on_project(KEYSTONE_ENDPOINT, admin_project_token, target_project_id, ADMIN_USER_ID, ADMIN_ROLE_ID)
    operation_status = 0
    if r.status_code == 204:
        operation_status = 1
    
    return operation_status

def create_os_network(target_project_token, network_name):
    r = create_network(NEUTRON_ENDPOINT, target_project_token, network_name)
    
    network_id = ''
    if r.status_code == 201:
        network_id = r.json()['network']['id']
    
    return network_id

# 🟢 FUNCIÓN CORREGIDA - Ahora acepta CIDR como parámetro
def create_os_subnet(target_project_token, subnet_name, network_id, cidr="10.0.39.96/28"):
    """
    Crea una subnet en OpenStack
    
    Args:
        target_project_token: Token del proyecto
        subnet_name: Nombre de la subnet
        network_id: ID de la red asociada
        cidr: Rango CIDR (ej: "10.0.100.0/24") - AHORA ES PARAMETRIZABLE
    
    Returns:
        subnet_id: ID de la subnet creada o '' si falla
    """
    ip_version = '4'

    r = create_subnet(NEUTRON_ENDPOINT, target_project_token, network_id, subnet_name, ip_version, cidr)
    
    subnet_id = ''
    if r.status_code == 201:
        subnet_id = r.json()['subnet']['id']
        print(f"✅ Subnet {subnet_name} creada con CIDR {cidr}")
    else:
        print(f"❌ Error creando subnet: HTTP {r.status_code}")
        print(f"   Respuesta: {r.text}")
    
    return subnet_id    

def create_os_port(target_project_token, port_name, network_id, target_project_id):
    r = create_port(NEUTRON_ENDPOINT, target_project_token, port_name, network_id, target_project_id)
    
    port_id = ''
    if r.status_code == 201:
        port_id = r.json()['port']['id']
    
    return port_id

# ================================== FUNCIONES PARA INTERNET ==================================

def get_external_network_id(admin_token):
    """Busca la red externa disponible en OpenStack"""
    import requests
    
    if EXTERNAL_NETWORK_ID:
        print(f"✅ Usando red externa del .env: {EXTERNAL_NETWORK_ID}")
        return EXTERNAL_NETWORK_ID
    
    url = f"{NEUTRON_ENDPOINT}/networks?router:external=true"
    headers = {
        'Content-type': 'application/json',
        'X-Auth-Token': admin_token
    }
    
    r = requests.get(url=url, headers=headers)
    if r.status_code == 200:
        networks = r.json().get('networks', [])
        if networks:
            external_net = networks[0]
            print(f"✅ Red externa encontrada: {external_net['name']} ({external_net['id']})")
            return external_net['id']
    
    print("❌ No se encontró ninguna red externa en OpenStack")
    return None

def create_os_router(project_token, router_name, external_network_id=None):
    """Crea un router virtual en el proyecto"""
    r = create_router(NEUTRON_ENDPOINT, project_token, router_name, external_network_id)
    
    router_id = ''
    if r.status_code == 201:
        router_id = r.json()['router']['id']
        print(f"✅ Router {router_name} creado: {router_id}")
    else:
        print(f"❌ Error creando router: HTTP {r.status_code}")
        print(f"   Respuesta: {r.text}")
    
    return router_id

def connect_router_to_subnet(project_token, router_id, subnet_id):
    """Conecta un router a una subnet"""
    
    # PRIMERO: Verificar si ya está conectada
    if check_router_interface_exists(project_token, router_id, subnet_id):
        print(f"ℹ️ Subnet {subnet_id[:8]}... ya está conectada al router")
        return True
    
    r = add_router_interface(NEUTRON_ENDPOINT, project_token, router_id, subnet_id)

    if r.status_code == 200:
        print(f"✅ Router conectado a subnet {subnet_id[:8]}...")
        return True
    elif r.status_code == 400:
        # Parsear el error para saber si ya está conectada
        try:
            error_msg = r.json().get('NeutronError', {}).get('message', '')
            if 'already' in error_msg.lower() or 'exists' in error_msg.lower():
                print(f"ℹ️ Subnet {subnet_id[:8]}... ya estaba conectada (detectado en error)")
                return True
        except:
            pass
        
        print(f"❌ Error 400 conectando router: {r.text}")
        return False
    else:
        print(f"❌ Error HTTP {r.status_code} conectando router: {r.text}")
        return False

def set_router_external_gateway(admin_token, router_id, external_network_id):
    """Configura el gateway externo del router"""
    r = set_router_gateway(NEUTRON_ENDPOINT, admin_token, router_id, external_network_id)
    
    if r.status_code == 200:
        print(f"✅ Gateway externo configurado")
        return True
    else:
        print(f"❌ Error configurando gateway: HTTP {r.status_code}")
        return False

def get_or_create_router_for_project(admin_token, project_token, project_id, slice_id):
    """Obtiene o crea un router para el proyecto con salida a Internet"""
    import requests
    
    router_name = f"router_slice_{slice_id}"
    
    # Verificar si existe
    url = f"{NEUTRON_ENDPOINT}/routers?project_id={project_id}&name={router_name}"
    headers = {
        'Content-type': 'application/json',
        'X-Auth-Token': project_token
    }
    
    r = requests.get(url=url, headers=headers)
    if r.status_code == 200:
        routers = r.json().get('routers', [])
        # 🔥 CORRECCIÓN: Verificar que la lista no esté vacía y que el primer elemento sea válido
        if routers and routers[0] is not None and isinstance(routers[0], dict):
            router_id = routers[0]['id']
            gateway_info = routers[0].get('external_gateway_info')
            external_net = gateway_info.get('network_id') if gateway_info else None
            print(f"ℹ️ Router {router_name} ya existe: {router_id}")
            return {
                "router_id": router_id,
                "external_network_id": external_net,
                "created": False
            }
        else:
            print(f"⚠️ Router encontrado pero con datos inválidos, recreando...")
    
    # Obtener red externa
    external_network_id = get_external_network_id(admin_token)
    if not external_network_id:
        return None
    
    # Crear router
    router_id = create_os_router(project_token, router_name)
    if not router_id:
        return None
    
    # Configurar gateway
    if not set_router_external_gateway(admin_token, router_id, external_network_id):
        print("⚠️ Router creado pero sin gateway externo")
    
    return {
        "router_id": router_id,
        "external_network_id": external_network_id,
        "created": True
    }

def check_router_interface_exists(token, router_id, subnet_id):
    """Verifica si una subnet ya está conectada a un router"""
    import requests
    
    url = f"{NEUTRON_ENDPOINT}/routers/{router_id}"
    headers = {
        'Content-type': 'application/json',
        'X-Auth-Token': token
    }
    
    try:
        r = requests.get(url=url, headers=headers)
        if r.status_code == 200:
            router_data = r.json().get('router', {})
            
            # Verificar en ports del router
            ports_url = f"{NEUTRON_ENDPOINT}/ports?device_id={router_id}"
            r_ports = requests.get(url=ports_url, headers=headers)
            
            if r_ports.status_code == 200:
                ports = r_ports.json().get('ports', [])
                for port in ports:
                    for fixed_ip in port.get('fixed_ips', []):
                        if fixed_ip.get('subnet_id') == subnet_id:
                            return True
        return False
    except Exception as e:
        print(f"⚠️ Error verificando interfaz del router: {e}")
        return False

def create_os_external_port(admin_token, network_id, project_id, vm_name):
    """
    Crea un puerto en la red externa para la VM.
    """
    port_name = f"port_{vm_name}_external"
    
    # Llamamos a la función custom del SDK
    r = create_port_custom(NEUTRON_ENDPOINT, admin_token, port_name, network_id, project_id)
    
    port_id = ''
    if r.status_code == 201:
        port_id = r.json()['port']['id']
        print(f"✅ Puerto externo creado: {port_id}")
    else:
        print(f"❌ Error creando puerto externo: {r.status_code} - {r.text}")
    
    return port_id
