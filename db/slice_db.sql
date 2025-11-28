CREATE DATABASE  IF NOT EXISTS `mydb`;
USE `mydb`;

DROP TABLE IF EXISTS `rol`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `rol` (
  `idrol` int NOT NULL AUTO_INCREMENT,
  `nombre_rol` varchar(45) NOT NULL,
  PRIMARY KEY (`idrol`)
) ENGINE=InnoDB AUTO_INCREMENT=5 DEFAULT CHARSET=utf8mb3;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `rol`
--

LOCK TABLES `rol` WRITE;
/*!40000 ALTER TABLE `rol` DISABLE KEYS */;
INSERT INTO `rol` VALUES (1,'superadmin'),(2,'administrador'),(3,'investigador'),(4,'usuariofinal');
/*!40000 ALTER TABLE `rol` ENABLE KEYS */;
UNLOCK TABLES;

--
-- Table structure for table `usuario`
--

DROP TABLE IF EXISTS `usuario`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `usuario` (
  `idusuario` int NOT NULL AUTO_INCREMENT,
  `nombre` varchar(45) DEFAULT NULL,
  `contrasenia` varchar(128) DEFAULT NULL,
  `rol_idrol` int NOT NULL,
  PRIMARY KEY (`idusuario`,`rol_idrol`),
  KEY `fk_usuario_rol1_idx` (`rol_idrol`),
  CONSTRAINT `fk_usuario_rol1` FOREIGN KEY (`rol_idrol`) REFERENCES `rol` (`idrol`)
) ENGINE=InnoDB AUTO_INCREMENT=5 DEFAULT CHARSET=utf8mb3;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `usuario`
--

LOCK TABLES `usuario` WRITE;
/*!40000 ALTER TABLE `usuario` DISABLE KEYS */;
INSERT INTO `usuario` VALUES (1,'admin','$2a$13$hDsl2kC2dMYEuV02CoeiyuZd1SWPx4N0gM4QghCuJb7TDs0uaSgne', 1), (2,'daniel','$2a$13$hDsl2kC2dMYEuV02CoeiyuZd1SWPx4N0gM4QghCuJb7TDs0uaSgne', 2), (3,'bala','$2a$13$hDsl2kC2dMYEuV02CoeiyuZd1SWPx4N0gM4QghCuJb7TDs0uaSgne', 3), (4,'ricardo','$2a$13$hDsl2kC2dMYEuV02CoeiyuZd1SWPx4N0gM4QghCuJb7TDs0uaSgne', 4);
UNLOCK TABLES;

--
-- Table structure for table `imagen`
--

DROP TABLE IF EXISTS `imagen`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `imagen` (
  `idimagen` int NOT NULL AUTO_INCREMENT,
  `ruta` varchar(225) DEFAULT NULL,
  `nombre` varchar(45) DEFAULT NULL,
  `id_openstack` varchar(64) DEFAULT NULL,   -- nuevo campo agregado
  PRIMARY KEY (`idimagen`)
) ENGINE=InnoDB AUTO_INCREMENT=2 DEFAULT CHARSET=utf8mb3;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `imagen`
--

LOCK TABLES `imagen` WRITE;
/*!40000 ALTER TABLE `imagen` DISABLE KEYS */;
INSERT INTO `imagen` VALUES 
(1,'/var/lib/qemu-images/image-base/ubuntu.qcow2','ubuntu:latest', '56b9c357-4045-41b8-89f1-2d78e6ba7e64'),
(2,'/var/lib/qemu-images/image-base/cirros-base.qcow2','cirros:latest', 'ad11fa04-b020-41f6-9cc3-7f7a589c6a2a'),
(3,'/var/lib/qemu-images/image-base/debian-cloud.qcow2','debian-cloud:latest', 'oli');
/*!40000 ALTER TABLE `imagen` ENABLE KEYS */;
UNLOCK TABLES;

--
-- Table structure for table `vnc`
--

