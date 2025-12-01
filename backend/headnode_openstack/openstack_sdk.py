import json, requests

# ================================== KEYSTONE ==================================
# source: https://docs.openstack.org/api-ref/identity/v3/

def password_authentication_with_scoped_authorization(auth_endpoint, user_id, password, domain_id, project_id):
    url = auth_endpoint + '/auth/tokens'
    data = \
        {
            "auth": {
                "identity": {
                    "methods": [
                        "password"
                    ],
                    "password": {
                        "user": {
                            "id": user_id,
                            "domain": {
                                "id": domain_id
                            },
                            "password": password
                        }
                    }
                },
                "scope": {
                    "project": {
                        "domain": {
                            "id": domain_id
                        },
                        "id": project_id
                    }
                }
            }
        }
        
    r = requests.post(url=url, data=json.dumps(data))
    # status_code success = 201
    return r

def token_authentication_with_scoped_authorization(auth_endpoint, token, domain_id, project_id):
    url = auth_endpoint + '/auth/tokens'

    data = \
        {
            "auth": {
                "identity": {
                    "methods": [
                        "token"
                    ],
                    "token": {
                        "id": token
                    }
                },
                "scope": {
                    "project": {
                        "domain": {
                            "id": domain_id
                        },
                        "id": project_id
                    }
                }
            }
        }

    r = requests.post(url=url, data=json.dumps(data))
    # status_code success = 201
    return r

def create_project(auth_endpoint, token, domain_id, project_name, project_description):

    url = auth_endpoint + '/projects'
    headers = {'Content-type': 'application/json', 'X-Auth-Token': token}

    data = \
        {
            "project": {
                "id": '4edfadf0bcd54734b7fca0fb0e19f35g',
                "name": project_name,
                "description": project_description,
                "domain_id": domain_id
            }
        }

    r = requests.post(url=url, headers=headers, data=json.dumps(data))
    # status_code success = 201
    return r

def assign_role_to_user_on_project(auth_endpoint, token, project_id, user_id, role_id):
    url = auth_endpoint + '/projects/' + project_id + '/users/' + user_id + '/roles/' + role_id
    headers = {'Content-type': 'application/json', 'X-Auth-Token': token}

    r = requests.put(url=url, headers=headers)
    # status_code success = 204
    return r

# ================================== NOVA ==================================
# source: https://docs.openstack.org/api-ref/compute/

def create_server(nova_endpoint, token, name, flavor_id, image_id, networks=None, availability_zone=None):
    url = nova_endpoint + '/servers'
    headers = {
        'Content-type': 'application/json',
        'X-Auth-Token': token,
    }

    server_payload = {
        'name': name,
        'flavorRef': flavor_id,
        'imageRef': image_id,
        'networks': networks,
    }
    if availability_zone:
        server_payload['availability_zone'] = availability_zone

    data = {'server': server_payload}    
    
    r = requests.post(url=url, headers=headers, data=json.dumps(data))
    # status_code success = 202
    return r

def get_server_console(nova_endpoint, token, server_id, compute_api_version):
    url = nova_endpoint + '/servers/' + server_id + '/remote-consoles'
    headers = {
        'Content-type': 'application/json',
        'X-Auth-Token': token,
        "OpenStack-API-Version": "compute " + compute_api_version
    }
    
    data = \
        {
            "remote_console": {
                "protocol": "vnc",
                "type": "novnc"
                }
        }
    
    r = requests.post(url=url, headers=headers, data=json.dumps(data))
    # status_code success = 200
    return r

# ================================== NEUTRON ==================================
# source: https://docs.openstack.org/api-ref/network/v2/index.html

def create_network(auth_endpoint, token, name):
    url = auth_endpoint + '/networks'
    data = \
        {
            "network": {
                "name": name,
                "port_security_enabled": "false",
            }
        }
        
    headers = {'Content-type': 'application/json', 'X-Auth-Token': token}
    r = requests.post(url=url, headers=headers, data=json.dumps(data))
    # status_code success = 201
    return r

