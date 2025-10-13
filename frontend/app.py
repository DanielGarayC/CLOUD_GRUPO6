from flask import Flask, render_template, request, redirect, url_for, session, flash, jsonify
from models import db, User, Slice, Rol, Instancia, Imagen, Vnc, Worker, Enlace, Vlan
import os
import json
from datetime import datetime
import logging
import sys
import requests

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
    """Vista embebida de Grafana visible desde navegador y contenedor."""
    if 'user_id' not in session:
        flash('Por favor inicia sesión para acceder al dashboard de monitoreo.', 'error')
        return redirect(url_for('login'))

    user = User.query.get(session['user_id'])
    if not user:
        flash('Usuario no encontrado. Por favor, inicia sesión de nuevo.', 'error')
        session.clear()
        return redirect(url_for('login'))

    if user.rol_idrol not in [1, 2]:
        flash('No tienes los permisos necesarios para acceder a esta página.', 'error')
        return redirect(url_for('dashboard'))

    if os.environ.get("IN_DOCKER") == "true":
        grafana_url = "http://localhost:3000/d/d99c29a1-a13e-4b98-87cb-1d1601a129d6/dashboard-logs-teleflow?orgId=1&from=now-6h&to=now&kiosk"
    else:
        grafana_url = "http://grafana:3000/d/d99c29a1-a13e-4b98-87cb-1d1601a129d6/dashboard-logs-teleflow?orgId=1&from=now-6h&to=now&kiosk"

    app.logger.info(f"🌀 Grafana URL usada: {grafana_url}")
    return render_template('grafana_embed.html', grafana_url=grafana_url)

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
        # Get form data
        slice_name = request.form.get('slice_name', 'Unnamed Slice')
        num_vms = int(request.form['num_vms'])
        topology_type = request.form['topology_type']
        topology_data = request.form.get('topology_data', '')
        zona_disponibilidad = request.form.get('zona_disponibilidad', 'default')
        
        # Crear slice
        new_slice = Slice(
            nombre=slice_name,
            estado='STOPPED',
            zonadisponibilidad=zona_disponibilidad
        )
        
        # Set topology based on type
        if topology_type == 'custom' and topology_data:
            new_slice.topologia = topology_data
        else:
            # Generate predefined topology
            nodes = []
            edges = []
            
            for i in range(1, num_vms + 1):
                nodes.append({
                    'id': i,
                    'label': f'VM{i}',
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
            
            topology = {'nodes': nodes, 'edges': edges}
            new_slice.set_topology_data(topology)
        
        db.session.add(new_slice)
        db.session.commit()
        
        # Add current user to slice
        new_slice.usuarios.append(user)
        
        # Crear instancias - MODIFICADO para imagen individual e internet
        for i in range(1, num_vms + 1):
            vm_name = request.form.get(f'vm_{i}_name', f'VM{i}')
            vm_cpu = request.form.get(f'vm_{i}_cpu', '1')
            vm_ram = request.form.get(f'vm_{i}_ram', '1GB')
            vm_storage = request.form.get(f'vm_{i}_storage', '10GB')
            vm_internet = request.form.get(f'vm_{i}_internet') == 'on'  # Checkbox individual
            vm_ip = request.form.get(f'vm_{i}_ip', '')
            vm_image_name = request.form.get(f'vm_{i}_image', 'ubuntu:latest')  # Imagen individual
            
            # Obtener o crear la imagen específica para esta VM
            imagen = Imagen.query.filter_by(nombre=vm_image_name).first()
            if not imagen:
                max_id = db.session.query(db.func.max(Imagen.idimagen)).scalar()
                next_id = (max_id or 0) + 1
                imagen = Imagen(
                    idimagen=next_id,
                    nombre=vm_image_name,
                    ruta=f'/images/{vm_image_name}'
                )
                db.session.add(imagen)
                db.session.commit()
            
            instance = Instancia(
                slice_idslice=new_slice.idslice,
                nombre=vm_name,
                cpu=vm_cpu,
                ram=vm_ram,
                storage=vm_storage,
                salidainternet=vm_internet,  # Internet individual
                imagen_idimagen=imagen.idimagen,  # Imagen individual
                ip=vm_ip if vm_ip else None,
                vnc_idvnc=None,
                worker_idworker=None
            )
            db.session.add(instance)
        
        db.session.commit()
        flash('Slice created successfully!', 'success')
        return redirect(url_for('dashboard'))
    
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
    
    return render_template('slice_topology.html', slice=slice_obj, user=user)

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
    
    # Check if user can access this slice
    if not can_access_slice(user, slice_obj):
        return jsonify({'error': 'Access denied'}), 403
    
    slice_name = slice_obj.nombre or f'Slice #{slice_id}'
    
    try:
        # Delete the slice (cascade will handle related instances and interfaces)
        db.session.delete(slice_obj)
        db.session.commit()
        
        return jsonify({
            'success': True,
            'message': f'Slice {slice_name} deleted successfully'
        })
    except Exception as e:
        db.session.rollback()
        return jsonify({
            'success': False,
            'error': f'Error deleting slice: {str(e)}'
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
    if slice_obj.estado != 'STOPPED':
        flash('Solo se pueden editar slices en estado STOPPED', 'error')
        return redirect(url_for('dashboard'))
    
    # Get current topology data
    current_topology = slice_obj.get_topology_data()
    if not current_topology:
        current_topology = {'nodes': [], 'edges': []}
    
    # Convert instances to serializable format
    instances_data = []
    for instance in slice_obj.instancias:
        instances_data.append({
            'id': instance.idinstancia,
            'nombre': instance.nombre,
            'cpu': instance.cpu,
            'ram': instance.ram,
            'storage': instance.storage,
            'imagen': instance.imagen.nombre if instance.imagen else 'N/A',  # 🟢 CORREGIDO
            'estado': instance.estado,
            'ip': instance.ip or 'No asignada',  # 🟢 AGREGADO
            'salidainternet': instance.salidainternet  # 🟢 AGREGADO
        })
    
    # Get available images and zones for new VMs
    imagenes_disponibles = Imagen.query.all()
    zonas_disponibles = ['us-east-1', 'us-west-1', 'eu-west-1', 'default']
    
    return render_template('edit_slice.html', 
                         slice=slice_obj, 
                         user=user,
                         current_topology=current_topology,
                         instances_data=instances_data,
                         imagenes=imagenes_disponibles,  # 🟢 AGREGADO
                         zonas=zonas_disponibles)  # 🟢 AGREGADO

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
    
    if slice_obj.estado != 'STOPPED':
        return jsonify({'error': 'El slice debe estar en estado STOPPED para editarlo'}), 400
    
    try:
        # Get form data
        slice_name = request.form.get('slice_name', slice_obj.nombre)
        topology_data = request.form.get('topology_data', '')
        num_new_vms = int(request.form.get('num_new_vms', 0))
        zona_disponibilidad = request.form.get('zona_disponibilidad', slice_obj.zonadisponibilidad)
        
        # 🟢 VALIDACIÓN: Solo permitir cambios seguros
        original_vm_count = len(slice_obj.instancias)
        
        # Update slice information (solo campos permitidos)
        slice_obj.nombre = slice_name
        slice_obj.zonadisponibilidad = zona_disponibilidad
        
        # Update topology if provided
        if topology_data:
            slice_obj.topologia = topology_data
        
        # 🟢 CREAR SOLO NUEVAS INSTANCIAS (no tocar las existentes)
        new_instances_created = 0
        
        for i in range(1, num_new_vms + 1):
            vm_name = request.form.get(f'new_vm_{i}_name', f'VM{original_vm_count + i}')
            vm_cpu = request.form.get(f'new_vm_{i}_cpu', '1')
            vm_ram = request.form.get(f'new_vm_{i}_ram', '1GB')
            vm_storage = request.form.get(f'new_vm_{i}_storage', '10GB')
            vm_image_name = request.form.get(f'new_vm_{i}_image', 'ubuntu:latest')
            vm_internet = request.form.get(f'new_vm_{i}_internet', 'false') == 'true'
            vm_ip = request.form.get(f'new_vm_{i}_ip', '')
            
            # 🟢 OBTENER O CREAR LA IMAGEN
            imagen = Imagen.query.filter_by(nombre=vm_image_name).first()
            if not imagen:
                # Crear imagen si no existe
                max_id = db.session.query(db.func.max(Imagen.idimagen)).scalar()
                next_id = (max_id or 0) + 1
                imagen = Imagen(
                    idimagen=next_id,
                    nombre=vm_image_name,
                    ruta=f'/images/{vm_image_name}'
                )
                db.session.add(imagen)
                db.session.commit()
            
            # 🟢 CREAR NUEVA INSTANCIA CON ESTRUCTURA CORRECTA
            new_instance = Instancia(
                slice_idslice=slice_obj.idslice,
                nombre=vm_name,
                cpu=vm_cpu,
                ram=vm_ram,
                storage=vm_storage,
                salidainternet=vm_internet,
                imagen_idimagen=imagen.idimagen,  # 🟢 RELACIÓN CORRECTA
                ip=vm_ip if vm_ip else None,
                vnc_idvnc=None,  # Opcional por ahora
                worker_idworker=None  # Opcional por ahora
            )
            db.session.add(new_instance)
            new_instances_created += 1
        
        db.session.commit()
        
        # 🟢 MENSAJE DETALLADO DE ÉXITO
        message = f'Slice "{slice_obj.nombre}" actualizado exitosamente. '
        if new_instances_created > 0:
            message += f'Se agregaron {new_instances_created} nueva(s) VM(s). '
        if topology_data:
            message += 'Topología actualizada. '
        message += f'Las {original_vm_count} VM(s) existentes se mantuvieron intactas.'
        
        return jsonify({
            'success': True,
            'message': message,
            'slice_name': slice_obj.nombre,
            'new_vms_added': new_instances_created,
            'total_vms': len(slice_obj.instancias),
            'original_vms': original_vm_count
        })
        
    except Exception as e:
        db.session.rollback()
        return jsonify({
            'success': False,
            'error': f'Error updating slice: {str(e)}'
        }), 500

if __name__ == '__main__':
    initialize_database()
    app.run(debug=True, host='0.0.0.0', port=5000)