DROP TABLE IF EXISTS `vnc`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `vnc` (
  `idvnc` int NOT NULL AUTO_INCREMENT,
  `puerto` varchar(45) DEFAULT NULL,
  `estado` varchar(45) DEFAULT NULL,
  PRIMARY KEY (`idvnc`)
) ENGINE=InnoDB AUTO_INCREMENT=21 DEFAULT CHARSET=utf8mb3;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `vnc`
--

LOCK TABLES `vnc` WRITE;
/*!40000 ALTER TABLE `vnc` DISABLE KEYS */;
INSERT INTO `vnc` VALUES (1,'1','disponible'),(2,'2','disponible'),(3,'3','disponible'),(4,'4','disponible'),(5,'5','disponible'),(6,'6','disponible'),(7,'7','disponible'),(8,'8','disponible'),(9,'9','disponible'),(10,'10','disponible'),(11,'11','disponible'),(12,'12','disponible'),(13,'13','disponible'),(14,'14','disponible'),(15,'15','disponible'),(16,'16','disponible'),(17,'17','disponible'),(18,'18','disponible'),(19,'19','disponible'),(20,'20','disponible');
/*!40000 ALTER TABLE `vnc` ENABLE KEYS */;
UNLOCK TABLES;

--
-- Table structure for table `worker`
--

DROP TABLE IF EXISTS `worker`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `worker` (
  `idworker` int NOT NULL AUTO_INCREMENT,
  `nombre` varchar(45) DEFAULT NULL,
  `ip` varchar(45) DEFAULT NULL,
  `cpu` varchar(45) DEFAULT NULL,
  `ram` varchar(45) DEFAULT NULL,
  `storage` varchar(45) DEFAULT NULL,
  PRIMARY KEY (`idworker`)
) ENGINE=InnoDB AUTO_INCREMENT=1 DEFAULT CHARSET=utf8mb3;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `worker`
--

LOCK TABLES `worker` WRITE;
/*!40000 ALTER TABLE `worker` DISABLE KEYS */;
INSERT INTO worker (nombre, ip, cpu, ram, storage) VALUES
('server2', '192.168.201.2', '4', '8GB', '100GB'),
('server3', '192.168.201.3', '4', '8GB', '100GB'),
('server4', '192.168.201.4', '4', '8GB', '100GB'),
('worker1', '192.168.202.2', '4', '8GB', '100GB'),
('worker2', '192.168.202.3', '4', '8GB', '100GB'),
('worker3', '192.168.202.4', '4', '8GB', '100GB');
/*!40000 ALTER TABLE `worker` ENABLE KEYS */;
UNLOCK TABLES;

--
-- Table structure for table `slice`
--

DROP TABLE IF EXISTS `slice`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `slice` (
  `idslice` int NOT NULL AUTO_INCREMENT,
  `nombre` varchar(100) DEFAULT NULL,
  `estado` varchar(45) DEFAULT NULL,
  `topologia` text,
  `fecha_creacion` date DEFAULT NULL,
  `fecha_upload` date DEFAULT NULL,
  `zonadisponibilidad` varchar(45) DEFAULT NULL,
  `platform` varchar(20) DEFAULT 'linux' COMMENT 'Plataforma: linux | openstack',
  PRIMARY KEY (`idslice`)
) ENGINE=InnoDB AUTO_INCREMENT=20 DEFAULT CHARSET=utf8mb3;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `slice`
--

LOCK TABLES `slice` WRITE;
/*!40000 ALTER TABLE `slice` DISABLE KEYS */;
INSERT INTO `slice` VALUES (19,'oli','STOPPED','{\"nodes\":[{\"id\":1,\"label\":\"VM1\",\"x\":100,\"y\":0},{\"id\":2,\"label\":\"VM2\",\"x\":-49.99999999999998,\"y\":86.60254037844388},{\"id\":3,\"label\":\"VM3\",\"x\":-50.00000000000004,\"y\":-86.60254037844383}],\"edges\":[{\"from\":1,\"to\":2,\"id\":\"f50e0b85-95e6-44bd-b6ea-9b9c7be57668\"},{\"from\":1,\"to\":3,\"id\":\"0689e997-4c3b-4a12-8def-26f5a3a3fed1\"},{\"from\":2,\"to\":3,\"id\":\"a43918b0-7509-45e3-aa16-a08e25af5749\"}]}','2025-10-12',NULL,NULL,'default');
/*!40000 ALTER TABLE `slice` ENABLE KEYS */;
UNLOCK TABLES;

