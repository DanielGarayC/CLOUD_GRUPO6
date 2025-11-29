from flask import Flask, render_template, request, redirect, url_for, session, flash, jsonify
from models import db, User, Slice, Rol, Instancia, Imagen, Vnc, Worker, Enlace, Vlan
import os
import json
from datetime import datetime
import logging
import sys
import requests
from utils.novnc_manager import ensure_tunnel_and_token

AUTH_SERVICE_URL = "http://auth:8080/login"
VERIFY_URL = "http://auth:8080/verify"


app = Flask(__name__)
app.config['SECRET_KEY'] = 'your-secret-key-change-in-production'
app.config['SQLALCHEMY_DATABASE_URI'] = 'mysql+pymysql://root:root@slice_db:3306/mydb'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

logging.basicConfig(stream=sys.stdout, level=logging.INFO)
app.logger.addHandler(logging.StreamHandler(sys.stdout))
app.logger.setLevel(logging.INFO)
# Initialize database
db.init_app(app)

def initialize_database():
    """Create database tables - no sample data creation"""
    with app.app_context():
        db.create_all()
        print("Database tables initialized!")

def is_admin_user(user):
    """Check if user has admin privileges (administrator or superadmin roles)"""
    if not user or not user.rol:
        return False
    return user.rol.nombre_rol in ['administrador', 'superadmin']

def can_access_slice(user, slice_obj):
    """Check if user can access a specific slice based on their role"""
    if not user:
        return False
    
    # Admin users can access all slices
    if is_admin_user(user):
        return True
    
    # Regular users (usuariofinal, investigador) can only access their own slices
    return user in slice_obj.usuarios

def get_user_slices(user):
    """Get slices that user can access based on their role"""
    if not user:
        return []
    
    # Admin users can see all slices
    if is_admin_user(user):
        return Slice.query.all()
    
    # Regular users can only see their own slices
    return user.slices

# Agregar estas funciones antes de las rutas

def save_topology_links(slice_obj, topology_data, node_to_instance_map):
    """
    Guarda los enlaces de la topología en la tabla enlace
    """
    if not topology_data or 'edges' not in topology_data:
        return 0
    
    enlaces_creados = 0
    for edge in topology_data['edges']:
        from_node = edge.get('from')
        to_node = edge.get('to')
        
        if from_node and to_node and from_node in node_to_instance_map and to_node in node_to_instance_map:
            vm1_id = node_to_instance_map[from_node]
            vm2_id = node_to_instance_map[to_node]
            
            # Verificar que no exista ya este enlace
            existing_link = Enlace.query.filter(
                db.and_(
                    Enlace.slice_idslice == slice_obj.idslice,
                    db.or_(
                        db.and_(Enlace.vm1 == str(vm1_id), Enlace.vm2 == str(vm2_id)),
                        db.and_(Enlace.vm1 == str(vm2_id), Enlace.vm2 == str(vm1_id))
                    )
                )
            ).first()
            
            if not existing_link:
                enlace = Enlace(
                    vm1=str(vm1_id),
                    vm2=str(vm2_id),
                    slice_idslice=slice_obj.idslice,
                    vlan=None,
                    vlan_idvlan=None
                )
                db.session.add(enlace)
                enlaces_creados += 1
    
    return enlaces_creados

def assign_vlans_to_slice_links(slice_id):
    """
    Asigna VLANs automáticamente a los enlaces de un slice que no tengan
    """
    enlaces_sin_vlan = Enlace.query.filter_by(
        slice_idslice=slice_id, 
        vlan_idvlan=None
    ).all()
    
    vlans_asignadas = 0
    for enlace in enlaces_sin_vlan:
        available_vlan = Vlan.query.filter_by(estado='disponible').first()
        if available_vlan:
            enlace.vlan = available_vlan.numero
            enlace.vlan_idvlan = available_vlan.idvlan
            available_vlan.estado = 'ocupada'
            vlans_asignadas += 1
        else:
            break  # No hay más VLANs disponibles
    
    db.session.commit()
    return vlans_asignadas

def update_slice_links(slice_obj, topology_data, node_to_instance_map):
    """
    Actualiza los enlaces del slice basado en la nueva topología
    """
    if not topology_data or 'edges' not in topology_data:
        return 0
    
    # 🟢 OBTENER ENLACES EXISTENTES
    existing_links = Enlace.query.filter_by(slice_idslice=slice_obj.idslice).all()
    existing_connections = set()
    
    for link in existing_links:
        # Crear identificador único para cada conexión (ordenado para evitar duplicados)
        vm_pair = tuple(sorted([int(link.vm1), int(link.vm2)]))
        existing_connections.add(vm_pair)
    
    # 🟢 PROCESAR NUEVOS ENLACES DE LA TOPOLOGÍA
    enlaces_creados = 0
    new_connections = set()
    
    for edge in topology_data['edges']:
        from_node = edge.get('from')
        to_node = edge.get('to')
        
        if from_node and to_node and from_node in node_to_instance_map and to_node in node_to_instance_map:
            vm1_id = node_to_instance_map[from_node]
            vm2_id = node_to_instance_map[to_node]
            
            # Crear identificador único para esta conexión
            vm_pair = tuple(sorted([vm1_id, vm2_id]))
            new_connections.add(vm_pair)
            
            # 🟢 CREAR ENLACE SOLO SI NO EXISTE
            if vm_pair not in existing_connections:
                enlace = Enlace(
                    vm1=str(vm1_id),
                    vm2=str(vm2_id),
                    slice_idslice=slice_obj.idslice,
                    vlan=None,
                    vlan_idvlan=None
                )
                db.session.add(enlace)
                enlaces_creados += 1
    
    # 🟢 OPCIONAL: ELIMINAR ENLACES QUE YA NO ESTÁN EN LA TOPOLOGÍA
    # (Solo si quieres que la topología sea la fuente de verdad absoluta)
    enlaces_eliminados = 0
    for link in existing_links:
        vm_pair = tuple(sorted([int(link.vm1), int(link.vm2)]))
        if vm_pair not in new_connections:
            # Este enlace ya no está en la nueva topología
            if link.vlan_obj:
                link.vlan_obj.estado = 'disponible'  # Liberar VLAN
            db.session.delete(link)
            enlaces_eliminados += 1
    
    return enlaces_creados

@app.route('/')
def index():
    """Redirect to login if not authenticated, otherwise to dashboard"""
    if 'user_id' in session:
        return redirect(url_for('dashboard'))
    return redirect(url_for('login'))

@app.route('/test')
def test():
    app.logger.error("ERROR: prueba de Flask desde web_app")
    return "ok"


