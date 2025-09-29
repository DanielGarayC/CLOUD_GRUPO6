from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime
import json

db = SQLAlchemy()

class Security(db.Model):
    __tablename__ = 'security'
    
    idsecurity = db.Column('idsecurity', db.Integer, primary_key=True)
    tipo = db.Column(db.String(45))
    descripcion = db.Column(db.String(45))
    
    # Alias for easier access
    @property
    def id(self):
        return self.idsecurity
    
    def __repr__(self):
        return f'<Security {self.tipo}>'

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
    nombre = db.Column(db.String(100))  # Add slice name field
    estado = db.Column(db.String(45), default='STOPPED')
    topologia = db.Column(db.Text)  # Keep as TEXT for JSON storage
    fecha_creacion = db.Column(db.Date, default=datetime.utcnow)
    fecha_upload = db.Column(db.Date)
    security_idsecurity = db.Column('security_idsecurity', db.Integer, db.ForeignKey('security.idsecurity'), nullable=False)
    
    # Relationships
    security = db.relationship('Security', backref='slices', foreign_keys=[security_idsecurity])
    instancias = db.relationship('Instancia', backref='slice', lazy=True, cascade='all, delete-orphan', foreign_keys='Instancia.slice_idslice')
    
    # Many-to-many relationship with users
    usuarios = db.relationship('User', secondary='usuario_has_slice', backref='slices')
    
    # Aliases for easier access
    @property
    def id(self):
        return self.idslice
    
    @property
    def security_id(self):
        return self.security_idsecurity
    
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

class Instancia(db.Model):
    __tablename__ = 'instancia'
    
    idinstancia = db.Column('idinstancia', db.Integer, primary_key=True)
    slice_idslice = db.Column('slice_idslice', db.Integer, db.ForeignKey('slice.idslice'), nullable=False)
    nombre = db.Column(db.String(100), nullable=False)  # Add nombre field
    estado = db.Column(db.String(45), default='STOPPED')
    cpu = db.Column(db.String(45))
    ram = db.Column(db.String(45))
    storage = db.Column(db.String(45))
    imagen = db.Column(db.String(100))  # Add imagen field
    
    # Relationships
    interfaces = db.relationship('Interfaz', backref='instancia', lazy=True, cascade='all, delete-orphan', foreign_keys='Interfaz.instancia_idinstancia')
    
    # Aliases for easier access
    @property
    def id(self):
        return self.idinstancia
    
    @property
    def slice_id(self):
        return self.slice_idslice
    
    def __repr__(self):
        return f'<Instancia {self.nombre}>'

class Interfaz(db.Model):
    __tablename__ = 'interfaz'
    
    idinterfaz = db.Column('idinterfaz', db.Integer, primary_key=True)
    nombre_interfaz = db.Column(db.String(45))
    instancia_idinstancia = db.Column('instancia_idinstancia', db.Integer, db.ForeignKey('instancia.idinstancia'), nullable=False)
    instancia_slice_idslice = db.Column('instancia_slice_idslice', db.Integer, db.ForeignKey('slice.idslice'), nullable=False)
    
    # Aliases for easier access
    @property
    def id(self):
        return self.idinterfaz
    
    @property
    def instancia_id(self):
        return self.instancia_idinstancia
    
    def __repr__(self):
        return f'<Interfaz {self.nombre_interfaz}>'

# Association table for many-to-many relationship between users and slices
usuario_has_slice = db.Table('usuario_has_slice',
    db.Column('usuario_idusuario', db.Integer, db.ForeignKey('usuario.idusuario'), primary_key=True),
    db.Column('slice_idslice', db.Integer, db.ForeignKey('slice.idslice'), primary_key=True)
)