def create_subnet(auth_endpoint, token, network_id, name, ip_version, cidr):
    url = auth_endpoint + '/subnets'
    data = \
        {
            "subnet": {
                "network_id": network_id,
                "name": name,
                "enable_dhcp": False,
                "gateway_ip": None,
                "ip_version": ip_version,
                "cidr": cidr
            }
        }

    data = data=json.dumps(data)

    headers = {'Content-type': 'application/json', 'X-Auth-Token': token}
    r = requests.post(url=url, headers=headers, data=data)
    # status_code success = 201
    return r

def create_port(auth_endpoint, token, name, network_id, project_id):
    url = auth_endpoint + '/ports'
    headers = {'Content-type': 'application/json', 'X-Auth-Token': token}

    data = \
        {
            'port': {
                'name': name,
                'tenant_id': project_id,
                'network_id': network_id,
                'port_security_enabled': 'false'
            }
        }

    r = requests.post(url=url, headers=headers, data=json.dumps(data))
    # status_code success = 201
    return r


# ================================== NEUTRON - ROUTER FUNCTIONS ==================================

def create_router(neutron_endpoint, token, name, external_network_id=None):
    """Crea un router virtual"""
    url = neutron_endpoint + '/routers'
    headers = {
        'Content-type': 'application/json',
        'X-Auth-Token': token
    }
    
    data = {
        "router": {
            "name": name,
            "admin_state_up": True
        }
    }
    
    if external_network_id:
        data["router"]["external_gateway_info"] = {
            "network_id": external_network_id,
            "enable_snat": True
        }
    
    r = requests.post(url=url, headers=headers, data=json.dumps(data))
    return r

def add_router_interface(neutron_endpoint, token, router_id, subnet_id):
    """Conecta un router a una subnet"""
    url = neutron_endpoint + '/routers/' + router_id + '/add_router_interface'
    headers = {
        'Content-type': 'application/json',
        'X-Auth-Token': token
    }
    
    data = {"subnet_id": subnet_id}
    
    r = requests.put(url=url, headers=headers, data=json.dumps(data))
    return r

def set_router_gateway(neutron_endpoint, token, router_id, external_network_id):
    """Configura el gateway externo de un router"""
    url = neutron_endpoint + '/routers/' + router_id
    headers = {
        'Content-type': 'application/json',
        'X-Auth-Token': token
    }
    
    data = {
        "router": {
            "external_gateway_info": {
                "network_id": external_network_id,
                "enable_snat": True
            }
        }
    }
    
    r = requests.put(url=url, headers=headers, data=json.dumps(data))
    return r

def remove_router_interface(neutron_endpoint, token, router_id, subnet_id):
    """Desconecta un router de una subnet"""
    url = neutron_endpoint + '/routers/' + router_id + '/remove_router_interface'
    headers = {
        'Content-type': 'application/json',
        'X-Auth-Token': token
    }
    
    data = {"subnet_id": subnet_id}
    
    r = requests.put(url=url, headers=headers, data=json.dumps(data))
    return r

def create_port_custom(auth_endpoint, token, name, network_id, project_id, mac_address=None, fixed_ips=None):
    """
    Crea un puerto con opciones avanzadas (MAC, Fixed IPs) para la red externa.
    """
    url = auth_endpoint + '/ports'
    headers = {'Content-type': 'application/json', 'X-Auth-Token': token}

    port_data = {
        'name': name,
        'network_id': network_id,
        'tenant_id': project_id,
        'admin_state_up': True,
        'port_security_enabled': False  # Deshabilitado para evitar bloqueos por ahora
    }

    if mac_address:
        port_data['mac_address'] = mac_address
    
    if fixed_ips:
        # fixed_ips debe ser una lista de dicts: [{"ip_address": "10.60.12.105"}]
        port_data['fixed_ips'] = fixed_ips

    data = {'port': port_data}

    r = requests.post(url=url, headers=headers, data=json.dumps(data))
    return r