@app.route('/grafana')
def grafana_dashboard():
    """Vista embebida de Grafana - Workers Monitoring Dashboard"""
    if 'user_id' not in session:
        flash('Por favor inicia sesión para acceder al dashboard de monitoreo.', 'error')
        return redirect(url_for('login'))

    user = User.query.get(session['user_id'])
    if not user:
        flash('Usuario no encontrado. Por favor, inicia sesión de nuevo.', 'error')
        session.clear()
        return redirect(url_for('login'))

    # Solo admin y superadmin pueden ver el monitoreo
    if not is_admin_user(user):
        flash('No tienes los permisos necesarios para acceder al monitoreo de infraestructura.', 'error')
        return redirect(url_for('dashboard'))

    # URL del dashboard de Workers Monitoring
    # Modo kiosk para ocultar menús de Grafana
    grafana_url = "http://10.20.12.106:3000/d/workers-monitoring-v2/workers-monitoring-dashboard-enhanced?orgId=1&refresh=5s"

    app.logger.info(f"🌀 Admin {user.nombre} accediendo a monitoreo de workers")
    return render_template('grafana_embed.html', grafana_url=grafana_url, user=user)

@app.route('/login', methods=['GET', 'POST'])
def login():
    """Login page - authenticate via Auth microservice"""
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']

        try:
            # Enviar credenciales al servicio auth
            response = requests.post(
                AUTH_SERVICE_URL,
                data={"username": username, "password": password},
                headers={"Content-Type": "application/x-www-form-urlencoded"}
            )

            print("Respuesta del servicio:", response.status_code, response.text)

            if response.status_code == 200:
                data = response.json()
                session['access_token'] = data['access_token']
                session['username'] = username

                # Verificar token para obtener rol e ID
                verify = requests.get(VERIFY_URL, headers={"Authorization": f"Bearer {data['access_token']}"})
                if verify.status_code == 200:
                    decoded = verify.json()
                    session['user_id'] = decoded.get('sub')
                    session['access_token'] = data['access_token'] # Guardar token en sesión
                    session['user_role'] = decoded.get('role')
                    app.logger.info(f"SESIÓN CREADA: {session}")
                    flash(f"Bienvenido {username}!", "success")
                    return redirect(url_for('dashboard'))
                else:
                    flash("Error verificando token", "error")

            else:
                flash("Credenciales inválidas", "error")

        except Exception as e:
            flash(f"Error de conexión con el servicio de autenticación: {e}", "error")

    return render_template('login.html')
    
@app.route('/register', methods=['GET', 'POST'])
def register():
    """User registration page"""
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        confirm_password = request.form['confirm_password']
        
        # Validation
        if password != confirm_password:
            flash('Passwords do not match', 'error')
            return render_template('register.html')
        
        if User.query.filter_by(nombre=username).first():
            flash('Username already exists', 'error')
            return render_template('register.html')
        
        # Create new user with default user role
        user_rol = Rol.query.filter_by(nombre_rol='user').first()
        if not user_rol:
            # Create user role if it doesn't exist
            user_rol = Rol(nombre_rol='user')
            db.session.add(user_rol)
            db.session.commit()
        
        new_user = User(nombre=username, rol_idrol=user_rol.idrol)
        new_user.set_password(password)
        db.session.add(new_user)
        db.session.commit()
        
        flash('Registration successful! Please log in.', 'success')
        return redirect(url_for('login'))
    
    return render_template('register.html')


@app.route('/logout')
def logout():
    """Logout and clear session"""
    session.clear()
    flash('You have been logged out', 'info')
    return redirect(url_for('login'))

@app.route('/dashboard')
def dashboard():
    """Dashboard page - shows slices based on user role"""
    if 'user_id' not in session:
        flash('Please log in to access the dashboard', 'error')
        return redirect(url_for('login'))
    
    user = User.query.get(session['user_id'])
    if not user:
        flash('User not found', 'error')
        session.clear()
        return redirect(url_for('login'))
    
    # Get slices based on user role
    user_slices = get_user_slices(user)
    
    # Add role information for template
    user_role = user.rol.nombre_rol if user.rol else 'unknown'
    is_admin = is_admin_user(user)
    
    return render_template('dashboard.html', 
                         user=user, 
                         slices=user_slices,
                         user_role=user_role,
                         is_admin=is_admin)


@app.route('/create_slice', methods=['GET', 'POST'])
def create_slice():
    if 'user_id' not in session:
        flash('Please log in to create slices', 'error')
        return redirect(url_for('login'))
    
    user = User.query.get(session['user_id'])
    if not user:
        flash('User not found', 'error')
        return redirect(url_for('login'))
    
    if request.method == 'POST':
        try:
            # Get form data
            slice_name = request.form.get('slice_name', 'Unnamed Slice')
            num_vms = int(request.form['num_vms'])
            topology_type = request.form['topology_type']
            topology_data = request.form.get('topology_data', '')
            zona_disponibilidad = request.form.get('zona_disponibilidad', 'default')
            
            # Crear slice
            new_slice = Slice(
                nombre=slice_name,
                estado='DRAW',
                zonadisponibilidad=zona_disponibilidad,
                fecha_creacion=datetime.now().date()
            )
            
            # Parse topology data
            topology_dict = {}
            if topology_type == 'custom' and topology_data:
                try:
                    topology_dict = json.loads(topology_data)
                except json.JSONDecodeError:
                    topology_dict = {'nodes': [], 'edges': []}
            else:
                # Generate predefined topology
                nodes = []
                edges = []
                
                for i in range(1, num_vms + 1):
                    vm_name = request.form.get(f'vm_{i}_name', f'VM{i}')
                    nodes.append({
                        'id': i,
                        'label': vm_name,
                        'color': '#28a745'
                    })
                
                if topology_type == 'star':
                    for i in range(2, num_vms + 1):
                        edges.append({'from': 1, 'to': i})
                elif topology_type == 'tree':
                    for i in range(2, num_vms + 1):
                        parent = (i - 1) // 2
                        if parent == 0:
                            parent = 1
                        edges.append({'from': parent, 'to': i})
                
                topology_dict = {'nodes': nodes, 'edges': edges}
            
            # Set topology as JSON
            new_slice.set_topology_data(topology_dict)
            
            db.session.add(new_slice)
            db.session.flush()  # 🟢 IMPORTANTE: flush para obtener el ID del slice
            
            # Add current user to slice
            new_slice.usuarios.append(user)
            
            # 🟢 MAPEO: Diccionario para mapear nodo_id -> instancia_id
            node_to_instance_map = {}
            
            # Crear instancias
            for i in range(1, num_vms + 1):
                vm_name = request.form.get(f'vm_{i}_name', f'VM{i}')
                vm_cpu = request.form.get(f'vm_{i}_cpu', '1')
                vm_ram = request.form.get(f'vm_{i}_ram', '1GB')
                vm_storage = request.form.get(f'vm_{i}_storage', '10GB')
                vm_internet = request.form.get(f'vm_{i}_internet') == 'on'
                vm_image_name = request.form.get(f'vm_{i}_image', 'ubuntu:latest')
                
                # Obtener o crear la imagen
                imagen = Imagen.query.filter_by(nombre=vm_image_name).first()
                if not imagen:
                    max_id = db.session.query(db.func.max(Imagen.idimagen)).scalar()
                    next_id = (max_id or 0) + 1
                    imagen = Imagen(
                        idimagen=next_id,
                        nombre=vm_image_name,
                        ruta=f'default'
                    )
                    db.session.add(imagen)
                    db.session.flush()
                
                instance = Instancia(
                    slice_idslice=new_slice.idslice,
                    nombre=vm_name,
                    cpu=vm_cpu,
                    ram=vm_ram,
                    storage=vm_storage,
                    salidainternet=vm_internet,
                    imagen_idimagen=imagen.idimagen,
                    ip=None,  # Se asignará después
                    vnc_idvnc=None,
                    worker_idworker=None
                )
                db.session.add(instance)
                db.session.flush()  # 🟢 Flush para obtener el ID de la instancia
                
                # 🟢 MAPEAR: nodo_id (i) -> instancia_id real
                node_to_instance_map[i] = instance.idinstancia
            
            # 🟢 CREAR ENLACES en la tabla enlace
            if 'edges' in topology_dict:
                for edge in topology_dict['edges']:
                    from_node = edge.get('from')
                    to_node = edge.get('to')
                    
                    if from_node and to_node and from_node in node_to_instance_map and to_node in node_to_instance_map:
                        # Obtener los IDs reales de las instancias
                        vm1_id = node_to_instance_map[from_node]
                        vm2_id = node_to_instance_map[to_node]
                        
                        # Crear enlace sin VLAN (se asignará después)
                        enlace = Enlace(
                            vm1=str(vm1_id),
                            vm2=str(vm2_id),
                            slice_idslice=new_slice.idslice,
                            vlan=None,
                            vlan_idvlan=None
                        )
                        db.session.add(enlace)
            
            db.session.commit()
            flash(f'Slice "{slice_name}" creado exitosamente con {len(topology_dict.get("edges", []))} enlaces!', 'success')
            return redirect(url_for('dashboard'))
            
        except Exception as e:
            db.session.rollback()
            flash(f'Error creando slice: {str(e)}', 'error')
            return redirect(url_for('create_slice'))
    
    # Pasar datos al template
    imagenes_disponibles = Imagen.query.all()
    zonas_disponibles = ['us-east-1', 'us-west-1', 'eu-west-1', 'default']
    
    return render_template('create_slice2.html', 
                         imagenes=imagenes_disponibles,
                         zonas=zonas_disponibles)




