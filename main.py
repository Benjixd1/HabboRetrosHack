#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Benji Habbo Retros Hack v4.0 - State Machine Architecture
Tkinter tabanli grafik arayuz. Tum moduller attack_state.json uzerinden
veri paylasir. Tab siralamasi atak zincirine goredir.
"""

import sys
import os
import json
import threading
import time
import tkinter as tk
from tkinter import ttk, scrolledtext, messagebox, filedialog
from typing import Optional, Dict, Any, Callable, List
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Modul importlari
try:
    from modules.cloudflare_bypass import CloudflareBypass
    HAS_CLOUDFLARE = True
except ImportError:
    HAS_CLOUDFLARE = False

try:
    from modules.admin_extractor import AdminExtractor
    HAS_ADMIN = True
except ImportError:
    HAS_ADMIN = False

try:
    from modules.packet_manipulator import PacketManipulator
    HAS_PACKET = True
except ImportError:
    HAS_PACKET = False

try:
    from modules.cms_exploiter import CMSExploiter
    HAS_CMS = True
except ImportError:
    HAS_CMS = False

try:
    from modules.rate_limit_bypass import RateLimitBypass
    HAS_RLB = True
except ImportError:
    HAS_RLB = False

try:
    from modules.database_exploiter import DatabaseExploiter
    HAS_DB = True
except ImportError:
    HAS_DB = False

try:
    from modules.gearth_injector import GEarthInjector
    HAS_GEARTH = True
except ImportError:
    HAS_GEARTH = False

try:
    from modules.hotel_fingerprinter import HotelFingerprinter
    HAS_FINGERPRINTER = True
except ImportError:
    HAS_FINGERPRINTER = False

try:
    from modules.targeted_sqli import TargetedSQLi
    HAS_SQLI = True
except ImportError:
    HAS_SQLI = False

try:
    from modules.persistence import Persistence
    HAS_PERSISTENCE = True
except ImportError:
    HAS_PERSISTENCE = False

try:
    from modules.habbo_camera_exploit import HabboCameraExploit
    HAS_CAMERA = True
except ImportError:
    HAS_CAMERA = False

try:
    from modules.self_updater import SelfUpdater
    HAS_UPDATER = True
except ImportError:
    HAS_UPDATER = False

try:
    from utils.log_utils import Logger, LogLevel, LogManager
    from utils.network_utils import normalize_url, resolve_dns, get_public_ip
    HAS_UTILS = True
except ImportError:
    HAS_UTILS = False

try:
    from utils.attack_state import get_state, AttackState, reset_state
    HAS_STATE = True
except ImportError:
    HAS_STATE = False


# ========== Atak Zinciri Tanimi ==========
# Her tab: (index, name, module_key, prerequisites, auto_fields)
ATTACK_CHAIN = [
    (0,  "Hotel Fingerprint",  "fingerprinter", [], ["cms_type", "emulator_type", "origin_ips"]),
    (1,  "Cloudflare Bypass",  "cloudflare",    ["fingerprinter"], ["origin_ips", "cloudflare_detected"]),
    (2,  "Rate Limit Byp",     "rate_limit",    ["cloudflare"], ["origin_ips", "session_cookie"]),
    (3,  "Admin Extract",      "admin",         ["cloudflare"], ["admin_panels", "admin_credentials"]),
    (4,  "CMS Exploit",        "cms",           ["admin", "fingerprinter"], ["cms_type", "db_credentials"]),
    (5,  "Database Exploit",   "database",      ["cms"], ["db_credentials", "target_user", "new_rank"]),
    (6,  "Hotel Exploit",      "hotel_exploit", ["database"], ["sso_tokens", "target_user", "new_rank"]),
    (7,  "G-Earth Inject",     "gearth",        ["hotel_exploit"], ["sso_tokens", "gearth_ws_host", "gearth_ws_port"]),
    (8,  "Targeted SC",        "targeted_sqli", ["cms"], ["cms_type", "db_credentials"]),
    (9,  "Camera Expl",        "camera",        ["admin"], ["webshell_url"]),
    (10, "Persistent",         "persistence",   ["camera", "database"], ["webshell_url", "reverse_shell_active"]),
    (11, "Self-Update",        "updater",       [], []),
    (12, "Konsol",             "console",       [], []),
]


class ConsoleHandler:
    """Konsol ciktisini GUI'ye yonlendiren isleyici."""
    def __init__(self, text_widget: tk.Text, max_lines: int = 1000):
        self.text_widget = text_widget
        self.max_lines = max_lines
        self._lock = threading.Lock()

    def write(self, message: str) -> None:
        if not message.strip():
            return
        def _write():
            with self._lock:
                try:
                    self.text_widget.insert(tk.END, message + "\n")
                    lines = int(self.text_widget.index('end-1c').split('.')[0])
                    if lines > self.max_lines:
                        self.text_widget.delete('1.0', f'{lines - self.max_lines}.0')
                    self.text_widget.see(tk.END)
                except Exception:
                    pass
        if threading.current_thread() is threading.main_thread():
            _write()
        else:
            self.text_widget.after(0, _write)

    def flush(self):
        pass


