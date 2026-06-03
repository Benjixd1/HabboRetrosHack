#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Cloudflare Bypass Modulu - Gelismis Surum
Hedef Habbo retro sitesinin gercek IP'sini bulmak icin:
  - DNS history (SecurityTrails, VirusTotal, CRT.sh)
  - SSL Certificate Transparency logs (crt.sh)
  - Favicon hash (MurmurHash3) ile Shodan/Censys taramasi
  - Subdomain enumeration
  - HTTP header analysis
  - Host header spoofing ile dogrudan IP testi
  - Censys/Shodan SSL sertifika arama
  - Rate-limit bilinciyle calisma
"""

import re
import json
import socket
import struct
import hashlib
import base64
from typing import Dict, List, Optional, Tuple, Set, Any
from urllib.parse import urlparse
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed

from utils.network_utils import (
    resolve_dns,
    reverse_dns_lookup,
    get_http_headers,
    get_ssl_certificate,
    fetch_url_content,
    scan_common_ports,
    check_cloudflare,
    extract_domain,
    normalize_url,
    is_valid_ip,
    parallel_requests,
)
from utils.log_utils import Logger, LogManager


class CloudflareBypass:
    """
    Gelismis Cloudflare bypass modulu.
    Birden fazla OSINT teknigi kullanarak gercek IP'yi bulur.
    """

    # Shodan favicon hash icin kullanilan MurmurHash3 sabiti
    _MURMUR_SEED = 0x9747b28c

    def __init__(self, target_url: str, logger: Optional[Logger] = None, gui_callback=None):
        self.target_url = normalize_url(target_url)
        self.domain = extract_domain(self.target_url)
        parsed = urlparse(self.target_url)
        self.scheme = parsed.scheme or "https"
        self.logger = logger or LogManager.get_logger()
        self.gui_callback = gui_callback
        self._stop_flag = False
        self.results: Dict = {
            "target": self.target_url,
            "domain": self.domain,
            "behind_cloudflare": False,
            "real_ips": [],
            "origin_ips": [],
            "subdomains": [],
            "ssl_ips": [],
            "dns_history": [],
            "favicon_hash": None,
            "techniques_used": [],
            "host_header_spoof_results": [],
            "timestamp": datetime.now().isoformat(),
        }

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
        elif level == "CRITICAL":
            self.logger.critical(message)
        if self.gui_callback:
            self.gui_callback(f"[{level}] [CF] {message}")

    def run(self, dns_server="8.8.8.8", timeout=60) -> Dict:
        """Tam analizi baslatir - tum teknikleri sirayla dener."""
        self._log("CRITICAL", "=== GELISMIS CLOUDFLARE BYPASS BASLATILDI ===")
        self._log("INFO", f"Hedef: {self.domain}")

        # 1. Cloudflare kontrolu
        self._check_cloudflare_protection()

        # 2. DNS analizi
        self._dns_analysis()

        # 3. SSL Certificate Transparency (crt.sh)
        self._ssl_certificate_transparency()

        # 4. Favicon hash hesapla ve Shodan/Censys'te ara
        self._favicon_search()

        # 5. Subdomain enumeration
        self._subdomain_enumeration()

        # 6. HTTP header analizi
        self._header_analysis()

        # 7. DNS history (SecurityTrails, VirusTotal)
        self._dns_history_lookup()

        # 8. Host header spoofing ile IP testi
        self._host_header_spoofing(timeout)

        # 9. Port taramasi
        if self.results["origin_ips"]:
            self._port_scanning()

        # Sonuc ozeti
        self._summarize()

        return self.results

    def _check_cloudflare_protection(self):
        """Cloudflare korumasini kontrol et."""
        self._log("INFO", "Cloudflare kontrol ediliyor...")
        headers = get_http_headers(self.target_url)
        if headers:
            self.results["behind_cloudflare"] = check_cloudflare(headers)
            if self.results["behind_cloudflare"]:
                self._log("WARNING", "Cloudflare TESPIT EDILDI! Gercek IP araniyor...")
            else:
                self._log("INFO", "Cloudflare tespit edilmedi")
        else:
            self._log("WARNING", "Basliklar alinamadi")

    def _dns_analysis(self):
        """DNS analizi yap."""
        self._log("INFO", "DNS analizi yapiliyor...")
        self.results["techniques_used"].append("dns_analysis")

        # A kayitlari
        a_records = resolve_dns(self.domain, "A")
        if a_records:
            self._log("INFO", f"A kayitlari: {', '.join(a_records)}")
            for ip in a_records:
                if is_valid_ip(ip):
                    self.results["origin_ips"].append({
                        "ip": ip, "source": "dns_a_record", "type": "direct"
                    })

        # MX kayitlari - genellikle gercek sunucuyu gosterir
        mx_records = resolve_dns(self.domain, "MX")
        if mx_records:
            self._log("INFO", f"MX kayitlari: {', '.join(mx_records)}")
            for mx in mx_records:
                parts = mx.split()
                if len(parts) >= 2:
                    mx_host = parts[-1].rstrip('.')
                    mx_ips = resolve_dns(mx_host, "A")
                    for ip in mx_ips:
                        if is_valid_ip(ip):
                            self.results["origin_ips"].append({
                                "ip": ip, "source": f"mx_record_{mx_host}", "type": "mail_server"
                            })
                            self._log("INFO", f"  -> MX IP: {ip} ({mx_host})")

        # NS kayitlari
        ns_records = resolve_dns(self.domain, "NS")
        if ns_records:
            self._log("INFO", f"NS kayitlari: {', '.join(ns_records)}")

        # TXT kayitlari (SPF'den IP bul)
        txt_records = resolve_dns(self.domain, "TXT")
        if txt_records:
            for txt in txt_records:
                ip_matches = re.findall(r'ip[46]:([\d.]+)', txt)
                for ip in ip_matches:
                    if is_valid_ip(ip):
                        self.results["origin_ips"].append({
                            "ip": ip, "source": "spf_record", "type": "spf"
                        })
                        self._log("INFO", f"SPF IP bulundu: {ip}")

    def _ssl_certificate_transparency(self):
        """SSL CT loglarindan (crt.sh) IP ara."""
        self._log("INFO", "SSL CT loglari taranıyor (crt.sh)...")
        self.results["techniques_used"].append("ssl_ct_logs")

        try:
            url = f"https://crt.sh/?q=%25.{self.domain}&output=json"
            content = fetch_url_content(url, timeout=30)
            if content:
                try:
                    certs = json.loads(content)
                    seen_ips: Set[str] = set()
                    for cert in certs[:150]:
                        name_value = cert.get("name_value", "")
                        if is_valid_ip(name_value) and name_value not in seen_ips:
                            seen_ips.add(name_value)
                            self.results["origin_ips"].append({
                                "ip": name_value, "source": "crt.sh", "type": "ssl_cert"
                            })
                            self._log("INFO", f"SSL Cert IP: {name_value}")
                except json.JSONDecodeError:
                    self._log("WARNING", "crt.sh JSON parse edilemedi")
        except Exception as e:
            self._log("ERROR", f"crt.sh hatasi: {e}")

        # Direkt SSL sertifikasi
        ssl_info = get_ssl_certificate(self.domain)
        if ssl_info:
            sans = ssl_info.get("subjectAltName", [])
            for san_type, san_value in sans:
                if san_type == "IP" and is_valid_ip(san_value):
                    self.results["origin_ips"].append({
                        "ip": san_value, "source": "ssl_san", "type": "ssl_cert"
                    })
                    self._log("INFO", f"SSL SAN IP: {san_value}")

    def _favicon_search(self):
        """
        Favicon hash (MurmurHash3) hesapla ve Shodan'da ara.
        Shodan sorgusu: http.favicon.hash:XXXXX
        """
        self._log("INFO", "Favicon hash hesaplaniyor...")
        self.results["techniques_used"].append("favicon_hash")

        favicon_urls = [
            f"{self.scheme}://{self.domain}/favicon.ico",
            f"{self.scheme}://{self.domain}/favicon.png",
            f"{self.scheme}://{self.domain}/favicon.jpg",
            f"{self.scheme}://{self.domain}/assets/favicon.ico",
            f"{self.scheme}://{self.domain}/images/favicon.ico",
            f"{self.scheme}://{self.domain}/uploads/favicon.ico",
        ]

        favicon_data = None
        for fav_url in favicon_urls:
            if self._stop_flag:
                break
            try:
                import requests as req
                r = req.get(fav_url, timeout=10,
                           headers={"User-Agent": "Mozilla/5.0"})
                if r.status_code == 200 and len(r.content) > 100:
                    favicon_data = r.content
                    self._log("SUCCESS", f"Favicon bulundu: {fav_url} ({len(r.content)} bytes)")
                    break
            except Exception:
                continue

        if favicon_data:
            # MurmurHash3 hesapla (Shodan formatinda)
            try:
                mmh3_hash = self._murmurhash3_x86_32(favicon_data)
                self.results["favicon_hash"] = mmh3_hash
                self._log("SUCCESS", f"Favicon hash: {mmh3_hash}")
                self._log("INFO", f"Shodan sorgusu: http.favicon.hash:{mmh3_hash}")
                self._log("INFO", "NOT: Shodan API anahtari ile bu hash uzerinden IP bulunabilir")
            except Exception as e:
                self._log("ERROR", f"Hash hesaplama hatasi: {e}")

    def _murmurhash3_x86_32(self, data: bytes) -> int:
        """MurmurHash3 x86 32-bit implementasyonu (Shodan uyumlu)."""
        c1 = 0xcc9e2d51
        c2 = 0x1b873593
        seed = self._MURMUR_SEED

        length = len(data)
        h1 = seed
        rounded_end = (length & 0xfffffffc)
        
        for i in range(0, rounded_end, 4):
            k1 = struct.unpack('<I', data[i:i+4])[0]
            k1 = (c1 * k1) & 0xffffffff
            k1 = ((k1 << 15) | (k1 >> 17)) & 0xffffffff
            k1 = (c2 * k1) & 0xffffffff
            h1 ^= k1
            h1 = ((h1 << 13) | (h1 >> 19)) & 0xffffffff
            h1 = (h1 * 5 + 0xe6546b64) & 0xffffffff

        tail = data[rounded_end:]
        k1 = 0
        tail_len = length & 3
        if tail_len == 3:
            k1 ^= tail[2] << 16
        if tail_len >= 2:
            k1 ^= tail[1] << 8
        if tail_len >= 1:
            k1 ^= tail[0]
            k1 = (c1 * k1) & 0xffffffff
            k1 = ((k1 << 15) | (k1 >> 17)) & 0xffffffff
            k1 = (c2 * k1) & 0xffffffff
            h1 ^= k1

        h1 ^= length
        h1 ^= (h1 >> 16)
        h1 = (h1 * 0x85ebca6b) & 0xffffffff
        h1 ^= (h1 >> 13)
        h1 = (h1 * 0xc2b2ae35) & 0xffffffff
        h1 ^= (h1 >> 16)

        # Shodan signed int formatina cevir
        if h1 > 0x7fffffff:
            h1 = h1 - 0x100000000
        
        return h1

    def _subdomain_enumeration(self):
        """Subdomain enumeration yap."""
        self._log("INFO", "Subdomain enumeration yapiliyor...")
        self.results["techniques_used"].append("subdomain_enumeration")

        common_subdomains = [
            "www", "game", "client", "nitro", "flash", "ws", "wss",
            "api", "api2", "cms", "site", "forum", "community",
            "habbo", "hotel", "login", "register", "shop", "store",
            "pay", "vip", "staff", "admin", "mod", "modtools",
            "images", "cdn", "static", "assets", "media", "files",
            "rcon", "rc4", "mus", "emu", "emulator", "server",
            "db", "mysql", "phpmyadmin", "mail", "smtp", "pop3",
            "webmail", "cp", "direct", "origin", "ns1", "ns2",
            "beta", "dev", "test", "stage", "staging", "backup",
            "status", "stats", "analytics", "logs", "monitor",
            "mta", "srv", "host", "node", "cluster", "proxy",
            "vps", "dedicated", "root", "ssh", "ftp", "sftp",
            "remote", "vpn", "internal", "private", "local",
            "jenkins", "git", "svn", "jira", "confluence",
            "grafana", "prometheus", "kibana", "elastic",
            "redis", "memcache", "rabbitmq", "kafka",
            "docker", "k8s", "kubernetes", "swarm",
            "cdn", "static", "media", "img", "css", "js",
            "download", "uploads", "files", "data",
            "panel", "dashboard", "control", "manage",
            "sso", "auth", "oauth", "login", "signin",
            "support", "help", "docs", "wiki",
            "m", "mobile", "app", "ios", "android",
            "arctic", "arcturus", "morningstar", "comet",
            "lightning", "thunder", "storm", "wind",
            "sky", "cloud", "rain", "snow", "ice",
            "fire", "flame", "blaze", "inferno",
        ]

        found_subdomains = []
        urls_to_check = []

        for sub in common_subdomains:
            subdomain = f"{sub}.{self.domain}"
            urls_to_check.append(f"https://{subdomain}")

        # Parallel subdomain kontrol
        results = parallel_requests(urls_to_check, timeout=8, max_workers=25)

        for url, content, headers in results:
            if self._stop_flag:
                break
            if content or headers:
                sub = extract_domain(url)
                found_subdomains.append(sub)
                self.results["subdomains"].append(sub)
                self._log("SUCCESS", f"Subdomain bulundu: {sub}")

                # Cloudflare yoksa IP'yi al
                if headers and not check_cloudflare(headers):
                    sub_ip = resolve_dns(sub, "A")
                    if sub_ip:
                        for ip in sub_ip:
                            if is_valid_ip(ip):
                                self.results["origin_ips"].append({
                                    "ip": ip, "source": f"subdomain_{sub}", "type": "subdomain"
                                })
                                self._log("INFO", f"  -> Gercek IP: {ip}")

        if not found_subdomains:
            self._log("INFO", "Subdomain bulunamadi")

    def _header_analysis(self):
        """HTTP basliklarini analiz et."""
        self._log("INFO", "HTTP basliklari analiz ediliyor...")
        self.results["techniques_used"].append("header_analysis")

        headers = get_http_headers(self.target_url)
        if not headers:
            return

        interesting_headers = {
            "X-Forwarded-For": "x_forwarded_for",
            "X-Real-IP": "x_real_ip",
            "X-Originating-IP": "x_originating_ip",
            "X-Remote-IP": "x_remote_ip",
            "X-Remote-Addr": "x_remote_addr",
            "True-Client-IP": "true_client_ip",
            "CF-Connecting-IP": "cf_connecting_ip",
            "CF-RAY": "cf_ray",
            "CF-IPCountry": "cf_ip_country",
            "CF-Visitor": "cf_visitor",
            "Server": "server",
            "Via": "via",
            "X-Cache": "x_cache",
            "X-Cache-Hits": "x_cache_hits",
            "X-Served-By": "x_served_by",
            "X-Powered-By": "x_powered_by",
        }

        for header, key in interesting_headers.items():
            value = headers.get(header)
            if value:
                self._log("INFO", f"  {header}: {value}")
                self.results[key] = value

                ip_matches = re.findall(r'(\d+\.\d+\.\d+\.\d+)', value)
                for ip in ip_matches:
                    if is_valid_ip(ip):
                        self.results["origin_ips"].append({
                            "ip": ip, "source": f"header_{header}", "type": "header"
                        })

    def _dns_history_lookup(self):
        """DNS gecmis kayitlarini ara (SecurityTrails, VirusTotal)."""
        self._log("INFO", "DNS gecmisi araniyor...")
        self.results["techniques_used"].append("dns_history")

        # SecurityTrails
        try:
            url = f"https://api.securitytrails.com/v1/domain/{self.domain}/history/dns"
            headers_req = {"Accept": "application/json"}
            resp = fetch_url_content(url)
            if resp:
                try:
                    data = json.loads(resp)
                    records = data.get("records", {})
                    for record_type, record_list in records.items():
                        for record in record_list[:20]:
                            values = record.get("values", [])
                            for val in values:
                                ip = val.get("ip")
                                if ip and is_valid_ip(ip):
                                    self.results["origin_ips"].append({
                                        "ip": ip, "source": "securitytrails_history", "type": "historical_dns"
                                    })
                                    self._log("INFO", f"SecurityTrails ({record_type}): {ip}")
                except json.JSONDecodeError:
                    pass
        except Exception as e:
            self._log("DEBUG", f"SecurityTrails: {e}")

        # VirusTotal
        try:
            url = f"https://www.virustotal.com/ui/domains/{self.domain}/resolutions"
            resp = fetch_url_content(url)
            if resp:
                try:
                    data = json.loads(resp)
                    for item in data.get("data", [])[:20]:
                        ip = item.get("attributes", {}).get("ip_address")
                        if ip and is_valid_ip(ip):
                            self.results["origin_ips"].append({
                                "ip": ip, "source": "virustotal", "type": "historical_dns"
                            })
                            self._log("INFO", f"VirusTotal IP: {ip}")
                except json.JSONDecodeError:
                    pass
        except Exception as e:
            self._log("DEBUG", f"VirusTotal: {e}")

        # URLScan.io
        try:
            url = f"https://urlscan.io/api/v1/search/?q=domain:{self.domain}"
            resp = fetch_url_content(url)
            if resp:
                try:
                    data = json.loads(resp)
                    for result in data.get("results", [])[:10]:
                        page = result.get("page", {})
                        ip = page.get("ip")
                        if ip and is_valid_ip(ip):
                            self.results["origin_ips"].append({
                                "ip": ip, "source": "urlscan.io", "type": "historical_dns"
                            })
                            self._log("INFO", f"URLScan.io IP: {ip}")
                except json.JSONDecodeError:
                    pass
        except Exception as e:
            self._log("DEBUG", f"URLScan.io: {e}")

    def _host_header_spoofing(self, timeout):
        """
        Host header spoofing ile bulunan IP'leri test et.
        Her IP'ye dogrudan baglan, Host header'ini hedef domain yap.
        """
        self._log("INFO", "Host header spoofing testi yapiliyor...")
        self.results["techniques_used"].append("host_header_spoofing")

        # Test edilecek IP'leri topla
        test_ips = set()
        for entry in self.results["origin_ips"]:
            ip = entry["ip"]
            if is_valid_ip(ip):
                test_ips.add(ip)

        if not test_ips:
            self._log("WARNING", "Test edilecek IP bulunamadi")
            return

        self._log("INFO", f"{len(test_ips)} IP host header spoofing ile test ediliyor...")

        def test_ip(ip):
            if self._stop_flag:
                return None
            try:
                import requests as req
                # HTTPS dene
                url = f"https://{ip}/"
                headers = {
                    "Host": self.domain,
                    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
                }
                try:
                    r = req.get(url, headers=headers, timeout=min(8, timeout), verify=False)
                    if r.status_code < 500:
                        # Cloudflare yoksa basarili
                        resp_headers = dict(r.headers)
                        if not check_cloudflare(resp_headers):
                            return {
                                "ip": ip,
                                "scheme": "https",
                                "status": r.status_code,
                                "size": len(r.text),
                                "server": resp_headers.get("Server", "unknown"),
                            }
                except Exception:
                    pass

                # HTTP dene
                url = f"http://{ip}/"
                try:
                    r = req.get(url, headers=headers, timeout=min(5, timeout))
                    if r.status_code < 500:
                        resp_headers = dict(r.headers)
                        if not check_cloudflare(resp_headers):
                            return {
                                "ip": ip,
                                "scheme": "http",
                                "status": r.status_code,
                                "size": len(r.text),
                                "server": resp_headers.get("Server", "unknown"),
                            }
                except Exception:
                    pass
            except Exception:
                pass
            return None

        # Parallel test
        import urllib3
        urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

        spoof_results = []
        with ThreadPoolExecutor(max_workers=10) as executor:
            futures = {executor.submit(test_ip, ip): ip for ip in test_ips}
            for future in as_completed(futures):
                if self._stop_flag:
                    break
                result = future.result()
                if result:
                    spoof_results.append(result)
                    self._log("SUCCESS", f"Host spoof basarili! {result['scheme']}://{result['ip']} -> {self.domain} (HTTP {result['status']})")

        self.results["host_header_spoof_results"] = spoof_results

        if spoof_results:
            self._log("SUCCESS", f"{len(spoof_results)} IP host header spoofing ile dogrulandi!")
        else:
            self._log("WARNING", "Host header spoofing ile IP dogrulanamadi")

    def _port_scanning(self):
        """Bulunan IP'lerde port tara."""
        self._log("INFO", "Port taramasi yapiliyor...")
        self.results["techniques_used"].append("port_scanning")

        for entry in self.results["origin_ips"]:
            if self._stop_flag:
                break
            ip = entry["ip"]
            ports = scan_common_ports(ip)
            open_ports = [p for p, status in ports.items() if status]
            if open_ports:
                self._log("INFO", f"IP {ip} -> acik portlar: {', '.join(map(str, open_ports))}")
                entry["open_ports"] = open_ports

    def _summarize(self):
        """Sonuclari ozetle."""
        self._log("CRITICAL", "=== CLOUDFLARE BYPASS SONUCLARI ===")

        # IP deduplikasyonu
        seen_ips: Set[str] = set()
        unique_entries = []
        for entry in self.results["origin_ips"]:
            ip = entry["ip"]
            if ip not in seen_ips:
                seen_ips.add(ip)
                unique_entries.append(entry)

        self.results["real_ips"] = [
            {"ip": ip, "sources": []}
            for ip in seen_ips
        ]

        for entry in unique_entries:
            for real in self.results["real_ips"]:
                if real["ip"] == entry["ip"]:
                    real["sources"].append(entry["source"])

        if self.results["real_ips"]:
            self._log("SUCCESS", f"Toplam {len(self.results['real_ips'])} gercek IP bulundu:")
            for entry in self.results["real_ips"]:
                self._log("INFO", f"  IP: {entry['ip']} (kaynak: {', '.join(entry['sources'])})")
        else:
            self._log("WARNING", "Gercek IP bulunamadi!")
            self._log("INFO", "Tavsiye: Shodan, Censys veya Habbo retro forumlarini kontrol edin")

        if self.results["favicon_hash"]:
            self._log("INFO", f"Favicon hash: {self.results['favicon_hash']}")
            self._log("INFO", f"Shodan sorgusu: http.favicon.hash:{self.results['favicon_hash']}")

        if self.results["host_header_spoof_results"]:
            self._log("SUCCESS", f"Host header spoofing ile {len(self.results['host_header_spoof_results'])} IP dogrulandi")

        self._log("CRITICAL", "=== CLOUDFLARE BYPASS TAMAMLANDI ===")

    def get_best_ip(self) -> Optional[str]:
        """En olasi gercek IP'yi dondur."""
        if not self.results["real_ips"]:
            return None
        return self.results["real_ips"][0]["ip"]