@app.route('/slice/<int:slice_id>')
def slice_detail(slice_id):
    if 'user_id' not in session:
        return jsonify({'error': 'Not authenticated'}), 401
    
    user = User.query.get(session['user_id'])
    if not user:
        return jsonify({'error': 'User not found'}), 401
    
    slice_obj = Slice.query.get_or_404(slice_id)
    
    # Check if user can access this slice
    if not can_access_slice(user, slice_obj):
        return jsonify({'error': 'Access denied'}), 403
    
    # Get instances data
    instances = []
    for inst in slice_obj.instancias:
        instances.append({
            'id': inst.id,
            'nombre': inst.nombre,
            'cpu': inst.cpu,
            'ram': inst.ram,
            'storage': inst.storage,
            'imagen': inst.imagen,
            'estado': inst.estado
        })
    
    # Get slice owners (users associated with this slice)
    owners = [u.nombre for u in slice_obj.usuarios]
    
    return jsonify({
        'id': slice_obj.idslice,
        'nombre': slice_obj.nombre,
        'estado': slice_obj.estado,
        'topologia': slice_obj.get_topology_data(),
        'fecha_creacion': slice_obj.fecha_creacion.strftime('%Y-%m-%d'),
        'instances': instances,
        'owners': owners,
        'current_user_role': user.rol.nombre_rol if user.rol else 'unknown'
    })

@app.route('/slice/<int:slice_id>/topology')
def slice_topology(slice_id):
    if 'user_id' not in session:
        flash('Please log in to view slice topology', 'error')
        return redirect(url_for('login'))
    
    user = User.query.get(session['user_id'])
    if not user:
        flash('User not found', 'error')
        return redirect(url_for('login'))
    
    slice_obj = Slice.query.get_or_404(slice_id)
    
    # Check if user can access this slice
    if not can_access_slice(user, slice_obj):
        flash('Access denied - You can only view your own slices', 'error')
        return redirect(url_for('dashboard'))
    
    platform = slice_obj.platform if slice_obj.platform else 'linux'
    
    app.logger.info(f" Cargando topología del slice {slice_id} - Plataforma: {platform}")
    
    return render_template('slice_topology.html', 
                         slice=slice_obj, 
                         user=user,
                         platform=platform)


