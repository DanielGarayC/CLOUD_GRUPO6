from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime
import json

db = SQLAlchemy()

class Rol(db.Model):
    __tablename__ = 'rol'
    
    idrol = db.Column('idrol', db.Integer, primary_key=True)
    nombre_rol = db.Column(db.String(45), nullable=False)
    
    # Alias for easier access
    @property
    def id(self):
        return self.idrol
    
    def __repr__(self):
        return f'<Rol {self.nombre_rol}>'

class User(db.Model):
    __tablename__ = 'usuario'
    
    idusuario = db.Column('idusuario', db.Integer, primary_key=True)
    nombre = db.Column(db.String(45), unique=True, nullable=False)
    contrasenia = db.Column(db.String(128), nullable=False)
    rol_idrol = db.Column('rol_idrol', db.Integer, db.ForeignKey('rol.idrol'), nullable=False)
    
    # Relationships
    rol = db.relationship('Rol', backref='usuarios', foreign_keys=[rol_idrol])
    
    # Aliases for easier access
    @property
    def id(self):
        return self.idusuario
    
    @property 
    def rol_id(self):
        return self.rol_idrol
    
    def set_password(self, password):
        """Set password in plain text (temporary - for development only)"""
        self.contrasenia = password
    
    def check_password(self, password):
        """Check password against plain text stored password"""
        # For now, compare directly without hashing
        return self.contrasenia == password
    
    def set_password_hashed(self, password):
        """Set password with hash (for future use when migrating to hashed passwords)"""
        self.contrasenia = generate_password_hash(password)
    
    def check_password_hashed(self, password):
        """Check password against hashed password (for future use)"""
        return check_password_hash(self.contrasenia, password)
    
    def __repr__(self):
        return f'<User {self.nombre}>'

class Slice(db.Model):
    __tablename__ = 'slice'
    
    idslice = db.Column('idslice', db.Integer, primary_key=True)
    nombre = db.Column(db.String(100))
    estado = db.Column(db.String(45), default='STOPPED')
    topologia = db.Column(db.Text)
    fecha_creacion = db.Column(db.Date, default=datetime.utcnow)
    fecha_upload = db.Column(db.Date)
    zonadisponibilidad = db.Column(db.String(45))
    
    # Relationships
    instancias = db.relationship('Instancia', backref='slice', lazy=True, cascade='all, delete-orphan', foreign_keys='Instancia.slice_idslice')
    
    # Many-to-many relationship with users
    usuarios = db.relationship('User', secondary='usuario_has_slice', backref='slices')
    
    # Aliases for easier access
    @property
    def id(self):
        return self.idslice
    
    def get_topology_data(self):
        """Parse topology JSON data"""
        if self.topologia:
            try:
                return json.loads(self.topologia)
            except json.JSONDecodeError:
                return None
        return None
    
    def set_topology_data(self, data):
        """Set topology as JSON string"""
        if data:
            self.topologia = json.dumps(data)
        else:
            self.topologia = None
    
    def __repr__(self):
        return f'<Slice {self.nombre or self.idslice}>'

class Imagen(db.Model):
    __tablename__ = 'imagen'
    
    idimagen = db.Column('idimagen', db.Integer, primary_key=True)
    ruta = db.Column(db.String(45))
    nombre = db.Column(db.String(45))
    
    # Aliases for easier access
    @property
    def id(self):
        return self.idimagen
    
    def __repr__(self):
        return f'<Imagen {self.nombre}>'

class Vnc(db.Model):
    __tablename__ = 'vnc'
    
    idvnc = db.Column('idvnc', db.Integer, primary_key=True)
    puerto = db.Column(db.String(45))
    
    # Aliases for easier access
    @property
    def id(self):
        return self.idvnc
    
    def __repr__(self):
        return f'<Vnc {self.puerto}>'

class Worker(db.Model):
    __tablename__ = 'worker'
    
    idworker = db.Column('idworker', db.Integer, primary_key=True)
    nombre = db.Column(db.String(45))
    puerto = db.Column(db.String(45))
    cpu = db.Column(db.String(45))
    ram = db.Column(db.String(45))
    storage = db.Column(db.String(45))
    
    # Aliases for easier access
    @property
    def id(self):
        return self.idworker
    
    def __repr__(self):
        return f'<Worker {self.nombre}>'

class Instancia(db.Model):
    __tablename__ = 'instancia'
    
    idinstancia = db.Column('idinstancia', db.Integer, primary_key=True)
    slice_idslice = db.Column('slice_idslice', db.Integer, db.ForeignKey('slice.idslice'), nullable=False)
    nombre = db.Column(db.String(100), nullable=False)
    estado = db.Column(db.String(45), default='STOPPED')
    cpu = db.Column(db.String(45))
    ram = db.Column(db.String(45))
    storage = db.Column(db.String(45))
    salidainternet = db.Column(db.Boolean, default=False)
    imagen_idimagen = db.Column('imagen_idimagen', db.Integer, db.ForeignKey('imagen.idimagen'), nullable=False)
    ip = db.Column(db.String(45))
    vnc_idvnc = db.Column('vnc_idvnc', db.Integer, db.ForeignKey('vnc.idvnc'), nullable=True)
    worker_idworker = db.Column('worker_idworker', db.Integer, db.ForeignKey('worker.idworker'), nullable=True)
    
    # Relationships
    imagen = db.relationship('Imagen', backref='instancias', foreign_keys=[imagen_idimagen])
    vnc = db.relationship('Vnc', backref='instancias', foreign_keys=[vnc_idvnc])
    worker = db.relationship('Worker', backref='instancias', foreign_keys=[worker_idworker])
    
    # Aliases for easier access
    @property
    def id(self):
        return self.idinstancia
    
    @property
    def slice_id(self):
        return self.slice_idslice
    
    @property
    def imagen_id(self):
        return self.imagen_idimagen
    
    @property
    def vnc_id(self):
        return self.vnc_idvnc
    
    @property
    def worker_id(self):
        return self.worker_idworker
    
    def __repr__(self):
        return f'<Instancia {self.nombre}>'

class Enlace(db.Model):
    __tablename__ = 'enlace'
    
    idenlace = db.Column('idenlace', db.Integer, primary_key=True)
    vm1 = db.Column(db.String(45))
    vm2 = db.Column(db.String(45))
    vlan = db.Column(db.String(45))
    
    # Aliases for easier access
    @property
    def id(self):
        return self.idenlace
    
    def __repr__(self):
        return f'<Enlace {self.vm1}-{self.vm2}>'

class Vlan(db.Model):
    __tablename__ = 'vlan'
    
    idvlan = db.Column('idvlan', db.Integer, primary_key=True)
    numero = db.Column(db.String(45))
    estado = db.Column(db.String(45))
    
    # Aliases for easier access
    @property
    def id(self):
        return self.idvlan
    
    def __repr__(self):
        return f'<Vlan {self.numero}>'

# Association table for many-to-many relationship between users and slices
usuario_has_slice = db.Table('usuario_has_slice',
    db.Column('usuario_idusuario', db.Integer, db.ForeignKey('usuario.idusuario'), primary_key=True),
    db.Column('slice_idslice', db.Integer, db.ForeignKey('slice.idslice'), primary_key=True)
)