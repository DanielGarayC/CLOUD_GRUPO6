CREATE DATABASE  IF NOT EXISTS `mydb` /*!40100 DEFAULT CHARACTER SET utf8mb3 */ /*!80016 DEFAULT ENCRYPTION='N' */;
USE `mydb`;
-- MySQL dump 10.13  Distrib 8.0.36, for Win64 (x86_64)
--
-- Host: localhost    Database: mydb
-- ------------------------------------------------------
-- Server version	8.0.36

/*!40101 SET @OLD_CHARACTER_SET_CLIENT=@@CHARACTER_SET_CLIENT */;
/*!40101 SET @OLD_CHARACTER_SET_RESULTS=@@CHARACTER_SET_RESULTS */;
/*!40101 SET @OLD_COLLATION_CONNECTION=@@COLLATION_CONNECTION */;
/*!50503 SET NAMES utf8 */;
/*!40103 SET @OLD_TIME_ZONE=@@TIME_ZONE */;
/*!40103 SET TIME_ZONE='+00:00' */;
/*!40014 SET @OLD_UNIQUE_CHECKS=@@UNIQUE_CHECKS, UNIQUE_CHECKS=0 */;
/*!40014 SET @OLD_FOREIGN_KEY_CHECKS=@@FOREIGN_KEY_CHECKS, FOREIGN_KEY_CHECKS=0 */;
/*!40101 SET @OLD_SQL_MODE=@@SQL_MODE, SQL_MODE='NO_AUTO_VALUE_ON_ZERO' */;
/*!40111 SET @OLD_SQL_NOTES=@@SQL_NOTES, SQL_NOTES=0 */;

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
  `imagen` varchar(100) DEFAULT NULL,
  PRIMARY KEY (`idinstancia`,`slice_idslice`),
  KEY `fk_instancia_slice1_idx` (`slice_idslice`),
  CONSTRAINT `fk_instancia_slice1` FOREIGN KEY (`slice_idslice`) REFERENCES `slice` (`idslice`)
) ENGINE=InnoDB AUTO_INCREMENT=37 DEFAULT CHARSET=utf8mb3;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `instancia`
--

LOCK TABLES `instancia` WRITE;
/*!40000 ALTER TABLE `instancia` DISABLE KEYS */;
INSERT INTO `instancia` VALUES (1,3,'VM1','STOPPED','1','1GB','10GB','ubuntu:latest'),(2,3,'VM2','STOPPED','1','1GB','10GB','ubuntu:latest'),(3,4,'VM1','STOPPED','1','1GB','10GB','ubuntu:latest'),(4,4,'VM2','STOPPED','1','1GB','10GB','ubuntu:latest'),(5,4,'VM3','STOPPED','1','1GB','10GB','ubuntu:latest'),(6,5,'VM1','STOPPED','1','1GB','10GB','ubuntu:latest'),(7,5,'VM2','STOPPED','1','1GB','10GB','ubuntu:latest'),(8,6,'VM1','STOPPED','1','1GB','10GB','centos:latest'),(9,6,'VM2','STOPPED','1','1GB','10GB','debian:latest'),(10,7,'VM1','STOPPED','1','1GB','10GB','debian:latest'),(11,7,'VM2','STOPPED','1','1GB','10GB','alpine:latest'),(12,7,'VM3','STOPPED','1','1GB','10GB','centos:latest'),(13,7,'VM4','STOPPED','1','1GB','10GB','ubuntu:latest'),(14,8,'VM1','STOPPED','1','1GB','10GB','debian:latest'),(15,8,'VM2','STOPPED','1','1GB','10GB','centos:latest'),(16,8,'VM3','STOPPED','1','1GB','10GB','ubuntu:latest'),(19,10,'VM1','STOPPED','1','1GB','10GB','ubuntu:latest'),(20,10,'VM2','STOPPED','1','1GB','10GB','ubuntu:latest'),(21,10,'VM3','STOPPED','1','1GB','10GB','ubuntu:latest'),(27,12,'VM1','STOPPED','1','1GB','10GB','ubuntu:latest'),(28,12,'VM2','STOPPED','1','1GB','10GB','ubuntu:latest'),(29,12,'VM3','STOPPED','1','1GB','10GB','ubuntu:latest'),(30,12,'VM4','STOPPED','1','1GB','10GB','ubuntu:latest'),(31,12,'VM5','STOPPED','1','1GB','10GB','ubuntu:latest');
/*!40000 ALTER TABLE `instancia` ENABLE KEYS */;
UNLOCK TABLES;

--
-- Table structure for table `interfaz`
--