"""@app.route('/users')
def list_users():
    if 'user_id' not in session:
        flash('Please log in to access this page', 'error')
        return redirect(url_for('login'))
    
    user = User.query.get(session['user_id'])
    if not user or not is_admin_user(user):
        flash('Access denied - Admin privileges required', 'error')
        return redirect(url_for('dashboard'))
    
    all_users = User.query.all()
    return render_template('users.html', users=all_users, current_user=user)

@app.route('/slice/<int:slice_id>/start', methods=['POST'])
def start_slice(slice_id):
    if 'user_id' not in session:
        return jsonify({'error': 'Not authenticated'}), 401
    
    user = User.query.get(session['user_id'])
    if not user:
        return jsonify({'error': 'User not found'}), 401
    
    slice_obj = Slice.query.get_or_404(slice_id)
    
    # Check if user can access this slice
    if not can_access_slice(user, slice_obj):
        return jsonify({'error': 'Access denied'}), 403
    
    # Update slice state
    slice_obj.estado = 'RUNNING'
    
    # Update all instances in this slice
    for instance in slice_obj.instancias:
        instance.estado = 'RUNNING'
    
    db.session.commit()
    
    return jsonify({
        'success': True,
        'message': f'Slice {slice_obj.nombre} started successfully',
        'new_state': slice_obj.estado
    })

@app.route('/slice/<int:slice_id>/stop', methods=['POST'])
def stop_slice(slice_id):
    if 'user_id' not in session:
        return jsonify({'error': 'Not authenticated'}), 401
    
    user = User.query.get(session['user_id'])
    if not user:
        return jsonify({'error': 'User not found'}), 401
    
    slice_obj = Slice.query.get_or_404(slice_id)
    
    # Check if user can access this slice
    if not can_access_slice(user, slice_obj):
        return jsonify({'error': 'Access denied'}), 403
    
    # Update slice state
    slice_obj.estado = 'STOPPED'
    
    # Update all instances in this slice
    for instance in slice_obj.instancias:
        instance.estado = 'STOPPED'
    
    db.session.commit()
    
    return jsonify({
        'success': True,
        'message': f'Slice {slice_obj.nombre} stopped successfully',
        'new_state': slice_obj.estado
    })
"""
@app.route('/delete_slice/<int:slice_id>', methods=['POST'])
def delete_slice(slice_id):
    if 'user_id' not in session:
        return jsonify({'error': 'Not authenticated'}), 401
    
    user = User.query.get(session['user_id'])
    if not user:
        return jsonify({'error': 'User not found'}), 401
    
    slice_obj = Slice.query.get_or_404(slice_id)
    
    if not can_access_slice(user, slice_obj):
        return jsonify({'error': 'Access denied'}), 403
    
    slice_name = slice_obj.nombre or f'Slice #{slice_id}'
    current_estado = slice_obj.estado
    
    # 🟢 AHORA PERMITE DRAW, STOPPED Y RUNNING
    if current_estado not in ['DRAW', 'STOPPED', 'RUNNING']:
        return jsonify({
            'success': False,
            'error': f'No se puede eliminar slice en estado "{current_estado}"',
            'message': 'Solo se pueden eliminar slices en estado DRAW, STOPPED o RUNNING'
        }), 400
    
    print(f"🗑️ Iniciando eliminación del slice {slice_id} en estado '{current_estado}'")
    
    try:
        if current_estado == 'DRAW':
            # ✅ ELIMINACIÓN SIMPLE: Solo BD (código existente)
            print(f"📝 Slice en estado DRAW - Eliminación simple de BD")
            
            enlaces_count = Enlace.query.filter_by(slice_idslice=slice_id).count()
            instancias_count = len(slice_obj.instancias)
            
            enlaces_del = Enlace.query.filter_by(slice_idslice=slice_id)
            for enlace in enlaces_del:
                db.session.delete(enlace)
            
            for instancia in slice_obj.instancias:
                db.session.delete(instancia)
            
            for usuario in slice_obj.usuarios:
                slice_obj.usuarios.remove(usuario)
            
            db.session.delete(slice_obj)
            db.session.commit()
            
            return jsonify({
                'success': True,
                'type': 'simple_delete',
                'message': f'Slice "{slice_name}" eliminado de la base de datos',
                'details': {
                    'slice_estado': current_estado,
                    'instancias_eliminadas': instancias_count,
                    'enlaces_eliminados': enlaces_count,
                    'infraestructura_limpiada': False
                }
            })
            
        elif current_estado in ['STOPPED', 'RUNNING']:
            # 🟢 ELIMINACIÓN COMPLETA: Llamar al Slice Manager
            action_type = 'parada_y_eliminacion' if current_estado == 'RUNNING' else 'eliminacion_completa'
            print(f"🏗️ Slice en estado {current_estado} - {action_type} vía Slice Manager")
            
            SLICE_MANAGER_URL = os.getenv("SLICE_MANAGER_URL", "http://slice-manager:8000")
            payload = {"id_slice": slice_id}
            
            try:
                response = requests.post(
                    f"{SLICE_MANAGER_URL}/placement/delete",
                    json=payload,
                    timeout=120
                )
                
                if response.status_code == 200:
                    deletion_result = response.json()
                    
                    if deletion_result.get('success', False):
                        return jsonify({
                            'success': True,
                            'type': action_type,
                            'message': f'Slice "{slice_name}" {"detenido y " if current_estado == "RUNNING" else ""}eliminado completamente',
                            'details': {
                                'slice_estado': current_estado,
                                'vms_eliminadas': deletion_result.get('vms', {}).get('eliminadas', 0),
                                'vlans_liberadas': deletion_result.get('recursos_red', {}).get('vlans_liberadas', 0),
                                'vncs_liberados': deletion_result.get('recursos_red', {}).get('vncs_liberados', 0),
                                'interfaces_tap_eliminadas': deletion_result.get('interfaces_tap_eliminadas', 0),
                                'infraestructura_limpiada': True,
                                'slice_manager_response': deletion_result.get('resumen', {})
                            }
                        })
                    else:
                        return jsonify({
                            'success': False,
                            'type': 'partial_delete',
                            'error': f'Eliminación parcial del slice "{slice_name}"',
                            'details': deletion_result,
                            'message': 'Algunos recursos pueden no haberse liberado correctamente'
                        }), 206
                else:
                    return jsonify({
                        'success': False,
                        'type': 'communication_error',
                        'error': f'Error del Slice Manager: HTTP {response.status_code}',
                        'details': {
                            'slice_estado': current_estado,
                            'response_text': response.text[:300]
                        }
                    }), 500
                    
            except requests.exceptions.Timeout:
                return jsonify({
                    'success': False,
                    'type': 'timeout_error',
                    'error': 'Timeout eliminando slice',
                    'message': f'La eliminación del slice "{slice_name}" excedió el tiempo límite'
                }), 408
                
            except requests.exceptions.RequestException as e:
                return jsonify({
                    'success': False,
                    'type': 'network_error',
                    'error': 'Error de red comunicándose con Slice Manager',
                    'details': str(e)
                }), 500
                
    except Exception as e:
        db.session.rollback()
        print(f"❌ Error eliminando slice {slice_id}: {str(e)}")
        return jsonify({
            'success': False,
            'type': 'database_error',
            'error': f'Error durante eliminación: {str(e)}',
            'message': f'Error eliminando slice "{slice_name}"'
        }), 500

"""@app.route('/download_topology/<int:slice_id>')
def download_topology(slice_id):
    if 'user_id' not in session:
        return jsonify({'error': 'Not authenticated'}), 401
    
    user = User.query.get(session['user_id'])
    if not user:
        return jsonify({'error': 'User not found'}), 401
    
    slice_obj = Slice.query.get_or_404(slice_id)
    
    # Check if user can access this slice
    if not can_access_slice(user, slice_obj):
        return jsonify({'error': 'Access denied'}), 403
    
    # Get topology data
    topology_data = slice_obj.get_topology_data()
    if not topology_data:
        topology_data = {'nodes': [], 'edges': []}
    
    # Create response with proper headers for file download
    response = jsonify(topology_data)
    slice_name = slice_obj.nombre or f'slice_{slice_id}'
    response.headers['Content-Disposition'] = f'attachment; filename="{slice_name}_topology.json"'
    response.headers['Content-Type'] = 'application/json'
    
    return response"""

# Agregar estas nuevas rutas al final del archivo app.py