--
-- Table structure for table `instancia`
--

DROP TABLE IF EXISTS `instancia`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `instancia` (
  `idinstancia` int NOT NULL AUTO_INCREMENT,
  `slice_idslice` int NOT NULL,
  `nombre` varchar(100) DEFAULT NULL,
  `estado` varchar(45) DEFAULT NULL,
  `cpu` varchar(45) DEFAULT NULL,
  `ram` varchar(45) DEFAULT NULL,
  `storage` varchar(45) DEFAULT NULL,
  `salidainternet` tinyint DEFAULT NULL,
  `imagen_idimagen` int NOT NULL,
  `ip` varchar(45) DEFAULT NULL,
  `vnc_idvnc` int DEFAULT NULL,
  `worker_idworker` int DEFAULT NULL,
  `process_id` int DEFAULT NULL,
  `platform` varchar(20) DEFAULT 'linux' COMMENT 'Plataforma donde se despliega: linux | openstack',
  `instance_id` varchar(100) DEFAULT NULL COMMENT 'UUID de la instancia en OpenStack (solo para platform=openstack)',
  `console_url` varchar(500) DEFAULT NULL COMMENT 'URL de consola VNC/noVNC para acceso remoto',
  
  PRIMARY KEY (`idinstancia`,`slice_idslice`),
  KEY `fk_instancia_slice1_idx` (`slice_idslice`),
  KEY `fk_instancia_imagen1_idx` (`imagen_idimagen`),
  KEY `fk_instancia_vnc1_idx` (`vnc_idvnc`),
  KEY `fk_instancia_worker1_idx` (`worker_idworker`),

  CONSTRAINT `fk_instancia_imagen1` FOREIGN KEY (`imagen_idimagen`) REFERENCES `imagen` (`idimagen`),
  CONSTRAINT `fk_instancia_slice1` FOREIGN KEY (`slice_idslice`) REFERENCES `slice` (`idslice`),
  CONSTRAINT `fk_instancia_vnc1` FOREIGN KEY (`vnc_idvnc`) REFERENCES `vnc` (`idvnc`),
  CONSTRAINT `fk_instancia_worker1` FOREIGN KEY (`worker_idworker`) REFERENCES `worker` (`idworker`)
) ENGINE=InnoDB AUTO_INCREMENT=4 DEFAULT CHARSET=utf8mb3;

/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `instancia`
--

LOCK TABLES `instancia` WRITE;
/*!40000 ALTER TABLE `instancia` DISABLE KEYS */;
INSERT INTO `instancia` VALUES
(1,19,'VM1','STOPPED','1','1GB','10GB',0,1,NULL,NULL,NULL,NULL,'linux',NULL, NULL),
(2,19,'VM2','STOPPED','1','1GB','10GB',0,1,NULL,NULL,NULL,NULL,'linux',NULL, NULL),
(3,19,'VM3','STOPPED','1','1GB','10GB',0,1,NULL,NULL,NULL,NULL,'linux',NULL, NULL);
/*!40000 ALTER TABLE `instancia` ENABLE KEYS */;
UNLOCK TABLES;

--
-- Table structure for table `usuario_has_slice`
--

