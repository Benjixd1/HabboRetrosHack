#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Benji Habbo Retros Hack - Shared Attack State Manager
Tum moduller arasinda veri paylasimi icin merkezi state yonetimi.
JSON dosyasi uzerinden okuma/yazma, observer pattern ile otomatik guncelleme.
"""

import os
import json
import threading
import time
from typing import Optional, Dict, Any, Callable, List
from datetime import datetime


ATTACK_STATE_FILE = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "attack_state.json")

DEFAULT_STATE = {
    "target_url": "",
    "target_domain": "",
    "origin_ips": [],
    "cloudflare_detected": False,
    "cloudflare_bypassed": False,
    "admin_panels": [],
    "admin_credentials": {},
    "cms_type": None,
    "cms_confidence": 0.0,
    "emulator_type": None,
    "emulator_confidence": 0.0,
    "db_credentials": {},
    "sso_tokens": [],
    "session_cookie": None,
    "proxy_pool_status": None,
    "target_user": "",
    "new_rank": 7,
    "new_rank_confirmed": False,
    "gearth_ws_host": None,
    "gearth_ws_port": None,
    "webshell_url": None,
    "reverse_shell_active": False,
    "discord_webhook": None,
    "module_status": {
        "fingerprinter": "pending",
        "cloudflare": "pending",
        "rate_limit": "pending",
        "admin": "pending",
        "cms": "pending",
        "database": "pending",
        "hotel_exploit": "pending",
        "gearth": "pending",
        "targeted_sqli": "pending",
        "camera": "pending",
        "persistence": "pending",
        "updater": "pending",
    },
    "last_updated": None,
    "errors": [],
}


class AttackState:
    """Merkezi atak state yoneticisi. JSON dosyasi uzerinden thread-safe okuma/yazma."""

    def __init__(self, state_file: str = ATTACK_STATE_FILE):
        self.state_file = state_file
        self._lock = threading.Lock()
        self._observers: Dict[str, List[Callable]] = {}
        self._state: Dict[str, Any] = {}
        self._polling = False
        self._poll_thread: Optional[threading.Thread] = None
        self._poll_interval = 2.0  # saniye
        self._load_or_create()

    def _load_or_create(self) -> None:
        """State dosyasini yukle veya varsayilan ile olustur."""
        try:
            if os.path.exists(self.state_file):
                with open(self.state_file, "r", encoding="utf-8") as f:
                    self._state = json.load(f)
                # Eksik anahtarlari varsayilanla doldur
                for key, val in DEFAULT_STATE.items():
                    if key not in self._state:
                        self._state[key] = val
            else:
                self._state = dict(DEFAULT_STATE)
                self._save()
        except Exception:
            self._state = dict(DEFAULT_STATE)
            self._save()

    def _save(self) -> None:
        """State'i JSON dosyasina yaz (thread-safe)."""
        with self._lock:
            self._state["last_updated"] = datetime.now().isoformat()
            try:
                with open(self.state_file, "w", encoding="utf-8") as f:
                    json.dump(self._state, f, indent=2, ensure_ascii=False)
            except Exception:
                pass

    def get(self, key: str, default=None) -> Any:
        """State'ten anahtar degerini al."""
        with self._lock:
            return self._state.get(key, default)

    def set(self, key: str, value: Any) -> None:
        """State'te anahtar degerini ayarla ve kaydet."""
        with self._lock:
            old_val = self._state.get(key)
            self._state[key] = value
            self._save()
        if old_val != value:
            self._notify(key, value)

    def update(self, data: Dict[str, Any]) -> None:
        """Birden fazla anahtari ayni anda guncelle."""
        with self._lock:
            changed_keys = {}
            for key, value in data.items():
                old_val = self._state.get(key)
                if old_val != value:
                    changed_keys[key] = value
                self._state[key] = value
            if changed_keys:
                self._save()
        for key, value in changed_keys.items():
            self._notify(key, value)

    def get_all(self) -> Dict[str, Any]:
        """State'in tam kopyasini al."""
        with self._lock:
            return dict(self._state)

    def set_module_status(self, module: str, status: str) -> None:
        """Modul durumunu guncelle (pending/running/success/failed/skipped)."""
        self.set(f"module_status.{module}", status)
        # Ayrica module_status dict'ini de guncelle
        with self._lock:
            if "module_status" not in self._state:
                self._state["module_status"] = {}
            self._state["module_status"][module] = status
            self._save()

    def get_module_status(self, module: str) -> str:
        """Modul durumunu sorgula."""
        ms = self.get("module_status", {})
        return ms.get(module, "pending")

    def add_error(self, error: str) -> None:
        """Hata listesine ekle."""
        with self._lock:
            if "errors" not in self._state:
                self._state["errors"] = []
            self._state["errors"].append(f"[{datetime.now().isoformat()}] {error}")
            if len(self._state["errors"]) > 100:
                self._state["errors"] = self._state["errors"][-100:]
            self._save()

    def reset(self) -> None:
        """State'i varsayilana sifirla."""
        with self._lock:
            self._state = dict(DEFAULT_STATE)
            self._save()
        self._notify_all()

    # --- Observer Pattern ---
    def observe(self, key: str, callback: Callable[[str, Any], None]) -> None:
        """Bir anahtar degistiginde cagrilacak callback ekle."""
        if key not in self._observers:
            self._observers[key] = []
        self._observers[key].append(callback)

    def observe_any(self, callback: Callable[[str, Any], None]) -> None:
        """Herhangi bir anahtar degistiginde cagrilacak callback ekle."""
        self.observe("*", callback)

    def _notify(self, key: str, value: Any) -> None:
        """Anahtar degisikligini observer'lara bildir."""
        callbacks = list(self._observers.get(key, []))
        callbacks.extend(list(self._observers.get("*", [])))
        for cb in callbacks:
            try:
                cb(key, value)
            except Exception:
                pass

    def _notify_all(self) -> None:
        """Tum observer'lara state'in tamamen degistigini bildir."""
        for key in list(self._observers.keys()):
            if key == "*":
                continue
            val = self._state.get(key)
            for cb in self._observers.get(key, []):
                try:
                    cb(key, val)
                except Exception:
                    pass
        # Wildcard observer'lara da bildir
        for cb in self._observers.get("*", []):
            try:
                cb("*", self._state)
            except Exception:
                pass

    # --- Polling (disardan degisiklikleri yakalamak icin) ---
    def start_polling(self, interval: float = 2.0) -> None:
        """State dosyasini belirli araliklarla kontrol eden polling thread'i baslat."""
        if self._polling:
            return
        self._poll_interval = interval
        self._polling = True
        self._poll_thread = threading.Thread(target=self._poll_loop, daemon=True)
        self._poll_thread.start()

    def stop_polling(self) -> None:
        """Polling thread'ini durdur."""
        self._polling = False

    def _poll_loop(self) -> None:
        """Polling dongusu - dosyadaki degisiklikleri kontrol et."""
        last_mtime = 0
        try:
            if os.path.exists(self.state_file):
                last_mtime = os.path.getmtime(self.state_file)
        except Exception:
            pass

        while self._polling:
            time.sleep(self._poll_interval)
            try:
                if os.path.exists(self.state_file):
                    mtime = os.path.getmtime(self.state_file)
                    if mtime > last_mtime:
                        last_mtime = mtime
                        # Dosya degismis, yeniden yukle
                        with self._lock:
                            try:
                                with open(self.state_file, "r", encoding="utf-8") as f:
                                    new_state = json.load(f)
                                for key, val in new_state.items():
                                    old_val = self._state.get(key)
                                    if old_val != val:
                                        self._state[key] = val
                                        # Observer'lara bildir (thread-safe icin ayri)
                                        self._notify(key, val)
                            except Exception:
                                pass
            except Exception:
                pass


# Singleton instance
_state_instance: Optional[AttackState] = None
_state_lock = threading.Lock()


def get_state() -> AttackState:
    """Singleton state instance'ini al."""
    global _state_instance
    if _state_instance is None:
        with _state_lock:
            if _state_instance is None:
                _state_instance = AttackState()
    return _state_instance


def reset_state() -> None:
    """State'i sifirla ve singleton'i yeniden olustur."""
    global _state_instance
    with _state_lock:
        if _state_instance:
            _state_instance.stop_polling()
        _state_instance = AttackState()