DROP TABLE IF EXISTS `interfaz`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `interfaz` (
  `idinterfaz` int NOT NULL AUTO_INCREMENT,
  `nombre_interfaz` varchar(45) DEFAULT NULL,
  `instancia_idinstancia` int NOT NULL,
  `instancia_slice_idslice` int NOT NULL,
  PRIMARY KEY (`idinterfaz`,`instancia_idinstancia`,`instancia_slice_idslice`),
  KEY `fk_interfaz_instancia1_idx` (`instancia_idinstancia`,`instancia_slice_idslice`),
  CONSTRAINT `fk_interfaz_instancia1` FOREIGN KEY (`instancia_idinstancia`, `instancia_slice_idslice`) REFERENCES `instancia` (`idinstancia`, `slice_idslice`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb3;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `interfaz`
--

LOCK TABLES `interfaz` WRITE;
/*!40000 ALTER TABLE `interfaz` DISABLE KEYS */;
/*!40000 ALTER TABLE `interfaz` ENABLE KEYS */;
UNLOCK TABLES;

--
-- Table structure for table `rol`
--

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
-- Table structure for table `security`
--

DROP TABLE IF EXISTS `security`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `security` (
  `idsecurity` int NOT NULL AUTO_INCREMENT,
  `tipo` varchar(45) DEFAULT NULL,
  `descripcion` varchar(45) DEFAULT NULL,
  PRIMARY KEY (`idsecurity`)
) ENGINE=InnoDB AUTO_INCREMENT=2 DEFAULT CHARSET=utf8mb3;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `security`
--

LOCK TABLES `security` WRITE;
/*!40000 ALTER TABLE `security` DISABLE KEYS */;
INSERT INTO `security` VALUES (1,'basic','Basic security policy');
/*!40000 ALTER TABLE `security` ENABLE KEYS */;
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
  `security_idsecurity` int NOT NULL,
  PRIMARY KEY (`idslice`,`security_idsecurity`),
  KEY `fk_slice_security1_idx` (`security_idsecurity`),
  CONSTRAINT `fk_slice_security1` FOREIGN KEY (`security_idsecurity`) REFERENCES `security` (`idsecurity`)
) ENGINE=InnoDB AUTO_INCREMENT=14 DEFAULT CHARSET=utf8mb3;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `slice`
--

LOCK TABLES `slice` WRITE;
/*!40000 ALTER TABLE `slice` DISABLE KEYS */;
INSERT INTO `slice` VALUES (3,'daniel','STOPPED','{\"nodes\":[{\"id\":1,\"label\":\"VM1\",\"color\":{\"background\":\"#28a745\",\"border\":\"#1e7e34\"}},{\"id\":2,\"label\":\"VM2\",\"color\":{\"background\":\"#28a745\",\"border\":\"#1e7e34\"}}],\"edges\":[{\"from\":1,\"to\":2,\"id\":\"b618874e-43e9-4b42-925e-4b133f57b835\"}]}','2025-09-24',NULL,1),(4,'daniel2','STOPPED','{\"nodes\": [{\"id\": 1, \"label\": \"VM1\", \"color\": \"#28a745\"}, {\"id\": 2, \"label\": \"VM2\", \"color\": \"#28a745\"}, {\"id\": 3, \"label\": \"VM3\", \"color\": \"#28a745\"}], \"edges\": [{\"from\": 1, \"to\": 2}, {\"from\": 1, \"to\": 3}]}','2025-09-24',NULL,1),(5,'9oa','STOPPED','{\"nodes\":[{\"id\":1,\"label\":\"VM1\",\"color\":{\"background\":\"#28a745\",\"border\":\"#1e7e34\"}},{\"id\":2,\"label\":\"VM2\",\"color\":{\"background\":\"#28a745\",\"border\":\"#1e7e34\"}},{\"id\":3,\"label\":\"VM3\",\"color\":{\"background\":\"#28a745\",\"border\":\"#1e7e34\"}},{\"id\":4,\"label\":\"VM4\",\"color\":{\"background\":\"#28a745\",\"border\":\"#1e7e34\"}}],\"edges\":[]}','2025-09-24',NULL,1),(6,'awa','STOPPED','{\"nodes\":[{\"id\":1,\"label\":\"VM1\",\"color\":{\"background\":\"#28a745\",\"border\":\"#1e7e34\"}},{\"id\":2,\"label\":\"VM2\",\"color\":{\"background\":\"#28a745\",\"border\":\"#1e7e34\"}}],\"edges\":[{\"from\":1,\"to\":2,\"id\":\"58fcbc68-d749-4c7b-9cfd-62c9e1f28bff\"}]}','2025-09-24',NULL,1),(7,'sdn','STOPPED','{\"nodes\": [{\"id\": 1, \"label\": \"VM1\", \"color\": \"#28a745\"}, {\"id\": 2, \"label\": \"VM2\", \"color\": \"#28a745\"}, {\"id\": 3, \"label\": \"VM3\", \"color\": \"#28a745\"}, {\"id\": 4, \"label\": \"VM4\", \"color\": \"#28a745\"}], \"edges\": [{\"from\": 1, \"to\": 2}, {\"from\": 1, \"to\": 3}, {\"from\": 1, \"to\": 4}]}','2025-09-25',NULL,1),(8,'sdn','STOPPED','{\"nodes\":[{\"id\":1,\"label\":\"VM1\",\"color\":{\"background\":\"#28a745\",\"border\":\"#1e7e34\"}},{\"id\":2,\"label\":\"VM2\",\"color\":{\"background\":\"#28a745\",\"border\":\"#1e7e34\"}},{\"id\":3,\"label\":\"VM3\",\"color\":{\"background\":\"#28a745\",\"border\":\"#1e7e34\"}}],\"edges\":[{\"from\":1,\"to\":2,\"id\":\"f1a64c3b-083f-4d0f-91e3-6b85fca8575c\"},{\"from\":2,\"to\":3,\"id\":\"b3113611-6732-4ef3-96e2-d4b78838109e\"}]}','2025-09-25',NULL,1),(10,'awa','STOPPED','{\"nodes\":[],\"edges\":[]}','2025-09-29',NULL,1),(12,'dadadad','STOPPED','{\"nodes\":[{\"id\":1,\"label\":\"VM1\",\"color\":{\"background\":\"#28a745\",\"border\":\"#1e7e34\"}},{\"id\":2,\"label\":\"VM2\",\"color\":{\"background\":\"#28a745\",\"border\":\"#1e7e34\"}},{\"id\":3,\"label\":\"VM3\",\"color\":{\"background\":\"#28a745\",\"border\":\"#1e7e34\"}},{\"id\":4,\"label\":\"VM4\",\"color\":{\"background\":\"#28a745\",\"border\":\"#1e7e34\"}},{\"id\":5,\"label\":\"VM5\",\"color\":{\"background\":\"#28a745\",\"border\":\"#1e7e34\"}}],\"edges\":[{\"from\":1,\"to\":2,\"id\":\"54755b46-7a9f-4102-8f6e-39ae56450086\"},{\"from\":3,\"to\":4,\"id\":\"e0e320c3-34d8-4480-81ff-c3bd411aa882\"},{\"from\":1,\"to\":5,\"id\":\"20b91a41-44a8-4da8-bbe6-4d72fc9ddc66\"},{\"from\":5,\"to\":4,\"id\":\"5d76ba38-79b8-4f00-aef1-d300302d4bd5\"},{\"from\":2,\"to\":3,\"id\":\"0c2e3a4d-1fa8-403e-8722-e1da156e95fd\"}]}','2025-09-29',NULL,1);
/*!40000 ALTER TABLE `slice` ENABLE KEYS */;
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
) ENGINE=InnoDB AUTO_INCREMENT=6 DEFAULT CHARSET=utf8mb3;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `usuario`
--