@app.route('/edit_slice/<int:slice_id>')
def edit_slice(slice_id):
    if 'user_id' not in session:
        flash('Please log in to edit slices', 'error')
        return redirect(url_for('login'))
    
    user = User.query.get(session['user_id'])
    if not user:
        flash('User not found', 'error')
        return redirect(url_for('login'))
    
    slice_obj = Slice.query.get_or_404(slice_id)
    
    # Check if user can access this slice
    if not can_access_slice(user, slice_obj):
        flash('Access denied - You can only edit your own slices', 'error')
        return redirect(url_for('dashboard'))
    
    # Check if slice is in STOPPED state
    if slice_obj.estado not in ['STOPPED', 'DRAW']:
        flash('Solo se pueden editar slices en estado STOPPED o DRAW', 'error')
        return redirect(url_for('dashboard'))
    
    # 🟢 SINCRONIZAR TOPOLOGÍA CON ENLACES DE LA BASE DE DATOS
    current_topology = synchronize_topology_with_links(slice_obj)
    
    # Convert instances to serializable format
    instances_data = []
    for instance in slice_obj.instancias:
        instances_data.append({
            'id': instance.idinstancia,
            'nombre': instance.nombre,
            'cpu': instance.cpu,
            'ram': instance.ram,
            'storage': instance.storage,
            'imagen': instance.imagen.nombre if instance.imagen else 'N/A',
            'estado': instance.estado,
            'ip': instance.ip or 'No asignada',
            'salidainternet': instance.salidainternet
        })
    
    # Get available images and zones for new VMs
    imagenes_disponibles = Imagen.query.all()
    zonas_disponibles = ['us-east-1', 'us-west-1', 'eu-west-1', 'default']
    
    return render_template('edit_slice.html', 
                         slice=slice_obj, 
                         user=user,
                         current_topology=current_topology,
                         instances_data=instances_data,
                         imagenes=imagenes_disponibles,
                         zonas=zonas_disponibles)

def synchronize_topology_with_links(slice_obj):
    """
    Sincroniza la topología JSON con los enlaces reales de la base de datos
    """
    # Obtener topología actual
    current_topology = slice_obj.get_topology_data()
    if not current_topology:
        current_topology = {'nodes': [], 'edges': []}
    
    # 🟢 CREAR NODOS BASADOS EN INSTANCIAS REALES
    nodes = []
    instance_to_node_map = {}
    
    for idx, instance in enumerate(slice_obj.instancias, 1):
        node = {
            'id': idx,
            'label': instance.nombre,
            'color': '#28a745'
        }
        nodes.append(node)
        instance_to_node_map[instance.idinstancia] = idx
    
    # 🟢 CREAR EDGES BASADOS EN ENLACES REALES DE LA BD
    edges = []
    enlaces_bd = Enlace.query.filter_by(slice_idslice=slice_obj.idslice).all()
    
    for enlace in enlaces_bd:
        vm1_id = int(enlace.vm1)
        vm2_id = int(enlace.vm2)
        
        # Convertir IDs de instancia a IDs de nodo
        if vm1_id in instance_to_node_map and vm2_id in instance_to_node_map:
            edge = {
                'from': instance_to_node_map[vm1_id],
                'to': instance_to_node_map[vm2_id],
                'id': f"link_{enlace.idenlace}"
            }
            edges.append(edge)
    
    # 🟢 TOPOLOGÍA SINCRONIZADA
    synchronized_topology = {
        'nodes': nodes,
        'edges': edges
    }
    
    return synchronized_topology

@app.route('/update_slice/<int:slice_id>', methods=['POST'])
def update_slice(slice_id):
    if 'user_id' not in session:
        return jsonify({'error': 'Not authenticated'}), 401
    
    user = User.query.get(session['user_id'])
    if not user:
        return jsonify({'error': 'User not found'}), 401
    
    slice_obj = Slice.query.get_or_404(slice_id)
    
    # Check access and state
    if not can_access_slice(user, slice_obj):
        return jsonify({'error': 'Access denied'}), 403
    
    if slice_obj.estado not in ['STOPPED', 'DRAW']:
        return jsonify({'error': 'El slice debe estar en estado STOPPED para editarlo'}), 400
    
    try:
        # Get form data
        slice_name = request.form.get('slice_name', slice_obj.nombre)
        topology_data = request.form.get('topology_data', '')
        num_new_vms = int(request.form.get('num_new_vms', 0))
        zona_disponibilidad = request.form.get('zona_disponibilidad', slice_obj.zonadisponibilidad)
        
        # 🟢 OBTENER INSTANCIAS EXISTENTES PARA MAPEO
        existing_instances = slice_obj.instancias
        original_vm_count = len(existing_instances)
        
        # 🟢 CREAR MAPEO DE INSTANCIAS EXISTENTES (node_id -> instance_id)
        # Asumimos que las instancias existentes mantienen su orden/ID de nodo
        node_to_instance_map = {}
        for idx, instance in enumerate(existing_instances, 1):
            node_to_instance_map[idx] = instance.idinstancia
        
        # Update slice information
        slice_obj.nombre = slice_name
        slice_obj.zonadisponibilidad = zona_disponibilidad
        
        # 🟢 CREAR NUEVAS INSTANCIAS Y ACTUALIZAR MAPEO
        new_instances_created = 0
        new_instances = []
        
        for i in range(1, num_new_vms + 1):
            vm_name = request.form.get(f'new_vm_{i}_name', f'VM{original_vm_count + i}')
            vm_cpu = request.form.get(f'new_vm_{i}_cpu', '1')
            vm_ram = request.form.get(f'new_vm_{i}_ram', '1GB')
            vm_storage = request.form.get(f'new_vm_{i}_storage', '10GB')
            vm_image_name = request.form.get(f'new_vm_{i}_image', 'ubuntu:latest')
            vm_internet = request.form.get(f'new_vm_{i}_internet') == 'on'  # 🟢 Corregido checkbox
            
            # Obtener o crear la imagen
            imagen = Imagen.query.filter_by(nombre=vm_image_name).first()
            if not imagen:
                max_id = db.session.query(db.func.max(Imagen.idimagen)).scalar()
                next_id = (max_id or 0) + 1
                imagen = Imagen(
                    idimagen=next_id,
                    nombre=vm_image_name,
                    ruta=f'default'
                )
                db.session.add(imagen)
                db.session.flush()  # Para obtener el ID
            
            # Crear nueva instancia
            new_instance = Instancia(
                slice_idslice=slice_obj.idslice,
                nombre=vm_name,
                cpu=vm_cpu,
                ram=vm_ram,
                storage=vm_storage,
                salidainternet=vm_internet,
                imagen_idimagen=imagen.idimagen,
                ip=None,
                vnc_idvnc=None,
                worker_idworker=None
            )
            db.session.add(new_instance)
            db.session.flush()  # 🟢 Para obtener el ID de la nueva instancia
            
            # 🟢 AGREGAR AL MAPEO: Las nuevas VMs empiezan después de las existentes
            new_node_id = original_vm_count + i
            node_to_instance_map[new_node_id] = new_instance.idinstancia
            
            new_instances.append(new_instance)
            new_instances_created += 1
        
        # 🟢 ACTUALIZAR TOPOLOGÍA Y ENLACES
        enlaces_creados = 0
        if topology_data:
            try:
                topology_dict = json.loads(topology_data)
                
                # Actualizar topología JSON
                slice_obj.set_topology_data(topology_dict)
                
                # 🟢 GESTIONAR ENLACES EN LA TABLA ENLACE
                enlaces_creados = update_slice_links(slice_obj, topology_dict, node_to_instance_map)
                
            except json.JSONDecodeError:
                return jsonify({'error': 'Invalid topology data format'}), 400
        
        db.session.commit()
        
        # 🟢 MENSAJE DETALLADO DE ÉXITO
        message = f'Slice "{slice_obj.nombre}" actualizado exitosamente. '
        if new_instances_created > 0:
            message += f'Se agregaron {new_instances_created} nueva(s) VM(s). '
        if topology_data:
            message += f'Topología actualizada con {enlaces_creados} enlaces. '
        message += f'Total: {len(slice_obj.instancias)} VMs.'
        
        return jsonify({
            'success': True,
            'message': message,
            'slice_name': slice_obj.nombre,
            'new_vms_added': new_instances_created,
            'links_created': enlaces_creados,
            'total_vms': len(slice_obj.instancias),
            'original_vms': original_vm_count
        })
        
    except Exception as e:
        db.session.rollback()
        return jsonify({
            'success': False,
            'error': f'Error updating slice: {str(e)}'
        }), 500