class BenjiHabboHackGUI:
    """Benji Habbo Retros Hack v4.0 - State Machine GUI."""
    COLORS = {
        "bg_dark": "#1a1a2e",
        "bg_medium": "#16213e",
        "bg_light": "#0f3460",
        "accent": "#e94560",
        "accent_green": "#00ff88",
        "accent_yellow": "#ffd700",
        "accent_cyan": "#00d4ff",
        "text_primary": "#ffffff",
        "text_secondary": "#a0a0b0",
        "text_success": "#00ff88",
        "text_error": "#ff4444",
        "text_warning": "#ffd700",
    }

    def __init__(self, root: tk.Tk, initial_url: Optional[str] = None):
        self.root = root
        self.initial_url = initial_url or ""
        self.root.title("Benji Habbo Retros Hack v4.0 - State Machine")
        self.root.geometry("1450x920")
        self.root.minsize(1000, 700)
        try:
            self.root.iconbitmap(default="icon.ico")
        except Exception:
            pass

        # State sistemi
        if HAS_STATE:
            self.state = get_state()
            self.state.start_polling(interval=2.0)
        else:
            self.state = None

        self._setup_styles()
        self.target_url = tk.StringVar(value=self.initial_url)
        self.status_text = tk.StringVar(value="Hazir")
        self.is_running = False
        self._chain_running = False

        # Modul nesneleri
        self.cloudflare_bypass: Optional = None
        self.admin_extractor: Optional = None
        self.packet_manipulator: Optional = None
        self.cms_exploiter: Optional = None
        self.rate_limit_bypass: Optional = None
        self.database_exploiter: Optional = None
        self.gearth_injector: Optional = None
        self.hotel_fingerprinter: Optional = None
        self.targeted_sqli: Optional = None
        self.persistence: Optional = None
        self.habbo_camera: Optional = None
        self.self_updater: Optional = None

        # Tab index mapping
        self.tab_frames: Dict[str, tk.Frame] = {}
        self.tab_start_btns: Dict[str, tk.Button] = {}
        self.tab_result_texts: Dict[str, scrolledtext.ScrolledText] = {}
        self.tab_notebook_indices: Dict[str, int] = {}

        self._build_ui()
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)
        if self.initial_url:
            self.url_entry.delete(0, tk.END)
            self.url_entry.insert(0, self.initial_url)

        # State observer - tab durumlarini otomatik guncelle
        if self.state:
            self.state.observe_any(self._on_state_changed)

        # Ilk tab guncellemesi
        self.root.after(1000, self._refresh_all_tabs)

    def _setup_styles(self) -> None:
        style = ttk.Style()
        self.root.configure(bg=self.COLORS["bg_dark"])
        style.theme_use("clam")
        style.configure("TNotebook", background=self.COLORS["bg_dark"], foreground=self.COLORS["text_primary"], borderwidth=0)
        style.configure("TNotebook.Tab", background=self.COLORS["bg_medium"], foreground=self.COLORS["text_primary"], padding=[12, 5], borderwidth=0)
        style.map("TNotebook.Tab", background=[("selected", self.COLORS["bg_light"]), ("active", self.COLORS["accent"])], foreground=[("selected", self.COLORS["accent_cyan"])])
        style.configure("Accent.TButton", background=self.COLORS["accent"], foreground=self.COLORS["text_primary"], borderwidth=0, padding=[10, 5])
        style.map("Accent.TButton", background=[("active", "#ff6b81")])
        style.configure("Success.TButton", background="#00aa55", foreground=self.COLORS["text_primary"], borderwidth=0, padding=[10, 5])
        style.map("Success.TButton", background=[("active", "#00cc66")])
        style.configure("Danger.TButton", background=self.COLORS["text_error"], foreground=self.COLORS["text_primary"], borderwidth=0, padding=[10, 5])
        style.map("Danger.TButton", background=[("active", "#ff6666")])
        style.configure("Chain.TButton", background="#ff8c00", foreground=self.COLORS["text_primary"], borderwidth=0, padding=[10, 5])
        style.map("Chain.TButton", background=[("active", "#ffa500")])

    def _build_ui(self) -> None:
        main_container = tk.Frame(self.root, bg=self.COLORS["bg_dark"])
        main_container.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        self._build_top_bar(main_container)
        self._build_tab_panel(main_container)
        self._build_status_bar(main_container)

    def _build_top_bar(self, parent: tk.Frame) -> None:
        top_frame = tk.Frame(parent, bg=self.COLORS["bg_dark"])
        top_frame.pack(fill=tk.X, pady=(0, 5))
        title_label = tk.Label(top_frame, text="Benji Habbo Retros Hack v4.0", font=("Consolas", 16, "bold"), fg=self.COLORS["accent"], bg=self.COLORS["bg_dark"])
        title_label.pack(side=tk.LEFT, padx=(0, 20))
        url_frame = tk.Frame(top_frame, bg=self.COLORS["bg_dark"])
        url_frame.pack(side=tk.LEFT, fill=tk.X, expand=True)
        url_label = tk.Label(url_frame, text="Hedef URL:", font=("Consolas", 10), fg=self.COLORS["text_secondary"], bg=self.COLORS["bg_dark"])
        url_label.pack(side=tk.LEFT, padx=(0, 5))
        self.url_entry = tk.Entry(url_frame, textvariable=self.target_url, font=("Consolas", 10), bg=self.COLORS["bg_medium"], fg=self.COLORS["text_primary"], insertbackground=self.COLORS["accent_cyan"], relief="flat", bd=3)
        self.url_entry.pack(side=tk.LEFT, fill=tk.X, expand=True, ipady=3)
        btn_frame = tk.Frame(top_frame, bg=self.COLORS["bg_dark"])
        btn_frame.pack(side=tk.RIGHT, padx=(10, 0))
        self.chain_run_btn = tk.Button(btn_frame, text=">>> Zincirleme Calistir", font=("Consolas", 9, "bold"), bg="#ff8c00", fg=self.COLORS["text_primary"], relief="flat", padx=10, pady=3, cursor="hand2", command=self._run_chain)
        self.chain_run_btn.pack(side=tk.LEFT, padx=2)
        self.start_all_btn = tk.Button(btn_frame, text=">>> Tumunu Baslat", font=("Consolas", 9, "bold"), bg="#00aa55", fg=self.COLORS["text_primary"], relief="flat", padx=10, pady=3, cursor="hand2", command=self._run_all_modules)
        self.start_all_btn.pack(side=tk.LEFT, padx=2)
        self.stop_btn = tk.Button(btn_frame, text="XXX Durdur", font=("Consolas", 9, "bold"), bg=self.COLORS["text_error"], fg=self.COLORS["text_primary"], relief="flat", padx=10, pady=3, cursor="hand2", state=tk.DISABLED, command=self._stop_all)
        self.stop_btn.pack(side=tk.LEFT, padx=2)
        self.clear_btn = tk.Button(btn_frame, text="Temizle", font=("Consolas", 9), bg=self.COLORS["bg_light"], fg=self.COLORS["text_secondary"], relief="flat", padx=10, pady=3, cursor="hand2", command=self._clear_console)
        self.clear_btn.pack(side=tk.LEFT, padx=2)

    def _build_tab_panel(self, parent: tk.Frame) -> None:
        self.notebook = ttk.Notebook(parent)
        self.notebook.pack(fill=tk.BOTH, expand=True)

        # Tabs are built in ATTACK_CHAIN order
        for idx, name, module_key, prereqs, auto_fields in ATTACK_CHAIN:
            tab = tk.Frame(self.notebook, bg=self.COLORS["bg_medium"])
            self.notebook.add(tab, text=f"  {name}  ")
            self.tab_frames[module_key] = tab
            self.tab_notebook_indices[module_key] = idx

            # Build the tab content based on module_key
            builder_method = f"_build_tab_{module_key}"
            if hasattr(self, builder_method):
                getattr(self, builder_method)(tab, module_key, name)

    def _build_tab_generic(self, parent: tk.Frame, module_key: str, title: str,
                           params_config: List[Dict], info_text: str = "") -> None:
        """Generic tab builder - sol tarafta parametreler, sag tarafta sonuclar."""
        left_frame = tk.Frame(parent, bg=self.COLORS["bg_medium"])
        left_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=5, pady=5)
        params_frame = tk.LabelFrame(left_frame, text=f"{title} Ayarlari", font=("Consolas", 10, "bold"), fg=self.COLORS["accent_cyan"], bg=self.COLORS["bg_medium"], relief="flat")
        params_frame.pack(fill=tk.X, pady=(0, 10))

        if info_text:
            tk.Label(params_frame, text=info_text, font=("Consolas", 9), fg=self.COLORS["text_secondary"], bg=self.COLORS["bg_medium"], justify=tk.LEFT).pack(anchor="w", pady=5, padx=5)

        # Parametre alanlarini olustur
        for cfg in params_config:
            row = tk.Frame(params_frame, bg=self.COLORS["bg_medium"])
            row.pack(fill=tk.X, pady=2)
            label_text = cfg.get("label", "")
            label_width = cfg.get("label_width", 15)
            tk.Label(row, text=label_text, font=("Consolas", 9), fg=self.COLORS["text_secondary"], bg=self.COLORS["bg_medium"], width=label_width, anchor="w").pack(side=tk.LEFT)

            field_type = cfg.get("type", "entry")
            field_key = cfg.get("key", "")
            default_val = cfg.get("default", "")
            state_key = cfg.get("state_key", "")

            if field_type == "entry":
                entry = tk.Entry(row, font=("Consolas", 9), bg=self.COLORS["bg_dark"], fg=self.COLORS["text_primary"], relief="flat", bd=2)
                entry.insert(0, str(default_val))
                entry.pack(side=tk.LEFT, fill=tk.X, expand=True, ipady=2)
                setattr(self, f"{module_key}_{field_key}", entry)
            elif field_type == "spinbox":
                from_val = cfg.get("from", 1)
                to_val = cfg.get("to", 10)
                spin = tk.Spinbox(row, from_=from_val, to=to_val, font=("Consolas", 9), bg=self.COLORS["bg_dark"], fg=self.COLORS["text_primary"], relief="flat", bd=2, width=10)
                spin.delete(0, tk.END)
                spin.insert(0, str(default_val))
                spin.pack(side=tk.LEFT, padx=5)
                setattr(self, f"{module_key}_{field_key}", spin)
            elif field_type == "checkbox":
                var = tk.BooleanVar(value=default_val)
                cb = tk.Checkbutton(row, text=label_text, variable=var, font=("Consolas", 9), fg=self.COLORS["text_primary"], bg=self.COLORS["bg_medium"], selectcolor=self.COLORS["bg_dark"], activebackground=self.COLORS["bg_medium"], activeforeground=self.COLORS["text_primary"])
                cb.pack(anchor="w", pady=2)
                setattr(self, f"{module_key}_{field_key}", var)
                # Checkbox icin label'i bos goster
                for child in row.winfo_children():
                    if isinstance(child, tk.Label):
                        child.config(text="")
            elif field_type == "combobox":
                values = cfg.get("values", [])
                var = tk.StringVar(value=str(default_val))
                combo = ttk.Combobox(row, textvariable=var, values=values, font=("Consolas", 9), state="readonly", width=15)
                combo.pack(side=tk.LEFT, padx=5)
                setattr(self, f"{module_key}_{field_key}", var)

        # Baslat butonu
        btn_frame = tk.Frame(params_frame, bg=self.COLORS["bg_medium"])
        btn_frame.pack(fill=tk.X, pady=(10, 5))
        start_btn = tk.Button(btn_frame, text=f"{title}'i Baslat", font=("Consolas", 10, "bold"), bg="#00aa55", fg=self.COLORS["text_primary"], relief="flat", padx=15, pady=5, cursor="hand2")
        run_method_name = f"_run_{module_key}"
        if hasattr(self, run_method_name):
            start_btn.config(command=getattr(self, run_method_name))
        start_btn.pack(side=tk.LEFT, padx=5)
        self.tab_start_btns[module_key] = start_btn

        # Sag taraftaki sonuc alani
        right_frame = tk.Frame(parent, bg=self.COLORS["bg_medium"])
        right_frame.pack(side=tk.RIGHT, fill=tk.BOTH, expand=True, padx=5, pady=5)
        results_frame = tk.LabelFrame(right_frame, text=f"{title} Sonuclari", font=("Consolas", 10, "bold"), fg=self.COLORS["accent_cyan"], bg=self.COLORS["bg_medium"], relief="flat")
        results_frame.pack(fill=tk.BOTH, expand=True)
        result_text = scrolledtext.ScrolledText(results_frame, font=("Consolas", 9), bg=self.COLORS["bg_dark"], fg=self.COLORS["text_primary"], insertbackground=self.COLORS["accent_cyan"], relief="flat", bd=2, height=15)
        result_text.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        self.tab_result_texts[module_key] = result_text

    # ========== Tab Builder'lar ==========
    def _build_tab_fingerprinter(self, parent, module_key, title):
        self._build_tab_generic(parent, module_key, title, [
            {"label": "Zaman Asimi (sn):", "key": "timeout", "type": "spinbox", "from": 10, "to": 120, "default": 60},
        ], info_text="Hedef: CMS ve Emulator tespiti\nAnaliz: Sayfa kaynagi, CSS, JS, Hata mesajlari\nTespit: RevCMS, AtomCMS, PhoenixPHP, UberCMS, CycloneCMS\n         Arcturus, PlusEMU, Comet, Phoenix, UberEmu")

    def _build_tab_cloudflare(self, parent, module_key, title):
        self._build_tab_generic(parent, module_key, title, [
            {"label": "DNS Sunucu:", "key": "dns", "type": "entry", "default": "8.8.8.8"},
            {"label": "Zaman Asimi (sn):", "key": "timeout", "type": "spinbox", "from": 5, "to": 120, "default": 60},
        ], info_text="Cloudflare bypass: DNS history, SSL CT logs, favicon hash\nHost header spoofing, subdomain enumeration")

    def _build_tab_rate_limit(self, parent, module_key, title):
        self._build_tab_generic(parent, module_key, title, [
            {"label": "", "key": "proxy", "type": "checkbox", "default": True},
            {"label": "", "key": "flaresolverr", "type": "checkbox", "default": False},
            {"label": "Zaman Asimi (sn):", "key": "timeout", "type": "spinbox", "from": 10, "to": 120, "default": 60},
        ], info_text="Rate limit bypass: Proxy rotasyonu, FlareSolverr\nCloudflare challenge cozumu, exponential backoff")

    def _build_tab_admin(self, parent, module_key, title):
        self._build_tab_generic(parent, module_key, title, [
            {"label": "", "key": "scan", "type": "checkbox", "default": True},
            {"label": "", "key": "bruteforce", "type": "checkbox", "default": True},
            {"label": "", "key": "configs", "type": "checkbox", "default": True},
            {"label": "", "key": "sqli", "type": "checkbox", "default": True},
            {"label": "Zaman Asimi (sn):", "key": "timeout", "type": "spinbox", "from": 10, "to": 300, "default": 60},
        ], info_text="Admin panel tarama: HEAD istekleri ile hizli tarama\nX-Forwarded-For IP spoofing, default credential test")

    def _build_tab_cms(self, parent, module_key, title):
        self._build_tab_generic(parent, module_key, title, [
            {"label": "Zaman Asimi (sn):", "key": "timeout", "type": "spinbox", "from": 10, "to": 120, "default": 60},
        ], info_text="Hedef: AtomCMS, RevCMS, PhoenixPHP, UberCMS\nTest: SQLi, RCE, SSO Extraction, Admin Bypass")

    def _build_tab_database(self, parent, module_key, title):
        self._build_tab_generic(parent, module_key, title, [
            {"label": "DB Host:", "key": "host", "type": "entry", "default": "localhost"},
            {"label": "DB Port:", "key": "port", "type": "spinbox", "from": 3306, "to": 9999, "default": 3306},
            {"label": "DB Kullanici:", "key": "user", "type": "entry", "default": "root"},
            {"label": "DB Sifre:", "key": "pass", "type": "entry", "default": ""},
            {"label": "DB Adi:", "key": "name", "type": "entry", "default": ""},
            {"label": "Hedef Kullanici:", "key": "target_user", "type": "entry", "default": ""},
            {"label": "Yeni Rank:", "key": "rank", "type": "spinbox", "from": 1, "to": 10, "default": 7},
            {"label": "", "key": "create_admin", "type": "checkbox", "default": False},
            {"label": "Zaman Asimi (sn):", "key": "timeout", "type": "spinbox", "from": 10, "to": 120, "default": 60},
        ], info_text="Database exploitation: MySQL baglantisi, rank/credit degistirme\nSSO token olusturma, admin kullanici ekleme")

    def _build_tab_hotel_exploit(self, parent, module_key, title):
        self._build_tab_generic(parent, module_key, title, [
            {"label": "", "key": "modify_rank", "type": "checkbox", "default": True},
            {"label": "Yeni Rank:", "key": "rank", "type": "spinbox", "from": 1, "to": 10, "default": 7},
            {"label": "", "key": "modify_credits", "type": "checkbox", "default": True},
            {"label": "Kredi Miktari:", "key": "credits", "type": "entry", "default": "999999"},
            {"label": "", "key": "modify_pixels", "type": "checkbox", "default": True},
            {"label": "", "key": "modify_diamonds", "type": "checkbox", "default": True},
        ], info_text="Hotel exploitation: SSO token extraction, rank manipulation\nAPI exploitation, currency modification")

    def _build_tab_gearth(self, parent, module_key, title):
        self._build_tab_generic(parent, module_key, title, [
            {"label": "SSO Token:", "key": "sso", "type": "entry", "default": ""},
            {"label": "Hedef Kullanici:", "key": "target_user", "type": "entry", "default": ""},
            {"label": "Yeni Rank:", "key": "rank", "type": "spinbox", "from": 1, "to": 10, "default": 7},
            {"label": "WS Host (ops):", "key": "ws_host", "type": "entry", "default": ""},
            {"label": "WS Port (ops):", "key": "ws_port", "type": "spinbox", "from": 1, "to": 65535, "default": 30000},
            {"label": "Zaman Asimi (sn):", "key": "timeout", "type": "spinbox", "from": 10, "to": 120, "default": 60},
        ], info_text="G-Earth/Xabbo packet injection: SSO login, rank change\nSerialization packet, MITM proxy, emulator detection")

    def _build_tab_targeted_sqli(self, parent, module_key, title):
        self._build_tab_generic(parent, module_key, title, [
            {"label": "CMS ID (ops):", "key": "cms_id", "type": "entry", "default": ""},
            {"label": "Zaman Asimi (sn):", "key": "timeout", "type": "spinbox", "from": 10, "to": 120, "default": 60},
        ], info_text="Hedef CMS'ler: RevCMS, PhoenixPHP, AtomCMS, UberCMS\nPayload: Time-based blind SQLi, Error-based SQLi\nOutput: Admin session cookies, DB credentials")

    def _build_tab_camera(self, parent, module_key, title):
        self._build_tab_generic(parent, module_key, title, [
            {"label": "Zaman Asimi (sn):", "key": "timeout", "type": "spinbox", "from": 10, "to": 120, "default": 60},
        ], info_text="Habbo Camera SWF upload exploit\n32 camera endpoint, path traversal, SSRF\nMalicious SWF ile PHP webshell yukleme")

    def _build_tab_persistence(self, parent, module_key, title):
        self._build_tab_generic(parent, module_key, title, [
            {"label": "Admin Cookie:", "key": "cookie", "type": "entry", "default": ""},
            {"label": "Reverse Host:", "key": "rev_host", "type": "entry", "default": ""},
            {"label": "Reverse Port:", "key": "rev_port", "type": "spinbox", "from": 1, "to": 65535, "default": 4444},
            {"label": "Discord WH:", "key": "discord", "type": "entry", "default": ""},
            {"label": "Zaman Asimi (sn):", "key": "timeout", "type": "spinbox", "from": 10, "to": 120, "default": 60},
        ], info_text="Persistence: Webshell yukleme, reverse shell\nCron-job re-exploitation, Discord monitoring")

    def _build_tab_updater(self, parent, module_key, title):
        self._build_tab_generic(parent, module_key, title, [
            {"label": "Mod:", "key": "mode", "type": "combobox", "values": ["check", "update", "train"], "default": "check"},
        ], info_text="Guncelleme kontrolu ve otomatik guncelleme\nAES-256-GCM sifreli iletisim, egitim modu")

    def _build_tab_console(self, parent, module_key, title):
        main_frame = tk.Frame(parent, bg=self.COLORS["bg_medium"])
        main_frame.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        console_frame = tk.LabelFrame(main_frame, text="Genel Konsol Ciktisi", font=("Consolas", 10, "bold"), fg=self.COLORS["accent_cyan"], bg=self.COLORS["bg_medium"], relief="flat")
        console_frame.pack(fill=tk.BOTH, expand=True)
        self.console_text = scrolledtext.ScrolledText(console_frame, font=("Consolas", 9), bg=self.COLORS["bg_dark"], fg=self.COLORS["text_primary"], insertbackground=self.COLORS["accent_cyan"], relief="flat", bd=2)
        self.console_text.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        btn_frame = tk.Frame(main_frame, bg=self.COLORS["bg_medium"])
        btn_frame.pack(fill=tk.X, pady=(5, 0))
        self.console_handler = ConsoleHandler(self.console_text)
        save_btn = tk.Button(btn_frame, text="Log Kaydet", font=("Consolas", 9), bg=self.COLORS["bg_light"], fg=self.COLORS["text_secondary"], relief="flat", padx=10, pady=3, cursor="hand2", command=self._save_log)
        save_btn.pack(side=tk.LEFT, padx=2)
        self.tab_result_texts["console"] = self.console_text

    # ========== Status Bar ==========
    def _build_status_bar(self, parent: tk.Frame) -> None:
        status_frame = tk.Frame(parent, bg=self.COLORS["bg_dark"])
        status_frame.pack(fill=tk.X, pady=(5, 0))
        self.status_label = tk.Label(status_frame, textvariable=self.status_text, font=("Consolas", 9), fg=self.COLORS["text_secondary"], bg=self.COLORS["bg_dark"], anchor="w")
        self.status_label.pack(side=tk.LEFT, padx=5)
        self.time_label = tk.Label(status_frame, text="", font=("Consolas", 9), fg=self.COLORS["text_secondary"], bg=self.COLORS["bg_dark"], anchor="e")
        self.time_label.pack(side=tk.RIGHT, padx=5)
        self._update_time()

    def _update_time(self) -> None:
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        self.time_label.config(text=now)
        self.root.after(1000, self._update_time)

    # ========== GUI Logger ==========
    def _gui_log(self, level: str, message: str, target: str = "console") -> None:
        widget = self.tab_result_texts.get(target, self.console_text)
        colors = {"INFO": self.COLORS["accent_cyan"], "SUCCESS": self.COLORS["text_success"], "WARNING": self.COLORS["text_warning"], "ERROR": self.COLORS["text_error"], "DEBUG": self.COLORS["text_secondary"]}
        color = colors.get(level.upper(), self.COLORS["text_primary"])
        timestamp = datetime.now().strftime("%H:%M:%S")
        tag_name = f"tag_{timestamp}_{level}"
        def _write():
            try:
                widget.tag_configure(tag_name, foreground=color)
                widget.insert(tk.END, f"[{timestamp}] [{level}] {message}\n", tag_name)
                widget.see(tk.END)
            except Exception:
                pass
        if threading.current_thread() is threading.main_thread():
            _write()
        else:
            self.root.after(0, _write)

    def _parse_gui_callback(self, msg: str, target: str) -> None:
        """Modul callback'lerinden gelen tek-string mesaji ayristirip _gui_log'a yonlendir."""
        if not msg or not isinstance(msg, str):
            return
        if msg.startswith("[") and "]" in msg:
            try:
                close_bracket = msg.index("]")
                level = msg[1:close_bracket].strip()
                message = msg[close_bracket+1:].strip()
                self._gui_log(level, message, target)
            except Exception:
                self._gui_log("INFO", msg, target)
        else:
            self._gui_log("INFO", msg, target)

    def _clear_console(self) -> None:
        """Tum sonuc alanlarini temizle."""
        for key, widget in self.tab_result_texts.items():
            try:
                widget.delete("1.0", tk.END)
            except Exception:
                pass
        self._gui_log("INFO", "Tum konsol ciktisi temizlendi.", "console")

    def _save_log(self) -> None:
        """Konsol ciktisini dosyaya kaydet."""
        try:
            filepath = filedialog.asksaveasfilename(
                defaultextension=".txt",
                filetypes=[("Text files", "*.txt"), ("All files", "*.*")],
                title="Log Dosyasini Kaydet"
            )
            if filepath:
                content = self.console_text.get("1.0", tk.END)
                with open(filepath, "w", encoding="utf-8") as f:
                    f.write(content)
                self._gui_log("SUCCESS", f"Log kaydedildi: {filepath}", "console")
        except Exception as e:
            self._gui_log("ERROR", f"Log kaydedilemedi: {e}", "console")

    def _set_running(self, running: bool) -> None:
        """UI durumunu running/stopped olarak ayarla."""
        self.is_running = running
        if running:
            self.start_all_btn.config(state=tk.DISABLED)
            self.chain_run_btn.config(state=tk.DISABLED)
            self.stop_btn.config(state=tk.NORMAL)
            self.status_text.set("Calisiyor...")
            for btn in self.tab_start_btns.values():
                btn.config(state=tk.DISABLED)
        else:
            self.start_all_btn.config(state=tk.NORMAL)
            self.chain_run_btn.config(state=tk.NORMAL)
            self.stop_btn.config(state=tk.DISABLED)
            self.status_text.set("Hazir")
            for btn in self.tab_start_btns.values():
                btn.config(state=tk.NORMAL)

    def _stop_all(self) -> None:
        """Tum calisan modulleri durdur."""
        self._gui_log("WARNING", "Tum moduller durduruluyor...", "console")
        self._chain_running = False
        modules_to_stop = [
            ("cloudflare_bypass", self.cloudflare_bypass),
            ("admin_extractor", self.admin_extractor),
            ("packet_manipulator", self.packet_manipulator),
            ("cms_exploiter", self.cms_exploiter),
            ("rate_limit_bypass", self.rate_limit_bypass),
            ("database_exploiter", self.database_exploiter),
            ("gearth_injector", self.gearth_injector),
            ("hotel_fingerprinter", self.hotel_fingerprinter),
            ("targeted_sqli", self.targeted_sqli),
            ("persistence", self.persistence),
            ("habbo_camera", self.habbo_camera),
            ("self_updater", self.self_updater),
        ]
        for name, module in modules_to_stop:
            if module and hasattr(module, 'stop'):
                try:
                    module.stop()
                    self._gui_log("INFO", f"{name} durduruldu.", "console")
                except Exception as e:
                    self._gui_log("ERROR", f"{name} durdurulamadi: {e}", "console")
        self._set_running(False)
        self._gui_log("SUCCESS", "Tum moduller durduruldu.", "console")

    def _on_close(self) -> None:
        """Pencere kapatilirken temizlik."""
        self._stop_all()
        if self.state and hasattr(self.state, 'stop_polling'):
            try:
                self.state.stop_polling()
            except Exception:
                pass
        self.root.destroy()

    def _on_state_changed(self, key: str, value: Any) -> None:
        """State degisikliklerini UI'a yansit."""
        try:
            if key == "module_status" or key.startswith("module_status"):
                for module_key, status in (value.items() if isinstance(value, dict) else {}).items():
                    btn = self.tab_start_btns.get(module_key)
                    if btn:
                        status_colors = {
                            "pending": self.COLORS["text_secondary"],
                            "running": self.COLORS["accent_yellow"],
                            "success": self.COLORS["text_success"],
                            "failed": self.COLORS["text_error"],
                            "skipped": self.COLORS["text_secondary"],
                        }
                        color = status_colors.get(status, self.COLORS["text_secondary"])
                        try:
                            btn.config(fg=color)
                        except Exception:
                            pass
            if key in ("target_user", "new_rank", "sso_tokens", "gearth_ws_host", "gearth_ws_port",
                       "cms_type", "origin_ips", "db_credentials", "admin_panels", "session_cookie"):
                self.root.after(0, self._refresh_all_tabs)
        except Exception:
            pass

    def _refresh_all_tabs(self) -> None:
        """State'ten gelen verilerle tum tab alanlarini guncelle."""
        if not self.state:
            self.root.after(2000, self._refresh_all_tabs)
            return
        try:
            state_data = self.state.get_all()
            for idx, name, module_key, prereqs, auto_fields in ATTACK_CHAIN:
                if module_key == "console":
                    continue
                btn = self.tab_start_btns.get(module_key)
                if not btn:
                    continue
                if self.is_running:
                    continue
                all_met = True
                for prereq in prereqs:
                    prereq_status = state_data.get("module_status", {}).get(prereq, "pending")
                    if prereq_status != "success":
                        all_met = False
                        break
                if all_met:
                    btn.config(state=tk.NORMAL, bg="#00aa55")
                else:
                    btn.config(state=tk.DISABLED, bg=self.COLORS["bg_light"])

            # Auto-fill fields from state
            sso_entry = getattr(self, "gearth_sso", None)
            if sso_entry and state_data.get("sso_tokens"):
                tokens = state_data["sso_tokens"]
                if isinstance(tokens, list) and tokens:
                    current = sso_entry.get()
                    if not current:
                        sso_entry.delete(0, tk.END)
                        sso_entry.insert(0, tokens[0])

            target_entry = getattr(self, "gearth_target_user", None)
            if target_entry and state_data.get("target_user"):
                current = target_entry.get()
                if not current:
                    target_entry.delete(0, tk.END)
                    target_entry.insert(0, str(state_data["target_user"]))

            rank_spin = getattr(self, "gearth_rank", None)
            if rank_spin and state_data.get("new_rank"):
                current = rank_spin.get()
                if not current or current == "7":
                    rank_spin.delete(0, tk.END)
                    rank_spin.insert(0, str(state_data["new_rank"]))

            ws_host_entry = getattr(self, "gearth_ws_host", None)
            if ws_host_entry and state_data.get("gearth_ws_host"):
                current = ws_host_entry.get()
                if not current:
                    ws_host_entry.delete(0, tk.END)
                    ws_host_entry.insert(0, str(state_data["gearth_ws_host"]))

            ws_port_spin = getattr(self, "gearth_ws_port", None)
            if ws_port_spin and state_data.get("gearth_ws_port"):
                current = ws_port_spin.get()
                if not current or current == "30000":
                    ws_port_spin.delete(0, tk.END)
                    ws_port_spin.insert(0, str(state_data["gearth_ws_port"]))

            db_host = getattr(self, "database_host", None)
            if db_host and state_data.get("db_credentials", {}).get("host"):
                current = db_host.get()
                if not current or current == "localhost":
                    db_host.delete(0, tk.END)
                    db_host.insert(0, str(state_data["db_credentials"]["host"]))

            db_user = getattr(self, "database_user", None)
            if db_user and state_data.get("db_credentials", {}).get("user"):
                current = db_user.get()
                if not current or current == "root":
                    db_user.delete(0, tk.END)
                    db_user.insert(0, str(state_data["db_credentials"]["user"]))

            db_pass = getattr(self, "database_pass", None)
            if db_pass and state_data.get("db_credentials", {}).get("password"):
                current = db_pass.get()
                if not current:
                    db_pass.delete(0, tk.END)
                    db_pass.insert(0, str(state_data["db_credentials"]["password"]))

            db_name = getattr(self, "database_name", None)
            if db_name and state_data.get("db_credentials", {}).get("database"):
                current = db_name.get()
                if not current:
                    db_name.delete(0, tk.END)
                    db_name.insert(0, str(state_data["db_credentials"]["database"]))

            db_target = getattr(self, "database_target_user", None)
            if db_target and state_data.get("target_user"):
                current = db_target.get()
                if not current:
                    db_target.delete(0, tk.END)
                    db_target.insert(0, str(state_data["target_user"]))

            db_rank = getattr(self, "database_rank", None)
            if db_rank and state_data.get("new_rank"):
                current = db_rank.get()
                if not current or current == "7":
                    db_rank.delete(0, tk.END)
                    db_rank.insert(0, str(state_data["new_rank"]))

            pers_cookie = getattr(self, "persistence_cookie", None)
            if pers_cookie and state_data.get("session_cookie"):
                current = pers_cookie.get()
                if not current:
                    pers_cookie.delete(0, tk.END)
                    pers_cookie.insert(0, str(state_data["session_cookie"]))
        except Exception:
            pass
        self.root.after(2000, self._refresh_all_tabs)

    # ========== Run Methods ==========

    def _run_fingerprinter(self) -> None:
        if not HAS_FINGERPRINTER:
            self._gui_log("ERROR", "HotelFingerprinter modulu yuklu degil!", "fingerprinter")
            return
        target = self.target_url.get().strip()
        if not target:
            self._gui_log("ERROR", "Lutfen bir hedef URL girin!", "fingerprinter")
            return
        timeout = int(getattr(self, "fingerprinter_timeout", tk.StringVar(value="60")).get())
        self._set_running(True)
        self.state.set_module_status("fingerprinter", "running")
        self.state.set("target_url", target)
        self._gui_log("INFO", f"Hotel Fingerprint baslatiliyor: {target}", "fingerprinter")

        def _run():
            try:
                self.hotel_fingerprinter = HotelFingerprinter(target, gui_callback=lambda msg: self._parse_gui_callback(msg, "fingerprinter"))
                result = self.hotel_fingerprinter.run(timeout=timeout)
                if result:
                    cms_type = result.get("cms_type")
                    cms_conf = result.get("cms_confidence", 0.0)
                    emu_type = result.get("emulator_type")
                    emu_conf = result.get("emulator_confidence", 0.0)
                    origin_ips = result.get("origin_ips", [])
                    self.state.update({
                        "cms_type": cms_type,
                        "cms_confidence": cms_conf,
                        "emulator_type": emu_type,
                        "emulator_confidence": emu_conf,
                        "origin_ips": origin_ips,
                    })
                    self._gui_log("SUCCESS", f"CMS: {cms_type} (conf: {cms_conf:.1f})", "fingerprinter")
                    self._gui_log("SUCCESS", f"Emulator: {emu_type} (conf: {emu_conf:.1f})", "fingerprinter")
                    if origin_ips:
                        self._gui_log("SUCCESS", f"Origin IP'ler: {', '.join(origin_ips)}", "fingerprinter")
                    self.state.set_module_status("fingerprinter", "success")
                else:
                    self.state.set_module_status("fingerprinter", "failed")
                    self._gui_log("ERROR", "Fingerprint basarisiz.", "fingerprinter")
            except Exception as e:
                self.state.set_module_status("fingerprinter", "failed")
                self._gui_log("ERROR", f"Hata: {e}", "fingerprinter")
            finally:
                self.root.after(0, lambda: self._set_running(False))

        threading.Thread(target=_run, daemon=True).start()

    def _run_cloudflare(self) -> None:
        if not HAS_CLOUDFLARE:
            self._gui_log("ERROR", "CloudflareBypass modulu yuklu degil!", "cloudflare")
            return
        target = self.target_url.get().strip()
        if not target:
            self._gui_log("ERROR", "Lutfen bir hedef URL girin!", "cloudflare")
            return
        dns = getattr(self, "cloudflare_dns", None)
        dns_server = dns.get().strip() if dns else "8.8.8.8"
        timeout = int(getattr(self, "cloudflare_timeout", tk.StringVar(value="60")).get())
        self._set_running(True)
        self.state.set_module_status("cloudflare", "running")
        self._gui_log("INFO", f"Cloudflare bypass baslatiliyor: {target}", "cloudflare")

        def _run():
            try:
                self.cloudflare_bypass = CloudflareBypass(target, gui_callback=lambda msg: self._parse_gui_callback(msg, "cloudflare"))
                result = self.cloudflare_bypass.run(dns_server=dns_server, timeout=timeout)
                if result:
                    origin_ips = result.get("origin_ips", [])
                    cf_detected = result.get("cloudflare_detected", False)
                    cf_bypassed = result.get("cloudflare_bypassed", False)
                    self.state.update({
                        "origin_ips": origin_ips,
                        "cloudflare_detected": cf_detected,
                        "cloudflare_bypassed": cf_bypassed,
                    })
                    if cf_bypassed:
                        self._gui_log("SUCCESS", "Cloudflare bypass basarili!", "cloudflare")
                    if origin_ips:
                        self._gui_log("SUCCESS", f"Origin IP'ler: {', '.join(origin_ips[:5])}", "cloudflare")
                    self.state.set_module_status("cloudflare", "success")
                else:
                    self.state.set_module_status("cloudflare", "failed")
                    self._gui_log("ERROR", "Cloudflare bypass basarisiz.", "cloudflare")
            except Exception as e:
                self.state.set_module_status("cloudflare", "failed")
                self._gui_log("ERROR", f"Hata: {e}", "cloudflare")
            finally:
                self.root.after(0, lambda: self._set_running(False))

        threading.Thread(target=_run, daemon=True).start()

    def _run_rate_limit(self) -> None:
        if not HAS_RLB:
            self._gui_log("ERROR", "RateLimitBypass modulu yuklu degil!", "rate_limit")
            return
        target = self.target_url.get().strip()
        if not target:
            self._gui_log("ERROR", "Lutfen bir hedef URL girin!", "rate_limit")
            return
        use_proxy = getattr(self, "rate_limit_proxy", None)
        use_proxy_val = use_proxy.get() if use_proxy else True
        use_flare = getattr(self, "rate_limit_flaresolverr", None)
        use_flare_val = use_flare.get() if use_flare else False
        timeout = int(getattr(self, "rate_limit_timeout", tk.StringVar(value="60")).get())
        self._set_running(True)
        self.state.set_module_status("rate_limit", "running")
        self._gui_log("INFO", f"Rate limit bypass baslatiliyor: {target}", "rate_limit")

        def _run():
            try:
                self.rate_limit_bypass = RateLimitBypass(target, gui_callback=lambda msg: self._parse_gui_callback(msg, "rate_limit"))
                result = self.rate_limit_bypass.run(use_proxy=use_proxy_val, use_flaresolverr=use_flare_val, timeout=timeout)
                if result:
                    session_cookie = result.get("session_cookie")
                    proxy_status = result.get("proxy_pool_status")
                    self.state.update({
                        "session_cookie": session_cookie,
                        "proxy_pool_status": proxy_status,
                    })
                    if session_cookie:
                        self._gui_log("SUCCESS", f"Session cookie alindi: {session_cookie[:50]}...", "rate_limit")
                    self.state.set_module_status("rate_limit", "success")
                else:
                    self.state.set_module_status("rate_limit", "failed")
                    self._gui_log("ERROR", "Rate limit bypass basarisiz.", "rate_limit")
            except Exception as e:
                self.state.set_module_status("rate_limit", "failed")
                self._gui_log("ERROR", f"Hata: {e}", "rate_limit")
            finally:
                self.root.after(0, lambda: self._set_running(False))

        threading.Thread(target=_run, daemon=True).start()

    def _run_admin(self) -> None:
        if not HAS_ADMIN:
            self._gui_log("ERROR", "AdminExtractor modulu yuklu degil!", "admin")
            return
        target = self.target_url.get().strip()
        if not target:
            self._gui_log("ERROR", "Lutfen bir hedef URL girin!", "admin")
            return
        scan = getattr(self, "admin_scan", None)
        scan_val = scan.get() if scan else True
        bruteforce = getattr(self, "admin_bruteforce", None)
        bruteforce_val = bruteforce.get() if bruteforce else True
        configs = getattr(self, "admin_configs", None)
        configs_val = configs.get() if configs else True
        sqli = getattr(self, "admin_sqli", None)
        sqli_val = sqli.get() if sqli else True
        timeout = int(getattr(self, "admin_timeout", tk.StringVar(value="60")).get())
        self._set_running(True)
        self.state.set_module_status("admin", "running")
        self._gui_log("INFO", f"Admin extraction baslatiliyor: {target}", "admin")

        def _run():
            try:
                self.admin_extractor = AdminExtractor(target, gui_callback=lambda msg: self._parse_gui_callback(msg, "admin"))
                result = self.admin_extractor.run(scan_admin=scan_val, bruteforce=bruteforce_val, scan_configs=configs_val, test_sqli=sqli_val, timeout=timeout)
                if result:
                    panels = result.get("admin_panels", [])
                    creds = result.get("admin_credentials", {})
                    self.state.update({
                        "admin_panels": panels,
                        "admin_credentials": creds,
                    })
                    if panels:
                        self._gui_log("SUCCESS", f"Admin panelleri: {', '.join(panels[:5])}", "admin")
                    if creds:
                        self._gui_log("SUCCESS", f"Admin kredensiyelleri bulundu!", "admin")
                    self.state.set_module_status("admin", "success")
                else:
                    self.state.set_module_status("admin", "failed")
                    self._gui_log("ERROR", "Admin extraction basarisiz.", "admin")
            except Exception as e:
                self.state.set_module_status("admin", "failed")
                self._gui_log("ERROR", f"Hata: {e}", "admin")
            finally:
                self.root.after(0, lambda: self._set_running(False))

        threading.Thread(target=_run, daemon=True).start()

    def _run_cms(self) -> None:
        if not HAS_CMS:
            self._gui_log("ERROR", "CMSExploiter modulu yuklu degil!", "cms")
            return
        target = self.target_url.get().strip()
        if not target:
            self._gui_log("ERROR", "Lutfen bir hedef URL girin!", "cms")
            return
        timeout = int(getattr(self, "cms_timeout", tk.StringVar(value="60")).get())
        self._set_running(True)
        self.state.set_module_status("cms", "running")
        self._gui_log("INFO", f"CMS exploit baslatiliyor: {target}", "cms")

        def _run():
            try:
                self.cms_exploiter = CMSExploiter(target, gui_callback=lambda msg: self._parse_gui_callback(msg, "cms"))
                result = self.cms_exploiter.run(timeout=timeout)
                if result:
                    db_creds = result.get("db_credentials", {})
                    sso_tokens = result.get("sso_tokens", [])
                    admin_panels = result.get("admin_panels", [])
                    self.state.update({
                        "db_credentials": db_creds,
                        "sso_tokens": sso_tokens,
                        "admin_panels": admin_panels,
                    })
                    if db_creds:
                        self._gui_log("SUCCESS", f"DB kredensiyelleri: {db_creds.get('user', '?')}@{db_creds.get('host', '?')}", "cms")
                    if sso_tokens:
                        self._gui_log("SUCCESS", f"SSO token'lar: {len(sso_tokens)} adet", "cms")
                    self.state.set_module_status("cms", "success")
                else:
                    self.state.set_module_status("cms", "failed")
                    self._gui_log("ERROR", "CMS exploit basarisiz.", "cms")
            except Exception as e:
                self.state.set_module_status("cms", "failed")
                self._gui_log("ERROR", f"Hata: {e}", "cms")
            finally:
                self.root.after(0, lambda: self._set_running(False))

        threading.Thread(target=_run, daemon=True).start()

    def _run_database(self) -> None:
        if not HAS_DB:
            self._gui_log("ERROR", "DatabaseExploiter modulu yuklu degil!", "database")
            return
        target = self.target_url.get().strip()
        if not target:
            self._gui_log("ERROR", "Lutfen bir hedef URL girin!", "database")
            return
        db_host = getattr(self, "database_host", None)
        host = db_host.get().strip() if db_host else "localhost"
        db_port = getattr(self, "database_port", None)
        port = int(db_port.get()) if db_port else 3306
        db_user = getattr(self, "database_user", None)
        user = db_user.get().strip() if db_user else "root"
        db_pass = getattr(self, "database_pass", None)
        password = db_pass.get().strip() if db_pass else ""
        db_name = getattr(self, "database_name", None)
        database = db_name.get().strip() if db_name else ""
        db_target = getattr(self, "database_target_user", None)
        target_user = db_target.get().strip() if db_target else ""
        db_rank = getattr(self, "database_rank", None)
        new_rank = int(db_rank.get()) if db_rank else 7
        create_admin = getattr(self, "database_create_admin", None)
        create_admin_val = create_admin.get() if create_admin else False
        timeout = int(getattr(self, "database_timeout", tk.StringVar(value="60")).get())
        self._set_running(True)
        self.state.set_module_status("database", "running")
        self._gui_log("INFO", f"Database exploitation baslatiliyor: {user}@{host}:{port}/{database}", "database")

        def _run():
            try:
                self.database_exploiter = DatabaseExploiter(target, gui_callback=lambda msg: self._parse_gui_callback(msg, "database"))
                result = self.database_exploiter.run(
                    db_host=host, db_port=port, db_user=user, db_password=password,
                    db_name=database, target_user=target_user, new_rank=new_rank,
                    create_admin=create_admin_val, timeout=timeout
                )
                if result:
                    rank_confirmed = result.get("rank_changed", False)
                    new_sso = result.get("sso_tokens", [])
                    self.state.update({
                        "new_rank_confirmed": rank_confirmed,
                        "sso_tokens": new_sso,
                        "target_user": target_user,
                        "new_rank": new_rank,
                    })
                    if rank_confirmed:
                        self._gui_log("SUCCESS", f"Rank degistirildi: {target_user} -> {new_rank}", "database")
                    if new_sso:
                        self._gui_log("SUCCESS", f"Yeni SSO token'lar: {len(new_sso)} adet", "database")
                    self.state.set_module_status("database", "success")
                else:
                    self.state.set_module_status("database", "failed")
                    self._gui_log("ERROR", "Database exploitation basarisiz.", "database")
            except Exception as e:
                self.state.set_module_status("database", "failed")
                self._gui_log("ERROR", f"Hata: {e}", "database")
            finally:
                self.root.after(0, lambda: self._set_running(False))

        threading.Thread(target=_run, daemon=True).start()

    def _run_hotel_exploit(self) -> None:
        if not HAS_PACKET:
            self._gui_log("ERROR", "PacketManipulator modulu yuklu degil!", "hotel_exploit")
            return
        target = self.target_url.get().strip()
        if not target:
            self._gui_log("ERROR", "Lutfen bir hedef URL girin!", "hotel_exploit")
            return
        modify_rank = getattr(self, "hotel_exploit_modify_rank", None)
        modify_rank_val = modify_rank.get() if modify_rank else True
        rank = int(getattr(self, "hotel_exploit_rank", tk.StringVar(value="7")).get())
        modify_credits = getattr(self, "hotel_exploit_modify_credits", None)
        modify_credits_val = modify_credits.get() if modify_credits else True
        credits = getattr(self, "hotel_exploit_credits", None)
        credits_val = int(credits.get()) if credits else 999999
        modify_pixels = getattr(self, "hotel_exploit_modify_pixels", None)
        modify_pixels_val = modify_pixels.get() if modify_pixels else True
        modify_diamonds = getattr(self, "hotel_exploit_modify_diamonds", None)
        modify_diamonds_val = modify_diamonds.get() if modify_diamonds else True
        self._set_running(True)
        self.state.set_module_status("hotel_exploit", "running")
        self._gui_log("INFO", f"Hotel exploitation baslatiliyor: {target}", "hotel_exploit")

        def _run():
            try:
                self.packet_manipulator = PacketManipulator(target, gui_callback=lambda msg: self._parse_gui_callback(msg, "hotel_exploit"))
                result = self.packet_manipulator.run(
                    modify_rank=modify_rank_val, new_rank=rank,
                    modify_credits=modify_credits_val, credits=credits_val,
                    modify_pixels=modify_pixels_val, modify_diamonds=modify_diamonds_val
                )
                if result:
                    sso_tokens = result.get("sso_tokens", [])
                    self.state.update({"sso_tokens": sso_tokens})
                    if sso_tokens:
                        self._gui_log("SUCCESS", f"SSO token'lar: {len(sso_tokens)} adet", "hotel_exploit")
                    self.state.set_module_status("hotel_exploit", "success")
                else:
                    self.state.set_module_status("hotel_exploit", "failed")
                    self._gui_log("ERROR", "Hotel exploitation basarisiz.", "hotel_exploit")
            except Exception as e:
                self.state.set_module_status("hotel_exploit", "failed")
                self._gui_log("ERROR", f"Hata: {e}", "hotel_exploit")
            finally:
                self.root.after(0, lambda: self._set_running(False))

        threading.Thread(target=_run, daemon=True).start()

    def _run_gearth(self) -> None:
        if not HAS_GEARTH:
            self._gui_log("ERROR", "GEarthInjector modulu yuklu degil!", "gearth")
            return
        target = self.target_url.get().strip()
        if not target:
            self._gui_log("ERROR", "Lutfen bir hedef URL girin!", "gearth")
            return
        sso = getattr(self, "gearth_sso", None)
        sso_token = sso.get().strip() if sso else ""
        target_user = getattr(self, "gearth_target_user", None)
        user = target_user.get().strip() if target_user else ""
        rank = int(getattr(self, "gearth_rank", tk.StringVar(value="7")).get())
        ws_host = getattr(self, "gearth_ws_host", None)
        host = ws_host.get().strip() if ws_host else ""
        ws_port = getattr(self, "gearth_ws_port", None)
        port = int(ws_port.get()) if ws_port else 30000
        timeout = int(getattr(self, "gearth_timeout", tk.StringVar(value="60")).get())
        self._set_running(True)
        self.state.set_module_status("gearth", "running")
        self._gui_log("INFO", f"G-Earth injection baslatiliyor: {target}", "gearth")

        def _run():
            try:
                self.gearth_injector = GEarthInjector(target, gui_callback=lambda msg: self._parse_gui_callback(msg, "gearth"))
                result = self.gearth_injector.run(
                    sso_token=sso_token, target_user=user, new_rank=rank,
                    ws_host=host, ws_port=port, timeout=timeout
                )
                if result:
                    ws_info = result.get("websocket_info", {})
                    self.state.update({
                        "gearth_ws_host": ws_info.get("host", host),
                        "gearth_ws_port": ws_info.get("port", port),
                    })
                    self._gui_log("SUCCESS", "G-Earth injection basarili!", "gearth")
                    self.state.set_module_status("gearth", "success")
                else:
                    self.state.set_module_status("gearth", "failed")
                    self._gui_log("ERROR", "G-Earth injection basarisiz.", "gearth")
            except Exception as e:
                self.state.set_module_status("gearth", "failed")
                self._gui_log("ERROR", f"Hata: {e}", "gearth")
            finally:
                self.root.after(0, lambda: self._set_running(False))

        threading.Thread(target=_run, daemon=True).start()

    def _run_targeted_sqli(self) -> None:
        if not HAS_SQLI:
            self._gui_log("ERROR", "TargetedSQLi modulu yuklu degil!", "targeted_sqli")
            return
        target = self.target_url.get().strip()
        if not target:
            self._gui_log("ERROR", "Lutfen bir hedef URL girin!", "targeted_sqli")
            return
        cms_id = getattr(self, "targeted_sqli_cms_id", None)
        cms_id_val = cms_id.get().strip() if cms_id else ""
        timeout = int(getattr(self, "targeted_sqli_timeout", tk.StringVar(value="60")).get())
        self._set_running(True)
        self.state.set_module_status("targeted_sqli", "running")
        self._gui_log("INFO", f"Targeted SQLi baslatiliyor: {target}", "targeted_sqli")

        def _run():
            try:
                self.targeted_sqli = TargetedSQLi(target, gui_callback=lambda msg: self._parse_gui_callback(msg, "targeted_sqli"))
                result = self.targeted_sqli.run(cms_id=cms_id_val, timeout=timeout)
                if result:
                    db_creds = result.get("db_credentials", {})
                    admin_sessions = result.get("admin_sessions", [])
                    self.state.update({"db_credentials": db_creds})
                    if db_creds:
                        self._gui_log("SUCCESS", f"DB kredensiyelleri: {db_creds.get('user', '?')}@{db_creds.get('host', '?')}", "targeted_sqli")
                    if admin_sessions:
                        self._gui_log("SUCCESS", f"Admin session'lar: {len(admin_sessions)} adet", "targeted_sqli")
                    self.state.set_module_status("targeted_sqli", "success")
                else:
                    self.state.set_module_status("targeted_sqli", "failed")
                    self._gui_log("ERROR", "Targeted SQLi basarisiz.", "targeted_sqli")
            except Exception as e:
                self.state.set_module_status("targeted_sqli", "failed")
                self._gui_log("ERROR", f"Hata: {e}", "targeted_sqli")
            finally:
                self.root.after(0, lambda: self._set_running(False))

        threading.Thread(target=_run, daemon=True).start()

    def _run_camera(self) -> None:
        if not HAS_CAMERA:
            self._gui_log("ERROR", "HabboCameraExploit modulu yuklu degil!", "camera")
            return
        target = self.target_url.get().strip()
        if not target:
            self._gui_log("ERROR", "Lutfen bir hedef URL girin!", "camera")
            return
        timeout = int(getattr(self, "camera_timeout", tk.StringVar(value="60")).get())
        self._set_running(True)
        self.state.set_module_status("camera", "running")
        self._gui_log("INFO", f"Camera exploit baslatiliyor: {target}", "camera")

        def _run():
            try:
                self.habbo_camera = HabboCameraExploit(target, gui_callback=lambda msg: self._parse_gui_callback(msg, "camera"))
                result = self.habbo_camera.run(timeout=timeout)
                if result:
                    webshell_url = result.get("webshell_url")
                    if webshell_url:
                        self.state.set("webshell_url", webshell_url)
                        self._gui_log("SUCCESS", f"Webshell yuklendi: {webshell_url}", "camera")
                    self.state.set_module_status("camera", "success")
                else:
                    self.state.set_module_status("camera", "failed")
                    self._gui_log("ERROR", "Camera exploit basarisiz.", "camera")
            except Exception as e:
                self.state.set_module_status("camera", "failed")
                self._gui_log("ERROR", f"Hata: {e}", "camera")
            finally:
                self.root.after(0, lambda: self._set_running(False))

        threading.Thread(target=_run, daemon=True).start()

    def _run_persistence(self) -> None:
        if not HAS_PERSISTENCE:
            self._gui_log("ERROR", "Persistence modulu yuklu degil!", "persistence")
            return
        target = self.target_url.get().strip()
        if not target:
            self._gui_log("ERROR", "Lutfen bir hedef URL girin!", "persistence")
            return
        cookie = getattr(self, "persistence_cookie", None)
        cookie_val = cookie.get().strip() if cookie else ""
        rev_host = getattr(self, "persistence_rev_host", None)
        rev_host_val = rev_host.get().strip() if rev_host else ""
        rev_port = int(getattr(self, "persistence_rev_port", tk.StringVar(value="4444")).get())
        discord = getattr(self, "persistence_discord", None)
        discord_val = discord.get().strip() if discord else ""
        timeout = int(getattr(self, "persistence_timeout", tk.StringVar(value="60")).get())
        self._set_running(True)
        self.state.set_module_status("persistence", "running")
        self._gui_log("INFO", f"Persistence baslatiliyor: {target}", "persistence")

        def _run():
            try:
                self.persistence = Persistence(target, gui_callback=lambda msg: self._parse_gui_callback(msg, "persistence"))
                result = self.persistence.run(
                    admin_cookie=cookie_val, rev_host=rev_host_val,
                    rev_port=rev_port, discord_webhook=discord_val, timeout=timeout
                )
                if result:
                    ws_url = result.get("webshell_url")
                    rs_active = result.get("reverse_shell_active", False)
                    self.state.update({
                        "webshell_url": ws_url,
                        "reverse_shell_active": rs_active,
                    })
                    if ws_url:
                        self._gui_log("SUCCESS", f"Webshell: {ws_url}", "persistence")
                    if rs_active:
                        self._gui_log("SUCCESS", "Reverse shell aktif!", "persistence")
                    self.state.set_module_status("persistence", "success")
                else:
                    self.state.set_module_status("persistence", "failed")
                    self._gui_log("ERROR", "Persistence basarisiz.", "persistence")
            except Exception as e:
                self.state.set_module_status("persistence", "failed")
                self._gui_log("ERROR", f"Hata: {e}", "persistence")
            finally:
                self.root.after(0, lambda: self._set_running(False))

        threading.Thread(target=_run, daemon=True).start()

    def _run_updater(self) -> None:
        if not HAS_UPDATER:
            self._gui_log("ERROR", "SelfUpdater modulu yuklu degil!", "updater")
            return
        mode = getattr(self, "updater_mode", None)
        mode_val = mode.get() if mode else "check"
        self._set_running(True)
        self.state.set_module_status("updater", "running")
        self._gui_log("INFO", f"Self-updater baslatiliyor (mod: {mode_val})", "updater")

        def _run():
            try:
                self.self_updater = SelfUpdater(gui_callback=lambda msg: self._parse_gui_callback(msg, "updater"))
                result = self.self_updater.run(mode=mode_val)
                if result:
                    self._gui_log("SUCCESS", "Guncelleme basarili!", "updater")
                    self.state.set_module_status("updater", "success")
                else:
                    self.state.set_module_status("updater", "failed")
                    self._gui_log("ERROR", "Guncelleme basarisiz.", "updater")
            except Exception as e:
                self.state.set_module_status("updater", "failed")
                self._gui_log("ERROR", f"Hata: {e}", "updater")
            finally:
                self.root.after(0, lambda: self._set_running(False))

        threading.Thread(target=_run, daemon=True).start()

    def _run_chain(self) -> None:
        """Zincirleme calistir - tum modulleri sirayla calistir."""
        if self._chain_running:
            self._gui_log("WARNING", "Zincir zaten calisiyor!", "console")
            return
        self._chain_running = True
        self._gui_log("INFO", ">>> Zincirleme atak baslatiliyor...", "console")
        self._set_running(True)

        def _chain():
            module_order = [
                ("fingerprinter", self._run_fingerprinter),
                ("cloudflare", self._run_cloudflare),
                ("rate_limit", self._run_rate_limit),
                ("admin", self._run_admin),
                ("cms", self._run_cms),
                ("database", self._run_database),
                ("hotel_exploit", self._run_hotel_exploit),
                ("gearth", self._run_gearth),
                ("targeted_sqli", self._run_targeted_sqli),
                ("camera", self._run_camera),
                ("persistence", self._run_persistence),
                ("updater", self._run_updater),
            ]
            for module_key, run_method in module_order:
                if not self._chain_running:
                    self._gui_log("WARNING", "Zincir durduruldu.", "console")
                    break
                status = self.state.get_module_status(module_key)
                if status == "success":
                    self._gui_log("INFO", f"{module_key} zaten basarili, atlaniyor.", "console")
                    continue
                self._gui_log("INFO", f"--- Zincir: {module_key} baslatiliyor ---", "console")
                run_method()
                # Bekle - modul bitene kadar
                timeout = 300  # 5 dakika maksimum
                while self._chain_running and timeout > 0:
                    current_status = self.state.get_module_status(module_key)
                    if current_status in ("success", "failed", "skipped"):
                        break
                    time.sleep(2)
                    timeout -= 2
                if not self._chain_running:
                    break
                current_status = self.state.get_module_status(module_key)
                if current_status == "failed":
                    self._gui_log("WARNING", f"{module_key} basarisiz, zincir devam ediyor...", "console")
            self._chain_running = False
            self.root.after(0, lambda: self._set_running(False))
            self._gui_log("SUCCESS", ">>> Zincirleme atak tamamlandi!", "console")

        threading.Thread(target=_chain, daemon=True).start()

    def _run_all_modules(self) -> None:
        """Tum modulleri paralel calistir."""
        self._gui_log("INFO", "Tum moduller baslatiliyor...", "console")
        self._set_running(True)
        methods = [
            self._run_fingerprinter, self._run_cloudflare, self._run_rate_limit,
            self._run_admin, self._run_cms, self._run_database,
            self._run_hotel_exploit, self._run_gearth, self._run_targeted_sqli,
            self._run_camera, self._run_persistence, self._run_updater,
        ]
        for m in methods:
            try:
                m()
            except Exception as e:
                self._gui_log("ERROR", f"Modul baslatilamadi: {e}", "console")

    def _check_stop(self) -> bool:
        """Durdurma flag'ini kontrol et."""
        return not self.is_running or (hasattr(self, '_chain_running') and not self._chain_running)


def main() -> None:
    """Ana giris noktasi."""
    root = tk.Tk()
    initial_url = ""
    if len(sys.argv) > 1:
        initial_url = sys.argv[1]
    app = BenjiHabboHackGUI(root, initial_url=initial_url)
    root.mainloop()


if __name__ == "__main__":
    main()