LOCK TABLES `usuario` WRITE;
/*!40000 ALTER TABLE `usuario` DISABLE KEYS */;
INSERT INTO `usuario` VALUES (1,'admin','$2a$13$hDsl2kC2dMYEuV02CoeiyuZd1SWPx4N0gM4QghCuJb7TDs0uaSgne', 1);
/*!40000 ALTER TABLE `usuario` ENABLE KEYS */;
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
  KEY `fk_usuario_has_slice_usuario_idx` (`usuario_idusuario`),
  CONSTRAINT `fk_usuario_has_slice_slice1` FOREIGN KEY (`slice_idslice`) REFERENCES `slice` (`idslice`),
  CONSTRAINT `fk_usuario_has_slice_usuario` FOREIGN KEY (`usuario_idusuario`) REFERENCES `usuario` (`idusuario`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb3;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `usuario_has_slice`
--

LOCK TABLES `usuario_has_slice` WRITE;
/*!40000 ALTER TABLE `usuario_has_slice` DISABLE KEYS */;
INSERT INTO `usuario_has_slice` VALUES (1,3),(1,4),(1,5),(1,6),(4,7),(4,8),(4,10),(4,12);
/*!40000 ALTER TABLE `usuario_has_slice` ENABLE KEYS */;
UNLOCK TABLES;
/*!40103 SET TIME_ZONE=@OLD_TIME_ZONE */;

/*!40101 SET SQL_MODE=@OLD_SQL_MODE */;
/*!40014 SET FOREIGN_KEY_CHECKS=@OLD_FOREIGN_KEY_CHECKS */;
/*!40014 SET UNIQUE_CHECKS=@OLD_UNIQUE_CHECKS */;
/*!40101 SET CHARACTER_SET_CLIENT=@OLD_CHARACTER_SET_CLIENT */;
/*!40101 SET CHARACTER_SET_RESULTS=@OLD_CHARACTER_SET_RESULTS */;
/*!40101 SET COLLATION_CONNECTION=@OLD_COLLATION_CONNECTION */;
/*!40111 SET SQL_NOTES=@OLD_SQL_NOTES */;

-- Dump completed on 2025-09-29 17:33:21
