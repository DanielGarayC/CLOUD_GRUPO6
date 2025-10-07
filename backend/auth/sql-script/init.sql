
CREATE DATABASE IF NOT EXISTS auth_db CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
USE auth_db;


CREATE TABLE IF NOT EXISTS rol (
  idrol INT AUTO_INCREMENT PRIMARY KEY,
  nombreRol VARCHAR(50) NOT NULL
);

CREATE TABLE IF NOT EXISTS usuario (
  idusuario INT AUTO_INCREMENT PRIMARY KEY,
  nombre VARCHAR(100) NOT NULL UNIQUE,
  contrasenha VARCHAR(255) NOT NULL,
  rol_idrol INT NOT NULL,
  FOREIGN KEY (rol_idrol) REFERENCES rol(idrol)
);

INSERT INTO rol (nombreRol) VALUES ('admin'), ('user');


INSERT INTO usuario (nombre, contrasenha, rol_idrol)
VALUES ('admin', '$2a$13$hDsl2kC2dMYEuV02CoeiyuZd1SWPx4N0gM4QghCuJb7TDs0uaSgne', 1);