@app.route('/deploy_slice/<int:slice_id>', methods=['POST'])
def deploy_slice(slice_id):
    if 'user_id' not in session:
        return jsonify({'error': 'Not authenticated'}), 401
    
    user = User.query.get(session['user_id'])
    if not user:
        return jsonify({'error': 'User not found'}), 401
    
    slice_obj = Slice.query.get_or_404(slice_id)
    
    if not can_access_slice(user, slice_obj):
        return jsonify({'error': 'Access denied'}), 403
    
    if slice_obj.estado != 'DRAW':
        return jsonify({
            'error': f'El slice debe estar en estado DRAW para desplegarse. Estado actual: {slice_obj.estado}'
        }), 400
    
    try:
        data = request.get_json() or {}
        platform = data.get('platform', 'linux')  
        valid_platforms = ['linux', 'openstack']
        if platform not in valid_platforms:
            return jsonify({
                'success': False,
                'error': f'Plataforma inválida: {platform}. Opciones válidas: {", ".join(valid_platforms)}'
            }), 400
        
        if platform == 'openstack' and not is_admin_user(user):
            return jsonify({
                'success': False,
                'error': 'Solo administradores pueden desplegar en OpenStack'
            }), 403
        zona = slice_obj.zonadisponibilidad or 'HP'
        SLICE_MANAGER_URL = "http://slice-manager:8000"
        payload = {
            "id_slice": slice_id,
            "platform": platform,
            "zonadisponibilidad": zona
        }
        
        app.logger.info(f"🚀 Desplegando slice {slice_id} en plataforma: {platform.upper()}")
        
        # 1️⃣ VERIFICAR VIABILIDAD
        verify_response = requests.post(
            f"{SLICE_MANAGER_URL}/placement/verify",
            json=payload,
            timeout=30
        )
        
        if verify_response.status_code != 200:
            return jsonify({
                'success': False,
                'error': f'Error verificando slice: HTTP {verify_response.status_code}',
                'details': verify_response.text[:300]
            })
        
        verify_result = verify_response.json()
        
        if not verify_result.get('can_deploy', False):
            print("🔍 DEBUG verify_result:", verify_result)
            app.logger.error(f"[VERIFY ERROR] {verify_result}")
            return jsonify({
                'success': False,
                'error': 'El slice no puede ser desplegado en este momento',
                'reason_backend': verify_result.get('error', None),
                'raw_backend': verify_result,
                'platform': platform
            })
        
        # Extraemos lo que decidió VM Placement del verify :D roberto kbro
        placement_plan = verify_result.get('placement_plan', [])
        modo = verify_result.get('modo', 'unknown')

        if not placement_plan:
            # Algo raro: dijo can_deploy=True pero no mandó plan
            app.logger.error(f"[VERIFY ERROR] can_deploy=True PERO placement_plan vacío: {verify_result}")
            return jsonify({
                'success': False,
                'error': 'VM Placement no devolvió un plan de despliegue válido',
                'raw_backend': verify_result
            })


        # 2️⃣ CAMBIAR ESTADO A DEPLOYING
        slice_obj.estado = 'DEPLOYING'
        db.session.commit()
        
        #Payload pal deploy
        deploy_payload = {
            "id_slice": slice_id,
            "platform": platform,
            "zonadisponibilidad": zona,
            "placement_plan": placement_plan,
            "modo": modo
        }

        # 3️⃣ DESPLEGAR
        deploy_response = requests.post(
            f"{SLICE_MANAGER_URL}/placement/deploy",
            json=deploy_payload,
            timeout=120
        )
        
        if deploy_response.status_code != 200:
            slice_obj.estado = 'DRAW'
            db.session.commit()
            
            return jsonify({
                'success': False,
                'error': f'Error en despliegue: HTTP {deploy_response.status_code}',
                'details': deploy_response.text[:300],
                'platform': platform
            })
        
        deploy_result = deploy_response.json()
        
        # 4️⃣ PROCESAR RESULTADO
        success = deploy_result.get('success', False)
        final_state = deploy_result.get('estado_final', 'RUNNING' if success else 'FAILED')
        
        slice_obj.estado = final_state
        db.session.commit()
        
        if success:
            return jsonify({
                'success': True,
                'message': f'Slice "{slice_obj.nombre}" desplegado exitosamente en {platform.upper()}',
                'new_status': final_state,
                'platform': platform,
                'deployment_summary': deploy_result.get('resumen', {}),
                'slice_manager_url': SLICE_MANAGER_URL
            })
        else:
            return jsonify({
                'success': False,
                'error': deploy_result.get('error', 'Error en despliegue'),
                'new_status': final_state,
                'platform': platform,
                'details': deploy_result.get('message', 'Despliegue falló')
            })
            
    except requests.exceptions.ConnectionError as e:
        try:
            slice_obj.estado = 'DRAW'
            db.session.commit()
        except:
            pass
        
        return jsonify({
            'success': False,
            'error': 'No se puede conectar con Slice Manager',
            'details': f'Servicio no disponible: {str(e)}',
            'slice_manager_url': SLICE_MANAGER_URL,
            'platform': platform
        }), 503
        
    except requests.exceptions.Timeout as e:
        return jsonify({
            'success': False,
            'error': 'Timeout en despliegue',
            'details': 'El despliegue puede estar en progreso, verifica en unos minutos',
            'platform': platform
        }), 408
        
    except Exception as e:
        try:
            slice_obj.estado = 'DRAW'
            db.session.commit()
        except:
            pass
        
        return jsonify({
            'success': False,
            'error': 'Error interno del servidor',
            'details': str(e),
            'platform': platform
        }), 500

