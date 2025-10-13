from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import generate_password_hash, check_password_hash
import json
from datetime import datetime

db = SQLAlchemy()

class Rol(db.Model):
    __tablename__ = 'rol'
    
    idrol = db.Column('idrol', db.Integer, primary_key=True)
    nombre_rol = db.Column(db.String(45), nullable=False)
    
    @property
    def id(self):
        return self.idrol
    
    def __repr__(self):
        return f'<Rol {self.nombre_rol}>'

class User(db.Model):
    __tablename__ = 'usuario'
    
    idusuario = db.Column('idusuario', db.Integer, primary_key=True)
    nombre = db.Column(db.String(45))
    contrasenia = db.Column(db.String(128))
    rol_idrol = db.Column('rol_idrol', db.Integer, db.ForeignKey('rol.idrol'), nullable=False)
    
    # Relationships
    rol = db.relationship('Rol', backref='usuarios', foreign_keys=[rol_idrol])
    
    # Many-to-many relationship with slices
    slices = db.relationship('Slice', secondary='usuario_has_slice', back_populates='usuarios')
    
    @property
    def id(self):
        return self.idusuario
    
    def set_password(self, password):
        self.contrasenia = generate_password_hash(password)
    
    def check_password(self, password):
        return check_password_hash(self.contrasenia, password)
    
    def __repr__(self):
        return f'<User {self.nombre}>'

class Imagen(db.Model):
    __tablename__ = 'imagen'
    
    idimagen = db.Column('idimagen', db.Integer, primary_key=True)
    ruta = db.Column(db.String(45))
    nombre = db.Column(db.String(45))
    
    @property
    def id(self):
        return self.idimagen
    
    def __repr__(self):
        return f'<Imagen {self.nombre}>'

class Vnc(db.Model):
    __tablename__ = 'vnc'
    
    idvnc = db.Column('idvnc', db.Integer, primary_key=True)
    puerto = db.Column(db.String(45))
    estado = db.Column(db.String(45))
    
    @property
    def id(self):
        return self.idvnc
    
    def __repr__(self):
        return f'<Vnc {self.puerto}>'

class Worker(db.Model):
    __tablename__ = 'worker'
    
    idworker = db.Column('idworker', db.Integer, primary_key=True)
    nombre = db.Column(db.String(45))
    ip = db.Column(db.String(45))  # 🟢 ACTUALIZADO: Cambiado de 'puerto' a 'ip'
    cpu = db.Column(db.String(45))
    ram = db.Column(db.String(45))
    storage = db.Column(db.String(45))
    
    @property
    def id(self):
        return self.idworker
    
    def __repr__(self):
        return f'<Worker {self.nombre}>'

class Slice(db.Model):
    __tablename__ = 'slice'
    
    idslice = db.Column('idslice', db.Integer, primary_key=True)
    nombre = db.Column(db.String(100))
    estado = db.Column(db.String(45))
    topologia = db.Column(db.Text)
    fecha_creacion = db.Column(db.Date)
    fecha_upload = db.Column(db.Date)
    zonadisponibilidad = db.Column(db.String(45))
    
    # Relationships
    instancias = db.relationship('Instancia', backref='slice', cascade='all, delete-orphan')
    enlaces = db.relationship('Enlace', backref='slice', cascade='all, delete-orphan')  # 🟢 NUEVO
    
    # Many-to-many relationship with users
    usuarios = db.relationship('User', secondary='usuario_has_slice', back_populates='slices')
    
    @property
    def id(self):
        return self.idslice
    
    def set_topology_data(self, topology_dict):
        """Store topology as JSON string"""
        self.topologia = json.dumps(topology_dict)
    
    def get_topology_data(self):
        """Retrieve topology as Python dict"""
        if self.topologia:
            try:
                return json.loads(self.topologia)
            except json.JSONDecodeError:
                return {'nodes': [], 'edges': []}
        return {'nodes': [], 'edges': []}
    
    def __repr__(self):
        return f'<Slice {self.nombre}>'

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

class Vlan(db.Model):
    __tablename__ = 'vlan'
    
    idvlan = db.Column('idvlan', db.Integer, primary_key=True)
    numero = db.Column(db.String(45))
    estado = db.Column(db.String(45))
    
    @property
    def id(self):
        return self.idvlan
    
    @classmethod
    def get_available_vlan(cls):
        """Get the next available VLAN"""
        return cls.query.filter_by(estado='disponible').first()
    
    @classmethod
    def get_available_vlans_count(cls):
        """Count available VLANs"""
        return cls.query.filter_by(estado='disponible').count()
    
    def reserve(self):
        """Mark VLAN as occupied"""
        self.estado = 'ocupada'
        db.session.commit()
    
    def release(self):
        """Mark VLAN as available"""
        self.estado = 'disponible'
        db.session.commit()
    
    def __repr__(self):
        return f'<Vlan {self.numero} ({self.estado})>'

# 🟢 MODELO ENLACE ACTUALIZADO
class Enlace(db.Model):
    __tablename__ = 'enlace'
    
    idenlace = db.Column('idenlace', db.Integer, primary_key=True)
    vm1 = db.Column(db.String(45))
    vm2 = db.Column(db.String(45))
    vlan = db.Column(db.String(45))  # Número de VLAN como string para acceso rápido
    vlan_idvlan = db.Column('vlan_idvlan', db.Integer, db.ForeignKey('vlan.idvlan'), nullable=False)
    slice_idslice = db.Column('slice_idslice', db.Integer, db.ForeignKey('slice.idslice'), nullable=False)
    
    # Relationships
    vlan_obj = db.relationship('Vlan', backref='enlaces', foreign_keys=[vlan_idvlan])
    # slice relationship is defined in Slice model
    
    @property
    def id(self):
        return self.idenlace
    
    @classmethod
    def create_link(cls, vm1, vm2, slice_id):
        """Create a new link between two VMs, automatically assigning a VLAN"""
        # Get available VLAN
        available_vlan = Vlan.get_available_vlan()
        if not available_vlan:
            raise ValueError("No hay VLANs disponibles para crear el enlace")
        
        # Create the link
        enlace = cls(
            vm1=vm1,
            vm2=vm2,
            vlan=available_vlan.numero,
            vlan_idvlan=available_vlan.idvlan,
            slice_idslice=slice_id
        )
        
        # Reserve the VLAN
        available_vlan.reserve()
        
        db.session.add(enlace)
        return enlace
    
    def delete_link(self):
        """Delete link and release its VLAN"""
        # Release the VLAN
        if self.vlan_obj:
            self.vlan_obj.release()
        
        # Delete the link
        db.session.delete(self)
    
    def __repr__(self):
        return f'<Enlace {self.vm1}-{self.vm2} VLAN:{self.vlan}>'

# Association table for many-to-many relationship between users and slices
usuario_has_slice = db.Table('usuario_has_slice',
    db.Column('usuario_idusuario', db.Integer, db.ForeignKey('usuario.idusuario'), primary_key=True),
    db.Column('slice_idslice', db.Integer, db.ForeignKey('slice.idslice'), primary_key=True)
)