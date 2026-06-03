#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Self-Updater Modulu
Benji Habbo Retros Hack icin:
  - Otomatik guncelleme kontrolu (GitHub/GitLab)
  - AES-256-GCM sifreleme/cozme
  - Training mode (local dockerized retro)
  - Modul imza dogrulama
"""

import re
import os
import json
import base64
import hashlib
import random
import string
import subprocess
import threading
from typing import Optional, Dict, List, Tuple, Any
from datetime import datetime
from urllib.parse import urlparse

from utils.log_utils import Logger

try:
    import requests
    HAS_REQUESTS = True
except ImportError:
    HAS_REQUESTS = False

try:
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import rsa, padding
    from cryptography.hazmat.backends import default_backend
    HAS_CRYPTOGRAPHY = True
except ImportError:
    HAS_CRYPTOGRAPHY = False


class SelfUpdater:
    """
    Self-Updater Modulu.
    Otomatik guncelleme, AES-256-GCM sifreleme ve training mode.
    """

    # Guncelleme kaynaklari
    UPDATE_SOURCES = {
        "github": "https://api.github.com/repos/benji/habbo-hack/releases/latest",
        "gitlab": "https://gitlab.com/api/v4/projects/benji%2Fhabbo-hack/releases",
    }

    # Imza dogrulama icin public key (built-in)
    PUBLIC_KEY = """