@app.route('/debug_slice_manager')
def debug_slice_manager():
    """Endpoint para verificar conectividad con Slice Manager"""
    if 'user_id' not in session:
        return jsonify({'error': 'Not authenticated'}), 401
    
    SLICE_MANAGER_URL = os.getenv("SLICE_MANAGER_URL", "http://localhost:8000")
    
    try:
        # Probar conectividad básica
        response = requests.get(f"{SLICE_MANAGER_URL}/", timeout=10)
        
        return jsonify({
            'slice_manager_url': SLICE_MANAGER_URL,
            'status': response.status_code,
            'response': response.json() if response.status_code == 200 else response.text,
            'connectivity': 'OK' if response.status_code == 200 else 'ERROR'
        })
        
    except Exception as e:
        return jsonify({
            'slice_manager_url': SLICE_MANAGER_URL,
            'connectivity': 'FAILED',
            'error': str(e)
        })


@app.route('/check_slice_status/<int:slice_id>')
def check_slice_status(slice_id):
    """Endpoint para verificar el estado actual de un slice"""
    if 'user_id' not in session:
        return jsonify({'error': 'Not authenticated'}), 401
    
    user = User.query.get(session['user_id'])
    slice_obj = Slice.query.get_or_404(slice_id)
    
    if not can_access_slice(user, slice_obj):
        return jsonify({'error': 'Access denied'}), 403
    
    return jsonify({
        'slice_id': slice_id,
        'nombre': slice_obj.nombre,
        'estado': slice_obj.estado,
        'can_deploy': slice_obj.estado == 'DRAW',
        'total_vms': len(slice_obj.instancias)
    })

@app.route('/vnc_console/<int:instance_id>')
def vnc_console(instance_id):
    """Renderiza la página de consola VNC para una instancia"""
    if 'user_id' not in session:
        flash('Por favor inicia sesión para acceder a la consola', 'error')
        return redirect(url_for('login'))
    
    user = User.query.get(session['user_id'])
    if not user:
        flash('Usuario no encontrado', 'error')
        return redirect(url_for('login'))
    
    instance = Instancia.query.get_or_404(instance_id)
    slice_obj = Slice.query.get(instance.slice_idslice)
    
    if not can_access_slice(user, slice_obj):
        flash('No tienes permiso para acceder a esta VM', 'error')
        return redirect(url_for('dashboard'))
    
    if instance.estado != 'RUNNING':
        flash(f'La VM debe estar en estado RUNNING. Estado actual: {instance.estado}', 'error')
        return redirect(url_for('slice_topology', slice_id=slice_obj.idslice))
    
    platform = getattr(slice_obj, 'platform', 'linux')
    
    # LÓGICA DIFERENCIADA POR PLATAFORMA
    if platform == 'openstack':
        console_url = getattr(instance, 'console_url', None) or getattr(instance, 'vnc_url', None)
        
        if not console_url:
            flash('Esta VM no tiene URL de consola configurada', 'error')
            return redirect(url_for('slice_topology', slice_id=slice_obj.idslice))
        
        app.logger.info(f"🌐 OpenStack VNC Console - VM: {instance.nombre}")
        app.logger.info(f"   Console URL original: {console_url}")
        
        try:
            # 🟢 NUEVO: Crear túnel SSH para OpenStack
            from utils.novnc_manager import ensure_openstack_tunnel_and_token
            
            # El gateway_ip se detecta automáticamente, pero puedes especificarlo
            # Si hay problemas, ajusta aquí:
            gateway_ip = os.getenv("GATEWAY_IP", "10.20.12.106")
            
            app.logger.info(f"   Gateway config: IP={gateway_ip}")
            
            proxied_console_url = ensure_openstack_tunnel_and_token(
                slice_id=slice_obj.idslice,
                instance_id=instance.idinstancia,
                console_url=console_url,
                gateway_ip=gateway_ip
            )
            
            app.logger.info(f"   Proxied URL: {proxied_console_url}")
            
            return render_template('vnc_console.html', 
                                 instance=instance, 
                                 slice=slice_obj,
                                 novnc_url=proxied_console_url,
                                 platform='openstack',
                                 user=user)
                                 
        except Exception as e:
            app.logger.error(f"❌ Error creando túnel OpenStack: {e}")
            flash(f'Error al procesar la consola OpenStack: {str(e)}', 'error')
            return redirect(url_for('slice_topology', slice_id=slice_obj.idslice))
    
    else:  # platform == 'linux'
        if not instance.vnc_idvnc:
            flash('Esta VM no tiene puerto VNC asignado', 'error')
            return redirect(url_for('slice_topology', slice_id=slice_obj.idslice))
        
        vnc_obj = Vnc.query.get(instance.vnc_idvnc)
        if not vnc_obj:
            flash('Puerto VNC no encontrado', 'error')
            return redirect(url_for('slice_topology', slice_id=slice_obj.idslice))
        
        worker_obj = Worker.query.get(instance.worker_idworker) if instance.worker_idworker else None
        
        vnc_display_port = vnc_obj.puerto  
        vnc_real_port = int(vnc_display_port) + 5900
        vnc_host = worker_obj.ip if worker_obj else 'localhost'
        
        from utils.novnc_manager import ensure_tunnel_and_token
        
        novnc_url = ensure_tunnel_and_token(
            slice_obj.idslice,
            instance.idinstancia,
            vnc_host,
            vnc_real_port
        )
        
        app.logger.info(f"🖥️ Linux VNC Console - VM: {instance.nombre}")
        app.logger.info(f"   Worker IP: {vnc_host}")
        app.logger.info(f"   Display Port (BD): {vnc_display_port}")
        app.logger.info(f"   Real VNC Port: {vnc_real_port}")
        app.logger.info(f"   noVNC URL: {novnc_url}")

        return render_template('vnc_console.html', 
                             instance=instance, 
                             slice=slice_obj,
                             vnc_display_port=vnc_obj.puerto,
                             vnc_real_port=vnc_real_port,
                             vnc_host=vnc_host,
                             novnc_url=novnc_url,
                             platform='linux',
                             user=user)


