# VNRT - Sistema de Gestión de Slices

Una arquitectura web mínima para la administración de slices en una nube privada.

## Características

- **Backend**: Flask con autenticación básica y manejo de sesiones
- **Base de datos**: SQLite con SQLAlchemy para usuarios y slices
- **Frontend**: Interfaz web responsiva con Bootstrap
- **Funcionalidades**: Login, dashboard, visualización de slices y detalles

## Estructura del Proyecto

```
/
├── app.py              # Aplicación principal Flask
├── models.py           # Modelos SQLAlchemy (User, Slice)
├── requirements.txt    # Dependencias Python
├── templates/          # Plantillas HTML
│   ├── login.html      # Página de login
│   └── dashboard.html  # Dashboard principal
└── static/            # Archivos estáticos
    ├── css/           # Estilos CSS
    │   ├── login.css
    │   └── dashboard.css
    └── js/            # JavaScript
        └── dashboard.js
```

## Instalación y Ejecución

1. **Instalar dependencias**:
   ```bash
   pip install -r requirements.txt
   ```

2. **Ejecutar la aplicación**:
   ```bash
   python app.py
   ```

3. **Acceder a la aplicación**:
   - URL: http://localhost:5000
   - Usuario de prueba: `admin`
   - Contraseña: `admin123`

## Funcionalidades

### Autenticación
- Login con usuario y contraseña
- Manejo de sesiones seguras
- Logout con limpieza de sesión

### Dashboard
- Tabla de slices del usuario autenticado
- Estados visuales (RUNNING/STOPPED)
- Selección de slice para ver detalles
- Información detallada del slice seleccionado

### Base de Datos
- Usuario de prueba preconfigurado
- 3 slices de ejemplo con diferentes estados
- Estructura relacional entre usuarios y slices

## Usuario de Prueba

- **Usuario**: admin
- **Contraseña**: admin123

## Datos de Ejemplo

El sistema incluye 3 slices de prueba:
- TEL141_2025-2_20206466 (RUNNING)
- TEL142_2025-2_20206467 (STOPPED)
- TEL143_2025-2_20206468 (RUNNING)

## Tecnologías Utilizadas

- Python 3.x
- Flask 2.3.3
- SQLAlchemy 3.0.5
- SQLite
- Bootstrap 5.3.0
- Font Awesome 6.4.0