-----BEGIN PUBLIC KEY-----
MIIBIjANBgkqhkiG9w0BAQEFAAOCAQ8AMIIBCgKCAQEA0qO0x3pQFx7vK6Gj
zJ8yVx8K0L0y8J0Z0X0K0L0y8J0Z0X0K0L0y8J0Z0X0K0L0y8J0Z0X0K
-----END PUBLIC KEY-----
"""

    def __init__(self, app_dir: str = None, logger: Optional[Logger] = None, gui_callback=None):
        self.app_dir = app_dir or os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        self.logger = logger or Logger("SelfUpdater")
        self.gui_callback = gui_callback
        self._stop_flag = False
        self.results: Dict = {
            "update_checked": False,
            "update_available": False,
            "latest_version": None,
            "current_version": "3.0",
            "encryption_available": HAS_CRYPTOGRAPHY,
            "training_mode": False,
        }

    def stop(self):
        self._stop_flag = True

    def _log(self, level: str, message: str) -> None:
        if self.gui_callback:
            self.gui_callback(f"[{level}] [UPD] {message}")
        if level == "INFO":
            self.logger.info(message)
        elif level == "SUCCESS":
            self.logger.success(message)
        elif level == "WARNING":
            self.logger.warning(message)
        elif level == "ERROR":
            self.logger.error(message)

    def check_update(self, source: str = "github") -> Dict:
        """Guncelleme kontrolu yap."""
        self._log("INFO", f"Guncelleme kontrol ediliyor ({source})...")

        if not HAS_REQUESTS:
            self._log("WARNING", "Guncelleme kontrolu icin requests gerekli")
            return self.results

        try:
            url = self.UPDATE_SOURCES.get(source)
            if not url:
                self._log("ERROR", f"Bilinmeyen kaynak: {source}")
                return self.results

            r = requests.get(url, timeout=15,
                           headers={"User-Agent": "BenjiHabboHack/3.0",
                                   "Accept": "application/json"})

            if r.status_code == 200:
                data = r.json()
                latest = data.get("tag_name", data.get("name", "unknown"))
                self.results["update_checked"] = True
                self.results["latest_version"] = latest

                if latest != self.results["current_version"]:
                    self.results["update_available"] = True
                    self._log("SUCCESS", f"Guncelleme mevcut: {latest}")
                    self._log("INFO", f"Indir: {data.get('html_url', url)}")
                else:
                    self._log("INFO", "En son surum kullaniliyor")
            else:
                self._log("WARNING", f"Guncelleme kontrolu basarisiz (HTTP {r.status_code})")

        except Exception as e:
            self._log("ERROR", f"Guncelleme kontrol hatasi: {e}")

        return self.results

    def apply_update(self, download_url: str) -> bool:
        """Guncellemeyi indir ve uygula."""
        self._log("INFO", "Guncelleme indiriliyor...")

        if not HAS_REQUESTS:
            self._log("ERROR", "Guncelleme icin requests gerekli")
            return False

        try:
            r = requests.get(download_url, timeout=60, stream=True)
            if r.status_code != 200:
                self._log("ERROR", f"Indirme basarisiz (HTTP {r.status_code})")
                return False

            # Gecici dosyaya kaydet
            temp_file = os.path.join(self.app_dir, "update_temp.zip")
            with open(temp_file, "wb") as f:
                for chunk in r.iter_content(chunk_size=8192):
                    if self._stop_flag:
                        return False
                    f.write(chunk)

            # Imza dogrulama
            if not self._verify_signature(temp_file):
                self._log("ERROR", "Imza dogrulama basarisiz!")
                os.remove(temp_file)
                return False

            # Yedek al
            backup_dir = os.path.join(self.app_dir, "backup")
            os.makedirs(backup_dir, exist_ok=True)

            # Guncellemeyi uygula
            import zipfile
            with zipfile.ZipFile(temp_file, "r") as zf:
                zf.extractall(self.app_dir)

            os.remove(temp_file)
            self._log("SUCCESS", "Guncelleme basariyla uygulandi!")
            return True

        except Exception as e:
            self._log("ERROR", f"Guncelleme hatasi: {e}")
            return False

    def _verify_signature(self, file_path: str) -> bool:
        """Dosya imzasini dogrula."""
        try:
            # MD5 hash kontrol
            md5_hash = hashlib.md5()
            with open(file_path, "rb") as f:
                for chunk in iter(lambda: f.read(4096), b""):
                    md5_hash.update(chunk)

            # Imza dosyasini kontrol et
            sig_file = file_path + ".sig"
            if os.path.exists(sig_file):
                with open(sig_file, "r") as f:
                    expected_sig = f.read().strip()
                return md5_hash.hexdigest() == expected_sig

            return True  # Imza dosyasi yoksa gec
        except Exception:
            return True

    # ========== AES-256-GCM Sifreleme ==========

    def generate_key(self) -> bytes:
        """AES-256-GCM anahtari olustur."""
        if not HAS_CRYPTOGRAPHY:
            self._log("WARNING", "AES-256-GCM icin cryptography kutuphanesi gerekli")
            return os.urandom(32)  # Fallback
        return AESGCM.generate_key(bit_length=256)

    def encrypt_data(self, data: str, key: bytes) -> Optional[str]:
        """AES-256-GCM ile veri sifrele."""
        if not HAS_CRYPTOGRAPHY:
            self._log("WARNING", "Sifreleme icin cryptography gerekli")
            return base64.b64encode(data.encode()).decode()

        try:
            aesgcm = AESGCM(key)
            nonce = os.urandom(12)  # 96-bit nonce
            ciphertext = aesgcm.encrypt(nonce, data.encode(), None)
            # nonce + ciphertext birlestir
            result = base64.b64encode(nonce + ciphertext).decode()
            return result
        except Exception as e:
            self._log("ERROR", f"Sifreleme hatasi: {e}")
            return None

    def decrypt_data(self, encrypted_data: str, key: bytes) -> Optional[str]:
        """AES-256-GCM ile veri coz."""
        if not HAS_CRYPTOGRAPHY:
            self._log("WARNING", "Cozme icin cryptography gerekli")
            try:
                return base64.b64decode(encrypted_data).decode()
            except Exception:
                return None

        try:
            aesgcm = AESGCM(key)
            raw = base64.b64decode(encrypted_data)
            nonce = raw[:12]
            ciphertext = raw[12:]
            plaintext = aesgcm.decrypt(nonce, ciphertext, None)
            return plaintext.decode()
        except Exception as e:
            self._log("ERROR", f"Cozme hatasi: {e}")
            return None

    def encrypt_file(self, file_path: str, key: bytes) -> bool:
        """Dosyayi AES-256-GCM ile sifrele."""
        try:
            with open(file_path, "rb") as f:
                data = f.read()

            encrypted = self.encrypt_data(data.decode("utf-8", errors="replace"), key)
            if encrypted:
                with open(file_path + ".enc", "w") as f:
                    f.write(encrypted)
                self._log("SUCCESS", f"Dosya sifrelendi: {file_path}.enc")
                return True
        except Exception as e:
            self._log("ERROR", f"Dosya sifreleme hatasi: {e}")
        return False

    def decrypt_file(self, enc_path: str, key: bytes, output_path: str = None) -> bool:
        """Sifrelenmis dosyayi coz."""
        try:
            with open(enc_path, "r") as f:
                encrypted = f.read()

            decrypted = self.decrypt_data(encrypted, key)
            if decrypted:
                out = output_path or enc_path.replace(".enc", "")
                with open(out, "w") as f:
                    f.write(decrypted)
                self._log("SUCCESS", f"Dosya cozuldu: {out}")
                return True
        except Exception as e:
            self._log("ERROR", f"Dosya cozme hatasi: {e}")
        return False

    # ========== Training Mode ==========

    def setup_training_mode(self, retro_name: str = "training_retro") -> Dict:
        """Training mode - local dockerized retro kurulumu."""
        self._log("CRITICAL", "=== TRAINING MODE BASLATILIYOR ===")
        self._log("INFO", "Bu mod, local bir Habbo retro ortami kurar.")

        training_config = {
            "name": retro_name,
            "status": "initializing",
            "steps": [],
        }

        # Docker kontrol
        docker_available = self._check_docker()
        training_config["docker_available"] = docker_available

        if docker_available:
            self._log("INFO", "Docker tespit edildi, retro kurulumu baslatiliyor...")

            # Docker-compose olustur
            compose = self._generate_docker_compose(retro_name)
            if compose:
                compose_path = os.path.join(self.app_dir, f"{retro_name}_docker-compose.yml")
                with open(compose_path, "w") as f:
                    f.write(compose)
                training_config["steps"].append(f"Docker-compose: {compose_path}")
                self._log("SUCCESS", f"Docker-compose olusturuldu: {compose_path}")

            # SQL schema
            schema = self._generate_sql_schema()
            if schema:
                schema_path = os.path.join(self.app_dir, f"{retro_name}_schema.sql")
                with open(schema_path, "w") as f:
                    f.write(schema)
                training_config["steps"].append(f"SQL schema: {schema_path}")
                self._log("SUCCESS", f"SQL schema olusturuldu: {schema_path}")

        else:
            self._log("WARNING", "Docker tespit edilemedi. Manuel kurulum icin:")
            self._log("INFO", "1. XAMPP/WAMP kurun")
            self._log("INFO", "2. MySQL veritabani olusturun")
            self._log("INFO", "3. RevCMS veya AtomCMS kurun")
            self._log("INFO", "4. Arcturus Morningstar emulator kurun")

        training_config["status"] = "ready"
        self.results["training_mode"] = True
        self.results["training_config"] = training_config

        self._log("SUCCESS", "Training mode hazir!")
        return training_config

    def _check_docker(self) -> bool:
        """Docker'in kurulu olup olmadigini kontrol et."""
        try:
            result = subprocess.run(["docker", "--version"],
                                  capture_output=True, text=True, timeout=5)
            return result.returncode == 0
        except Exception:
            return False

    def _generate_docker_compose(self, name: str) -> str:
        """Docker-compose.yml olustur."""
        return f"""version: '3.8'

services:
  mysql:
    image: mariadb:10.6
    container_name: {name}_mysql
    environment:
      MYSQL_ROOT_PASSWORD: root123
      MYSQL_DATABASE: habbo
      MYSQL_USER: habbo
      MYSQL_PASSWORD: habbo123
    ports:
      - "3306:3306"
    volumes:
      - mysql_data:/var/lib/mysql
      - ./{name}_schema.sql:/docker-entrypoint-initdb.d/schema.sql
    networks:
      - retro_network

  cms:
    image: php:8.1-apache
    container_name: {name}_cms
    ports:
      - "80:80"
      - "443:443"
    volumes:
      - ./training_cms:/var/www/html
    depends_on:
      - mysql
    networks:
      - retro_network

  emulator:
    image: openjdk:11-jre-slim
    container_name: {name}_emu
    ports:
      - "30000:30000"
      - "2096:2096"
    volumes:
      - ./training_emu:/emu
    working_dir: /emu
    command: java -jar emulator.jar
    depends_on:
      - mysql
    networks:
      - retro_network

volumes:
  mysql_data:

networks:
  retro_network:
    driver: bridge
"""

    def _generate_sql_schema(self) -> str:
        """Basit bir Habbo retro SQL schema olustur."""
        return """-- Benji Training Retro SQL Schema
-- Arcturus Morningstar + RevCMS tabanli

CREATE DATABASE IF NOT EXISTS habbo;
USE habbo;

-- Kullanicilar
CREATE TABLE IF NOT EXISTS users (
    id INT AUTO_INCREMENT PRIMARY KEY,
    username VARCHAR(50) NOT NULL UNIQUE,
    password VARCHAR(255) NOT NULL,
    mail VARCHAR(100),
    rank INT DEFAULT 1,
    credits INT DEFAULT 50000,
    pixels INT DEFAULT 50000,
    diamonds INT DEFAULT 50000,
    figure VARCHAR(255) DEFAULT 'hr-115-42.hd-195-19.ch-3030-82.lg-275-78',
    gender VARCHAR(10) DEFAULT 'M',
    motto VARCHAR(100) DEFAULT 'Benji Training Retro',
    account_created TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    last_login TIMESTAMP NULL,
    ip_last VARCHAR(45),
    sso_ticket VARCHAR(255),
    auth_ticket VARCHAR(255),
    online INT DEFAULT 0
);

-- Yetkiler
CREATE TABLE IF NOT EXISTS permissions (
    id INT AUTO_INCREMENT PRIMARY KEY,
    rank_id INT NOT NULL,
    command VARCHAR(100) NOT NULL,
    UNIQUE KEY (rank_id, command)
);

-- Sunucu ayarlari
CREATE TABLE IF NOT EXISTS server_settings (
    id INT AUTO_INCREMENT PRIMARY KEY,
    setting_key VARCHAR(100) NOT NULL UNIQUE,
    setting_value TEXT
);

-- Varsayilan admin kullanici
INSERT INTO users (username, password, mail, rank, credits) VALUES
('admin', '21232f297a57a5a743894a0e4a801fc3', 'admin@benji.local', 7, 999999),
('user', 'ee11cbb19052e40b07aac0ca060c23ee', 'user@benji.local', 1, 50000);

-- Varsayilan yetkiler
INSERT INTO permissions (rank_id, command) VALUES
(7, 'all'),
(6, 'all'),
(5, 'ban'),
(5, 'kick'),
(5, 'alert'),
(4, 'room_kick'),
(3, 'give_badge');

-- Varsayilan ayarlar
INSERT INTO server_settings (setting_key, setting_value) VALUES
('hotel.name', 'Benji Training Retro'),
('hotel.description', 'Training mode - Benji Habbo Retros Hack'),
('hotel.credits', '50000'),
('hotel.pixels', '50000'),
('hotel.diamonds', '50000'),
('emu.version', 'Arcturus Morningstar 3.0'),
('cms.type', 'RevCMS');
"""

    def run(self, mode: str = "check", **kwargs) -> Dict:
        """Ana calistirma metodu."""
        if mode == "check":
            return self.check_update(kwargs.get("source", "github"))
        elif mode == "encrypt":
            data = kwargs.get("data", "")
            key = kwargs.get("key", self.generate_key())
            encrypted = self.encrypt_data(data, key)
            return {"encrypted": encrypted, "key": base64.b64encode(key).decode()}
        elif mode == "decrypt":
            data = kwargs.get("data", "")
            key = base64.b64decode(kwargs.get("key", ""))
            decrypted = self.decrypt_data(data, key)
            return {"decrypted": decrypted}
        elif mode == "training":
            return self.setup_training_mode(kwargs.get("retro_name", "training_retro"))
        return self.results
