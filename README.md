# CLOUD_GRUPO6

Para instalar y ejecutar el código de este proyecto se necesita contar con Docker Desktop instalado, ya que nuestra arquitectura basada en microservicios se apoya del uso de contenedores.

Para ejecutar todos los módulos (orquestador en general) ejecutamos los siguientes comandos: 
. docker compose build
. docker compose up -d

Estos comandos servirán para levantar los contenedores definidos en el docker-compose.yml que son componentes importantes en el proyecto desarrollado.
IMPORTANTE!
Considerar que la ejecución de estos comandos debe realizarse en la raíz de este proyecto (en el mismo nivel del archivo docker-compose.yml)