DROP TABLE IF EXISTS `usuario_has_slice`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `usuario_has_slice` (
  `usuario_idusuario` int NOT NULL,
  `slice_idslice` int NOT NULL,
  PRIMARY KEY (`usuario_idusuario`,`slice_idslice`),
  KEY `fk_usuario_has_slice_slice1_idx` (`slice_idslice`),
  KEY `fk_usuario_has_slice_usuario1_idx` (`usuario_idusuario`),
  CONSTRAINT `fk_usuario_has_slice_slice1` FOREIGN KEY (`slice_idslice`) REFERENCES `slice` (`idslice`),
  CONSTRAINT `fk_usuario_has_slice_usuario1` FOREIGN KEY (`usuario_idusuario`) REFERENCES `usuario` (`idusuario`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb3;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `usuario_has_slice`
--

LOCK TABLES `usuario_has_slice` WRITE;
/*!40000 ALTER TABLE `usuario_has_slice` DISABLE KEYS */;
INSERT INTO `usuario_has_slice` VALUES (1,19);
/*!40000 ALTER TABLE `usuario_has_slice` ENABLE KEYS */;
UNLOCK TABLES;

--
-- Table structure for table `vlan`
--


CREATE TABLE `vlan` (
  `idvlan` int NOT NULL AUTO_INCREMENT,
  `numero` varchar(45) DEFAULT NULL,
  `estado` varchar(45) DEFAULT NULL,
  PRIMARY KEY (`idvlan`)
) ENGINE=InnoDB AUTO_INCREMENT=12 DEFAULT CHARSET=utf8mb4;
/*!40101 SET character_set_client = @saved_cs_client */;

-- 
-- Dumping data for table `vlan`
--

LOCK TABLES `vlan` WRITE;
/*!40000 ALTER TABLE `vlan` DISABLE KEYS */;

INSERT INTO `vlan` VALUES (1,'100','ocupada'),(2,'101','ocupada'),(3,'102','ocupada'),(4,'103','ocupada'),(5,'104','disponible'),(6,'105','disponible'),(7,'106','disponible'),(8,'107','disponible'),(9,'108','disponible'),(10,'109','disponible'),(11,'110','disponible'),(12,'11','reservada');
/*!40000 ALTER TABLE `vlan` ENABLE KEYS */;
UNLOCK TABLES;

--
-- Table structure for table `enlace`
--

DROP TABLE IF EXISTS `enlace`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `enlace` (
  `idenlace` int NOT NULL AUTO_INCREMENT,
  `vm1` varchar(45) DEFAULT NULL,           -- ID de la primera VM
  `vm2` varchar(45) DEFAULT NULL,           -- ID de la segunda VM  
  `vlan` varchar(45) DEFAULT NULL,          -- Número de VLAN (puede ser NULL)
  `vlan_idvlan` int DEFAULT NULL,           -- 🟢 CAMBIADO: Ahora puede ser NULL
  `slice_idslice` int NOT NULL,             -- ID del slice (obligatorio)
  PRIMARY KEY (`idenlace`),
  KEY `fk_enlace_vlan1_idx` (`vlan_idvlan`),
  KEY `fk_enlace_slice1_idx` (`slice_idslice`),
  CONSTRAINT `fk_enlace_slice1` FOREIGN KEY (`slice_idslice`) REFERENCES `slice` (`idslice`),
  CONSTRAINT `fk_enlace_vlan1` FOREIGN KEY (`vlan_idvlan`) REFERENCES `vlan` (`idvlan`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb3;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `enlace`
--

LOCK TABLES `enlace` WRITE;
INSERT INTO `enlace` VALUES (1,1,2,NULL,NULL,19),(2,2,3,NULL,NULL,19),(3,3,1,NULL,NULL,19);
UNLOCK TABLES;

-- Table structure for table `interfaces_tap`

DROP TABLE IF EXISTS `interfaces_tap`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `interfaces_tap` (
  `id_tap` int NOT NULL AUTO_INCREMENT,
  `nombre_interfaz` varchar(45) NOT NULL,
  `instancia_idinstancia` int NOT NULL,
  `worker_idworker` int NOT NULL,
  PRIMARY KEY (`id_tap`),
  KEY `fk_interfaces_tap_instancia1_idx` (`instancia_idinstancia`),
  KEY `fk_interfaces_tap_worker1_idx` (`worker_idworker`),
  CONSTRAINT `fk_interfaces_tap_instancia1` FOREIGN KEY (`instancia_idinstancia`) REFERENCES `instancia` (`idinstancia`),
  CONSTRAINT `fk_interfaces_tap_worker1` FOREIGN KEY (`worker_idworker`) REFERENCES `worker` (`idworker`)
) ENGINE=InnoDB AUTO_INCREMENT=1 DEFAULT CHARSET=utf8mb3;
/*!40101 SET character_set_client = @saved_cs_client */;

-- Dump completed on 2025-10-12  7:01:41