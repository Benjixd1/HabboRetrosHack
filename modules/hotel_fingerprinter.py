#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Hotel Fingerprinter Modulu
Hedef Habbo retrosunun CMS ve emulator tipini otomatik tespit eder.
Sayfa kaynagi, CSS yollari, hata mesajlari ve API yanitlarini analiz eder.
"""

import re
import json
import requests
from typing import Dict, List, Optional, Tuple, Any
from urllib.parse import urlparse
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed

from utils.log_utils import Logger


class HotelFingerprinter:
    """
    Hedef Habbo retrosunun CMS ve emulator tipini tespit eder.
    Birden fazla teknik kullanir: sayfa kaynagi, CSS, JS, hata mesajlari, API.
    """

    # CMS imzalari
    CMS_SIGNATURES = {
        "revcms": {
            "name": "RevCMS",
            "patterns": [
                r"RevCMS", r"revcms", r"powered by rev",
                r"tpl/", r"templates/revcms",
                r"revcms\.js", r"revcms\.css",
                r"var revcms",
            ],
            "paths": ["/tpl/", "/templates/", "/revcms/"],
            "cookies": ["revcms_session"],
        },
        "atomcms": {
            "name": "AtomCMS",
            "patterns": [
                r"AtomCMS", r"atomcms", r"atom cms",
                r"atomcms\.js", r"atomcms\.css",
                r"Atom\s*CMS",
                r"content/atomcms",
            ],
            "paths": ["/atomcms/", "/content/atomcms/"],
            "cookies": ["atomcms_session"],
        },
        "phoenixphp": {
            "name": "PhoenixPHP",
            "patterns": [
                r"PhoenixPHP", r"phoenixphp", r"phoenix php",
                r"app/tpl/", r"apps/tpl/",
                r"phoenix\.js", r"phoenix\.css",
            ],
            "paths": ["/app/tpl/", "/apps/tpl/", "/phoenix/"],
            "cookies": ["phoenix_session"],
        },
        "ubercms": {
            "name": "UberCMS",
            "patterns": [
                r"UberCMS", r"ubercms", r"uber cms",
                r"uber\.js", r"uber\.css",
                r"inc/tpl/",
            ],
            "paths": ["/inc/tpl/", "/ubercms/"],
            "cookies": ["ubercms_session"],
        },
        "cyclonecms": {
            "name": "CycloneCMS",
            "patterns": [
                r"CycloneCMS", r"cyclonecms", r"cyclone cms",
                r"cyclone\.js", r"cyclone\.css",
            ],
            "paths": ["/cyclone/"],
            "cookies": ["cyclone_session"],
        },
        "habbocms": {
            "name": "HabboCMS",
            "patterns": [
                r"HabboCMS", r"habbocms", r"habbo cms",
                r"habbocms\.js",
                r"habbo_cms",
            ],
            "paths": ["/habbocms/"],
            "cookies": ["habbocms_session"],
        },
        "bootstrapcms": {
            "name": "BootstrapCMS",
            "patterns": [
                r"BootstrapCMS", r"bootstrapcms",
                r"bootstrapcms\.js",
            ],
            "paths": ["/bootstrapcms/"],
            "cookies": ["bootstrapcms_session"],
        },
        "lightcms": {
            "name": "LightCMS",
            "patterns": [
                r"LightCMS", r"lightcms",
                r"lightcms\.js",
            ],
            "paths": ["/lightcms/"],
            "cookies": ["lightcms_session"],
        },
        "goldtree": {
            "name": "GoldTreeCMS",
            "patterns": [
                r"GoldTree", r"goldtree", r"gold tree",
                r"goldtree\.js",
            ],
            "paths": ["/goldtree/"],
            "cookies": ["goldtree_session"],
        },
    }

    # Emulator imzalari
    EMULATOR_SIGNATURES = {
        "arcturus_morningstar": {
            "name": "Arcturus Morningstar",
            "patterns": [
                r"Arcturus", r"arcturus", r"Morningstar",
                r"arcturus_morningstar",
                r"EMU: Arcturus",
                r"Arcturus Emulator",
            ],
            "headers": ["Arcturus"],
            "variables": ["arcturus", "morningstar"],
        },
        "plusemu": {
            "name": "PlusEMU",
            "patterns": [
                r"PlusEMU", r"plusemu", r"Plus Emulator",
                r"EMU: Plus",
                r"Plus Emulator",
            ],
            "headers": ["PlusEMU"],
            "variables": ["plusemu", "plus"],
        },
        "comet": {
            "name": "Comet",
            "patterns": [
                r"Comet", r"comet",
                r"EMU: Comet",
                r"Comet Emulator",
            ],
            "headers": ["Comet"],
            "variables": ["comet"],
        },
        "phoenix": {
            "name": "Phoenix",
            "patterns": [
                r"Phoenix", r"phoenix", r"Phoenix 3",
                r"EMU: Phoenix",
                r"Phoenix Emulator",
            ],
            "headers": ["Phoenix"],
            "variables": ["phoenix"],
        },
        "uberemu": {
            "name": "UberEmu",
            "patterns": [
                r"UberEmu", r"uberemu", r"Uber Emulator",
                r"EMU: Uber",
            ],
            "headers": ["UberEmu"],
            "variables": ["uberemu", "uber"],
        },
        "butterfly": {
            "name": "Butterfly",
            "patterns": [
                r"Butterfly", r"butterfly",
                r"EMU: Butterfly",
            ],
            "headers": ["Butterfly"],
            "variables": ["butterfly"],
        },
        "azure": {
            "name": "Azure",
            "patterns": [
                r"Azure", r"azure",
                r"EMU: Azure",
            ],
            "headers": ["Azure"],
            "variables": ["azure"],
        },
        "nitro": {
            "name": "Nitro",
            "patterns": [
                r"Nitro", r"nitro",
                r"Nitro Emulator",
                r"nitro\.js", r"nitro-client",
                r"nitro_renderer",
            ],
            "headers": ["Nitro"],
            "variables": ["nitro"],
        },
        "birp": {
            "name": "BiRP",
            "patterns": [
                r"BiRP", r"birp",
                r"EMU: BiRP",
            ],
            "headers": ["BiRP"],
            "variables": ["birp"],
        },
        "holograph": {
            "name": "Holograph",
            "patterns": [
                r"Holograph", r"holograph",
                r"EMU: Holograph",
                r"Holograph Emulator",
            ],
            "headers": ["Holograph"],
            "variables": ["holograph"],
        },
    }

    # CMS-spesifik hata mesajlari
    CMS_ERROR_PATTERNS = {
        "revcms": [
            "RevCMS Error", "revcms error",
            "Template not found:",
            "Fatal error: Call to undefined method RevCMS",
        ],
        "atomcms": [
            "AtomCMS Error", "atomcms error",
            "AtomCMS Exception",
        ],
        "phoenixphp": [
            "PhoenixPHP Error", "phoenixphp error",
            "Fatal error: Uncaught Error: Call to undefined method Phoenix",
        ],
        "ubercms": [
            "UberCMS Error", "ubercms error",
            "Fatal error: Uncaught Error: Call to undefined method UberCMS",
        ],
    }

    # CMS-spesifik API endpointleri
    CMS_API_PATHS = {
        "revcms": ["/api/", "/api/v1/", "/api/user/", "/api/register/"],
        "atomcms": ["/api/", "/api/v1/", "/atomcms/api/"],
        "phoenixphp": ["/api/", "/api/v1/", "/phoenix/api/"],
        "ubercms": ["/api/", "/api/v1/", "/ubercms/api/"],
        "generic": ["/api/", "/api/v1/", "/api/user/", "/api/register/", "/api/login/"],
    }

    def __init__(self, target_url: str, logger: Optional[Logger] = None, gui_callback=None):
        self.target_url = target_url.rstrip("/")
        parsed = urlparse(target_url)
        self.hostname = parsed.hostname or ""
        self.scheme = parsed.scheme or "https"
        self.logger = logger or Logger("HotelFingerprinter")
        self.gui_callback = gui_callback
        self._stop_flag = False
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.5",
        })
        self.results: Dict = {
            "target": self.target_url,
            "hostname": self.hostname,
            "cms": None,
            "cms_confidence": 0,
            "emulator": None,
            "emulator_confidence": 0,
            "page_title": None,
            "meta_generator": None,
            "cookies": [],
            "detected_paths": [],
            "api_endpoints": [],
            "version_info": {},
            "timestamp": datetime.now().isoformat(),
        }

    def stop(self):
        self._stop_flag = True

    def _log(self, level: str, message: str) -> None:
        if self.gui_callback:
            self.gui_callback(f"[{level}] [FINGERPRINT] {message}")
        if level == "INFO":
            self.logger.info(message)
        elif level == "SUCCESS":
            self.logger.success(message)
        elif level == "WARNING":
            self.logger.warning(message)
        elif level == "ERROR":
            self.logger.error(message)

    def run(self, timeout: int = 60) -> Dict:
        """Tam fingerprinter analizini baslatir."""
        self._log("INFO", f"Hotel Fingerprinter baslatiliyor: {self.hostname}")

        # 1. Ana sayfayi analiz et
        self._analyze_main_page(timeout)

        # 2. CMS imzalarini tara
        self._detect_cms(timeout)

        # 3. Emulator imzalarini tara
        self._detect_emulator(timeout)

        # 4. API endpointlerini kesfet
        self._discover_api_endpoints(timeout)

        # 5. Hata mesajlarini analiz et
        self._analyze_error_pages(timeout)

        # 6. external_variables analizi
        self._analyze_external_variables(timeout)

        # Sonuc
        if self.results["cms"]:
            self._log("SUCCESS", f"CMS tespit edildi: {self.results['cms']} (guven: %{self.results['cms_confidence']})")
        else:
            self._log("WARNING", "CMS tespit edilemedi.")

        if self.results["emulator"]:
            self._log("SUCCESS", f"Emulator tespit edildi: {self.results['emulator']} (guven: %{self.results['emulator_confidence']})")
        else:
            self._log("WARNING", "Emulator tespit edilemedi.")

        return self.results

    def _analyze_main_page(self, timeout: int) -> None:
        """Ana sayfayi indir ve analiz et."""
        try:
            r = self.session.get(self.target_url, timeout=min(timeout, 15))
            content = r.text
            self.results["cookies"] = [{"name": c.name, "value": c.value[:20] + "..." if len(c.value) > 20 else c.value} for c in r.cookies]

            # Page title
            title_match = re.search(r"<title>(.*?)</title>", content, re.IGNORECASE | re.DOTALL)
            if title_match:
                self.results["page_title"] = title_match.group(1).strip()
                self._log("INFO", f"Sayfa basligi: {self.results['page_title']}")

            # Meta generator
            gen_match = re.search(r'<meta\s+name=["\']generator["\']\s+content=["\'](.*?)["\']', content, re.IGNORECASE)
            if gen_match:
                self.results["meta_generator"] = gen_match.group(1).strip()
                self._log("INFO", f"Meta generator: {self.results['meta_generator']}")

            # Version info
            version_match = re.search(r"v(?:ersion)?\s*[.:]?\s*(\d+\.\d+(?:\.\d+)?)", content, re.IGNORECASE)
            if version_match:
                self.results["version_info"]["page_version"] = version_match.group(1)

            self._log("INFO", f"Ana sayfa analiz edildi ({len(content)} bytes)")

        except requests.RequestException as e:
            self._log("ERROR", f"Ana sayfa analiz hatasi: {e}")

    def _detect_cms(self, timeout: int) -> None:
        """CMS tipini tespit et."""
        scores = {}
        try:
            r = self.session.get(self.target_url, timeout=min(timeout, 15))
            content = r.text.lower()

            for cms_id, sig in self.CMS_SIGNATURES.items():
                score = 0
                # Pattern eslesmesi
                for pattern in sig["patterns"]:
                    if re.search(pattern, content, re.IGNORECASE):
                        score += 25
                        self._log("INFO", f"{sig['name']} pattern bulundu: {pattern}")

                # Cookie eslesmesi
                for cookie_name in sig["cookies"]:
                    if cookie_name in [c.name for c in r.cookies]:
                        score += 20
                        self._log("INFO", f"{sig['name']} cookie bulundu: {cookie_name}")

                # Path kontrolu
                for path in sig["paths"]:
                    path_url = f"{self.scheme}://{self.hostname}{path}"
                    try:
                        pr = self.session.get(path_url, timeout=5)
                        if pr.status_code == 200:
                            score += 15
                            self.results["detected_paths"].append(path_url)
                    except Exception:
                        pass

                if score > 0:
                    scores[cms_id] = score

            if scores:
                best = max(scores, key=scores.get)
                self.results["cms"] = self.CMS_SIGNATURES[best]["name"]
                self.results["cms_confidence"] = min(scores[best], 100)
                self.results["cms_id"] = best

        except requests.RequestException as e:
            self._log("ERROR", f"CMS tespit hatasi: {e}")

    def _detect_emulator(self, timeout: int) -> None:
        """Emulator tipini tespit et."""
        scores = {}
        try:
            # Ana sayfada emulator imzasi ara
            r = self.session.get(self.target_url, timeout=min(timeout, 15))
            content = r.text.lower()

            # external_variables kontrolu
            ext_paths = ["/external_variables", "/gamedata/external_variables", "/client/external_variables"]
            ext_content = ""
            for path in ext_paths:
                try:
                    er = self.session.get(f"{self.scheme}://{self.hostname}{path}", timeout=5)
                    if er.status_code == 200:
                        ext_content = er.text.lower()
                        break
                except Exception:
                    pass

            for emu_id, sig in self.EMULATOR_SIGNATURES.items():
                score = 0

                # Sayfa icinde pattern ara
                for pattern in sig["patterns"]:
                    if re.search(pattern, content, re.IGNORECASE):
                        score += 30
                        self._log("INFO", f"{sig['name']} pattern bulundu: {pattern}")

                # external_variables icinde ara
                if ext_content:
                    for var_pattern in sig["variables"]:
                        if var_pattern in ext_content:
                            score += 25
                            self._log("INFO", f"{sig['name']} external_variables'de bulundu: {var_pattern}")

                # Header kontrolu
                for header in sig["headers"]:
                    if header.lower() in str(r.headers).lower():
                        score += 20

                if score > 0:
                    scores[emu_id] = score

            if scores:
                best = max(scores, key=scores.get)
                self.results["emulator"] = self.EMULATOR_SIGNATURES[best]["name"]
                self.results["emulator_confidence"] = min(scores[best], 100)
                self.results["emulator_id"] = best

        except requests.RequestException as e:
            self._log("ERROR", f"Emulator tespit hatasi: {e}")

    def _discover_api_endpoints(self, timeout: int) -> None:
        """API endpointlerini kesfet."""
        cms_id = self.results.get("cms_id", "generic")
        api_paths = self.CMS_API_PATHS.get(cms_id, self.CMS_API_PATHS["generic"])

        found = []
        for path in api_paths:
            if self._stop_flag:
                break
            url = f"{self.scheme}://{self.hostname}{path}"
            try:
                r = self.session.get(url, timeout=min(timeout, 5))
                if r.status_code in [200, 201, 401, 403]:
                    found.append({"path": path, "status": r.status_code, "type": r.headers.get("Content-Type", "")})
                    self._log("INFO", f"API endpoint bulundu: {path} (HTTP {r.status_code})")
            except Exception:
                pass

        self.results["api_endpoints"] = found

    def _analyze_error_pages(self, timeout: int) -> None:
        """Hata sayfalarini analiz et."""
        error_paths = [
            "/admin", "/admin/", "/api", "/api/",
            "/index.php?url=../../../etc/passwd",
            "/index.php?page=../../",
            "/register", "/register/",
            "/nonexistent_page_12345",
        ]

        for path in error_paths:
            if self._stop_flag:
                break
            url = f"{self.scheme}://{self.hostname}{path}"
            try:
                r = self.session.get(url, timeout=min(timeout, 5))
                content = r.text.lower()

                for cms_id, patterns in self.CMS_ERROR_PATTERNS.items():
                    for pattern in patterns:
                        if pattern.lower() in content:
                            self._log("SUCCESS", f"Hata mesajinda {cms_id} tespit edildi: {pattern}")
                            if not self.results["cms"]:
                                self.results["cms"] = self.CMS_SIGNATURES.get(cms_id, {}).get("name", cms_id)
                                self.results["cms_confidence"] = max(self.results.get("cms_confidence", 0), 80)
                                self.results["cms_id"] = cms_id
            except Exception:
                pass

    def _analyze_external_variables(self, timeout: int) -> None:
        """external_variables dosyasini analiz et."""
        ext_paths = [
            "/external_variables",
            "/gamedata/external_variables",
            "/client/external_variables",
            "/swf/external_variables.txt",
            "/r63/external_variables",
            "/r63b/external_variables",
        ]

        for path in ext_paths:
            if self._stop_flag:
                break
            url = f"{self.scheme}://{self.hostname}{path}"
            try:
                r = self.session.get(url, timeout=min(timeout, 5))
                if r.status_code == 200:
                    content = r.text
                    self.results["external_variables_url"] = url

                    # Emulator ipucu ara
                    if "arcturus" in content.lower():
                        self._update_emulator_score("arcturus_morningstar", 40)
                    if "plusemu" in content.lower() or "plus" in content.lower():
                        self._update_emulator_score("plusemu", 40)
                    if "comet" in content.lower():
                        self._update_emulator_score("comet", 40)
                    if "nitro" in content.lower():
                        self._update_emulator_score("nitro", 40)

                    # WS bilgisi
                    ws_match = re.search(r"(?:ws|websocket)\.?(?:_|\.)?(?:host|port|url)[=:]\s*[\"']?([^\"'\s]+)", content, re.IGNORECASE)
                    if ws_match:
                        self.results["websocket_info"] = ws_match.group(1)
                        self._log("INFO", f"WebSocket bilgisi: {ws_match.group(1)}")

                    self._log("INFO", f"external_variables bulundu: {path}")
                    break
            except Exception:
                pass

    def _update_emulator_score(self, emu_id: str, points: int) -> None:
        """Emulator skorunu guncelle."""
        current_emu = self.results.get("emulator_id")
        if current_emu == emu_id:
            self.results["emulator_confidence"] = min(
                self.results.get("emulator_confidence", 0) + points, 100
            )
        elif not current_emu:
            self.results["emulator_id"] = emu_id
            self.results["emulator"] = self.EMULATOR_SIGNATURES[emu_id]["name"]
            self.results["emulator_confidence"] = points

    def get_cms_info(self) -> Dict:
        """CMS bilgilerini dondur."""
        return {
            "cms": self.results.get("cms"),
            "cms_id": self.results.get("cms_id"),
            "confidence": self.results.get("cms_confidence", 0),
        }

    def get_emulator_info(self) -> Dict:
        """Emulator bilgilerini dondur."""
        return {
            "emulator": self.results.get("emulator"),
            "emulator_id": self.results.get("emulator_id"),
            "confidence": self.results.get("emulator_confidence", 0),
        }
