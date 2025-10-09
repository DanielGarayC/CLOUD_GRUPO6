from flask import Flask, render_template, request, redirect, url_for, session, flash, jsonify
from models import db, User, Slice, Rol, Security, Instancia, Interfaz
import os
import json
from datetime import datetime
import logging
import sys


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

@app.route('/login', methods=['GET', 'POST'])
def login():
    """Login page - authenticate against existing users in database"""
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        
        # Query user from existing database
        user = User.query.filter_by(nombre=username).first()
        
        if user and user.check_password(password):
            session['user_id'] = user.id
            session['username'] = user.nombre
            session['user_role'] = user.rol.nombre_rol if user.rol else 'unknown'
            
            flash(f'Login successful! Welcome {user.nombre}', 'success')
            return redirect(url_for('dashboard'))
        else:
            flash('Invalid username or password', 'error')
    
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
    """Create new slice page - only for authenticated users"""
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
        
        # Get or create basic security policy
        security = Security.query.first()
        if not security:
            security = Security(tipo='basic', descripcion='Basic security policy')
            db.session.add(security)
            db.session.commit()
        
        # Create slice
        new_slice = Slice(
            nombre=slice_name,
            estado='STOPPED',
            security_idsecurity=security.idsecurity
        )
        
        # Set topology based on type
        if topology_type == 'custom' and topology_data:
            # Custom topology from Vis.js
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
                # Star topology - connect all VMs to VM1
                for i in range(2, num_vms + 1):
                    edges.append({'from': 1, 'to': i})
            elif topology_type == 'tree':
                # Tree topology - hierarchical connections
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
        
        # Create instances based on form data
        for i in range(1, num_vms + 1):
            vm_name = request.form.get(f'vm_{i}_name', f'VM{i}')
            vm_cpu = request.form.get(f'vm_{i}_cpu', '1')
            vm_ram = request.form.get(f'vm_{i}_ram', '1GB')
            vm_storage = request.form.get(f'vm_{i}_storage', '10GB')
            vm_image = request.form.get(f'vm_{i}_image', 'ubuntu:latest')
            
            instance = Instancia(
                slice_idslice=new_slice.idslice,
                nombre=vm_name,
                cpu=vm_cpu,
                ram=vm_ram,
                storage=vm_storage,
                imagen=vm_image
            )
            db.session.add(instance)
        
        db.session.commit()
        flash('Slice created successfully!', 'success')
        return redirect(url_for('dashboard'))
    
    return render_template('create_slice2.html')

@app.route('/slice/<int:slice_id>')
def slice_detail(slice_id):
    """Get slice details as JSON - with role-based access control"""
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
    """View slice topology with Vis.js - with role-based access control"""
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

@app.route('/users')
def list_users():
    """List all users - only for admin users"""
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
    """Start a slice - with role-based access control"""
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
    """Stop a slice - with role-based access control"""
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

@app.route('/delete_slice/<int:slice_id>', methods=['POST'])
def delete_slice(slice_id):
    """Delete a slice - with role-based access control"""
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

@app.route('/download_topology/<int:slice_id>')
def download_topology(slice_id):
    """Download slice topology as JSON - with role-based access control"""
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
    
    return response

# Agregar estas nuevas rutas al final del archivo app.py

@app.route('/edit_slice/<int:slice_id>')
def edit_slice(slice_id):
    """Edit slice page - only for STOPPED slices"""
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
            'imagen': instance.imagen,
            'estado': instance.estado
        })
    
    return render_template('edit_slice.html', 
                         slice=slice_obj, 
                         user=user,
                         current_topology=current_topology,
                         instances_data=instances_data)

@app.route('/update_slice/<int:slice_id>', methods=['POST'])
def update_slice(slice_id):
    """Update slice configuration - with warning message"""
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
        topology_type = request.form.get('topology_type', 'custom')
        num_vms = int(request.form.get('num_vms', len(slice_obj.instancias)))
        
        # Update slice information
        slice_obj.nombre = slice_name
        
        # Update topology if provided
        if topology_data:
            slice_obj.topologia = topology_data
        
        # Delete existing instances
        for instance in slice_obj.instancias:
            db.session.delete(instance)
        
        # Create new instances based on updated form data
        for i in range(1, num_vms + 1):
            vm_name = request.form.get(f'vm_{i}_name', f'VM{i}')
            vm_cpu = request.form.get(f'vm_{i}_cpu', '1')
            vm_ram = request.form.get(f'vm_{i}_ram', '1GB')
            vm_storage = request.form.get(f'vm_{i}_storage', '10GB')
            vm_image = request.form.get(f'vm_{i}_image', 'ubuntu:latest')
            
            instance = Instancia(
                slice_idslice=slice_obj.idslice,
                nombre=vm_name,
                cpu=vm_cpu,
                ram=vm_ram,
                storage=vm_storage,
                imagen=vm_image
            )
            db.session.add(instance)
        
        db.session.commit()
        
        return jsonify({
            'success': True,
            'message': '⚠️ ADVERTENCIA: Los cambios realizados son permanentes. No hay forma de recuperar la configuración anterior del slice.',
            'slice_name': slice_obj.nombre
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