@app.route('/api/vnc/status/<int:instance_id>')
def vnc_status(instance_id):
    """API endpoint para verificar el estado de la conexión VNC"""
    if 'user_id' not in session:
        return jsonify({'error': 'No autenticado'}), 401
    
    user = User.query.get(session['user_id'])
    instance = Instancia.query.get_or_404(instance_id)
    slice_obj = Slice.query.get(instance.slice_idslice)
    
    if not can_access_slice(user, slice_obj):
        return jsonify({'error': 'Acceso denegado'}), 403
    
    vnc_obj = Vnc.query.get(instance.vnc_idvnc) if instance.vnc_idvnc else None
    worker_obj = Worker.query.get(instance.worker_idworker) if instance.worker_idworker else None
    
    return jsonify({
        'instance_id': instance.idinstancia,
        'instance_name': instance.nombre,
        'estado': instance.estado,
        'vnc_available': instance.vnc_idvnc is not None,
        'vnc_port': vnc_obj.puerto if vnc_obj else None,
        'worker_ip': worker_obj.ip if worker_obj else None,
        'worker_name': worker_obj.nombre if worker_obj else None,
        'can_connect': instance.estado == 'RUNNING' and instance.vnc_idvnc is not None
    })


@app.route('/api/vnc/send_keys/<int:instance_id>', methods=['POST'])
def vnc_send_keys(instance_id):
    """Endpoint para enviar combinaciones de teclas especiales (Ctrl+Alt+Del)"""
    if 'user_id' not in session:
        return jsonify({'error': 'No autenticado'}), 401
    
    user = User.query.get(session['user_id'])
    instance = Instancia.query.get_or_404(instance_id)
    slice_obj = Slice.query.get(instance.slice_idslice)
    
    if not can_access_slice(user, slice_obj):
        return jsonify({'error': 'Acceso denegado'}), 403
    
    keys = request.json.get('keys', '')
    

    
    return jsonify({
        'success': True,
        'message': f'Combinación de teclas {keys} enviada a {instance.nombre}'
    })


# ==========================================
# RUTAS DE GESTIÓN DE USUARIOS
# ==========================================

@app.route('/users')
def list_users():
    """Lista de usuarios - solo para administradores"""
    if 'user_id' not in session:
        flash('Por favor inicia sesión para acceder a esta página', 'error')
        return redirect(url_for('login'))
    
    user = User.query.get(session['user_id'])
    if not user:
        flash('Usuario no encontrado', 'error')
        return redirect(url_for('login'))
    
    # Verificar que sea administrador
    if not is_admin_user(user):
        flash('Acceso denegado - Se requieren privilegios de administrador', 'error')
        return redirect(url_for('dashboard'))
    
    # Obtener todos los usuarios con sus roles
    all_users = User.query.join(Rol).all()
    
    return render_template('users.html', users=all_users, current_user=user)


@app.route('/delete_user/<int:user_id>', methods=['POST'])
def delete_user(user_id):
    """Eliminar un usuario - solo administradores"""
    if 'user_id' not in session:
        return jsonify({'error': 'No autenticado'}), 401
    
    current_user = User.query.get(session['user_id'])
    if not current_user or not is_admin_user(current_user):
        return jsonify({'error': 'Acceso denegado'}), 403
    
    # No permitir auto-eliminación
    if user_id == current_user.idusuario:
        return jsonify({
            'success': False,
            'error': 'No puedes eliminar tu propio usuario'
        }), 400
    
    user_to_delete = User.query.get_or_404(user_id)
    username = user_to_delete.nombre
    
    try:
        # Verificar si el usuario tiene slices asociados
        slices_count = len(user_to_delete.slices)
        
        if slices_count > 0:
            return jsonify({
                'success': False,
                'error': f'El usuario tiene {slices_count} slice(s) asociado(s). Elimina o reasigna los slices primero.'
            }), 400
        
        # Eliminar usuario
        db.session.delete(user_to_delete)
        db.session.commit()
        
        return jsonify({
            'success': True,
            'message': f'Usuario "{username}" eliminado exitosamente'
        })
        
    except Exception as e:
        db.session.rollback()
        return jsonify({
            'success': False,
            'error': f'Error eliminando usuario: {str(e)}'
        }), 500


@app.route('/user_details/<int:user_id>')
def user_details(user_id):
    """Obtener detalles de un usuario - para modal o AJAX"""
    if 'user_id' not in session:
        return jsonify({'error': 'No autenticado'}), 401
    
    current_user = User.query.get(session['user_id'])
    if not current_user or not is_admin_user(current_user):
        return jsonify({'error': 'Acceso denegado'}), 403
    
    user = User.query.get_or_404(user_id)
    
    # Obtener información de los slices del usuario
    slices_info = []
    for slice_obj in user.slices:
        slices_info.append({
            'id': slice_obj.idslice,
            'nombre': slice_obj.nombre,
            'estado': slice_obj.estado,
            'instancias_count': len(slice_obj.instancias)
        })
    
    return jsonify({
        'id': user.idusuario,
        'nombre': user.nombre,
        'rol': user.rol.nombre_rol if user.rol else 'N/A',
        'rol_id': user.rol_idrol,
        'slices_count': len(user.slices),
        'slices': slices_info
    })

# ======================================
# RUTAS PARA ADMIN - ANALYTICS
# ======================================

@app.route('/admin/resources')
def admin_resources():
    """Dashboard de recursos para administradores"""
    if 'user_id' not in session:
        flash('Por favor inicia sesión', 'error')
        return redirect(url_for('login'))
    
    user = User.query.get(session['user_id'])
    if not user:
        flash('Usuario no encontrado', 'error')
        return redirect(url_for('login'))
    
    # Verificar que sea admin (rol_idrol = 1)
    if user.rol_idrol != 1:
        flash('Acceso denegado. Solo para administradores.', 'error')
        return redirect(url_for('dashboard'))
    
    return render_template('admin_resources.html', user=user)

@app.route('/api/analytics/resources/summary')
def api_analytics_summary():
    """Proxy para evitar CORS"""
    import requests
    try:
        resp = requests.get('http://10.20.12.161:5030/resources/summary', timeout=10)
        return resp.json(), resp.status_code
    except Exception as e:
        return {"error": str(e)}, 500

@app.route('/api/analytics/metrics/export/<fecha>')
def api_analytics_export(fecha):
    """Proxy para exportar CSV"""
    import requests
    try:
        resp = requests.get(f'http://10.20.12.161:5030/metrics/export/{fecha}', timeout=10)
        from flask import Response
        return Response(
            resp.content,
            mimetype='text/csv',
            headers={'Content-Disposition': f'attachment; filename=metrics_{fecha}.csv'}
        )
    except Exception as e:
        return {"error": str(e)}, 500
    
@app.route('/api/analytics/metrics/history')
def api_analytics_history():
    """Proxy para obtener histórico de métricas"""
    import requests
    
    # Obtener parámetro de minutos (default 30)
    minutes = request. args.get('minutes', 30, type=int)
    
    try:
        resp = requests.get(
            f'http://10.20.12.161:5030/metrics/history?minutes={minutes}', 
            timeout=10
        )
        return resp.json(), resp.status_code
    except Exception as e:
        return {"error": str(e)}, 500
     

if __name__ == '__main__':
    initialize_database()
    app.run(debug=True, host='0.0.0.0', port=5000)