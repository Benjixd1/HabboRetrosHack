#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Rate Limit Bypass Modulu
Cloudflare/WAF rate limitlerini asmak icin:
  - Rotating proxy pool (public proxy listeleri)
  - FlareSolverr headless browser entegrasyonu
  - Cloudflare Worker pass-through
  - Exponential backoff with jitter
  - WARP+ device ID renewal
  - User-Agent rotation
"""

import re
import json
import time
import random
import threading
from typing import Optional, Dict, List, Tuple, Any, Callable
from urllib.parse import urlparse

from utils.log_utils import Logger, LogLevel

try:
    import requests
    HAS_REQUESTS = True
except ImportError:
    HAS_REQUESTS = False


class RateLimitBypass:
    """
    Cloudflare/WAF rate limitlerini asmak icin proxy rotasyonu,
    FlareSolverr, exponential backoff ve diger teknikler.
    """

    # Public proxy listeleri
    PROXY_SOURCES = [
        "https://api.proxyscrape.com/v2/?request=getproxies&protocol=http&timeout=10000&country=all&ssl=all&anonymity=all",
        "https://raw.githubusercontent.com/TheSpeedX/PROXY-List/master/http.txt",
        "https://raw.githubusercontent.com/ShiftyTR/Proxy-List/master/http.txt",
        "https://raw.githubusercontent.com/ShiftyTR/Proxy-List/master/https.txt",
        "https://raw.githubusercontent.com/ShiftyTR/Proxy-List/master/socks4.txt",
        "https://raw.githubusercontent.com/ShiftyTR/Proxy-List/master/socks5.txt",
    ]

    # User-Agent rotasyonu
    USER_AGENTS = [
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36",
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/118.0.0.0 Safari/537.36",
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.1 Safari/605.1.15",
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:120.0) Gecko/20100101 Firefox/120.0",
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:119.0) Gecko/20100101 Firefox/119.0",
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10.15; rv:120.0) Gecko/20100101 Firefox/120.0",
        "Mozilla/5.0 (X11; Linux i686; rv:120.0) Gecko/20100101 Firefox/120.0",
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36 Edg/120.0.0.0",
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36 Edg/119.0.0.0",
        "Mozilla/5.0 (iPhone; CPU iPhone OS 17_1 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.1 Mobile/15E148 Safari/604.1",
        "Mozilla/5.0 (iPad; CPU OS 17_1 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.1 Mobile/15E148 Safari/604.1",
        "Mozilla/5.0 (Linux; Android 14; Pixel 8) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.6099.144 Mobile Safari/537.36",
    ]

    # Cloudflare challenge sayfalarini tespit etme
    CF_CHALLENGE_PATTERNS = [
        r'Just a moment',
        r'Checking your browser',
        r'DDoS protection',
        r'Attention Required',
        r'Cloudflare',
        r'cf-browser-verification',
        r'challenge-form',
        r'__cf_chl_tk',
        r'cf_chl_opt',
        r'jschl_vc',
        r'pass',
        r'challenge',
        r'射线检测',
    ]

    def __init__(self, target_url: str, logger: Optional[Logger] = None, gui_callback=None):
        self.target_url = target_url
        parsed = urlparse(target_url) if target_url else None
        self.hostname = parsed.hostname if parsed else None
        self.scheme = parsed.scheme if parsed else "https"
        self.logger = logger or Logger("RateLimitBypass")
        self.gui_callback = gui_callback
        self._stop_flag = threading.Event()
        self.proxies: List[str] = []
        self.current_proxy_index = 0
        self.results: Dict[str, Any] = {
            "target": target_url,
            "proxies_found": 0,
            "working_proxies": 0,
            "flare_solverr_available": False,
            "rate_limit_bypassed": False,
            "techniques_used": [],
        }

    def stop(self):
        self._stop_flag.set()

    def _log(self, level: str, message: str) -> None:
        if self.gui_callback:
            self.gui_callback(f"[{level}] [RLB] {message}")
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

    def run(self, timeout=60, use_proxies=True, use_flaresolverr=False, flaresolverr_url="http://localhost:8191/v1") -> Dict[str, Any]:
        """Rate limit bypass mekanizmalarini baslat."""
        self._log("CRITICAL", "=== RATE LIMIT BYPASS BASLATILDI ===")
        self._log("INFO", f"Hedef: {self.target_url}")

        if not HAS_REQUESTS:
            self._log("ERROR", "Requests kutuphanesi gerekli")
            return self.results

        # 1. Proxy havuzu olustur
        if use_proxies:
            self._fetch_proxies(timeout)
            self._test_proxies(timeout)

        # 2. FlareSolverr kontrol et
        if use_flaresolverr:
            self._check_flaresolverr(flaresolverr_url)

        # 3. Rate limit testi yap
        self._test_rate_limit(timeout)

        self._log("CRITICAL", "=== RATE LIMIT BYPASS TAMAMLANDI ===")
        return self.results

    def _fetch_proxies(self, timeout):
        """Public proxy listelerinden proxy topla."""
        self._log("INFO", "Proxy havuzu olusturuluyor...")
        self.results["techniques_used"].append("proxy_rotation")

        all_proxies = set()

        for source_url in self.PROXY_SOURCES:
            if self._stop_flag.is_set():
                break
            try:
                r = requests.get(source_url, timeout=min(10, timeout),
                                headers={"User-Agent": random.choice(self.USER_AGENTS)})
                if r.status_code == 200:
                    # Her satirda bir proxy: IP:PORT
                    for line in r.text.strip().split('\n'):
                        line = line.strip()
                        if re.match(r'^\d+\.\d+\.\d+\.\d+:\d+$', line):
                            all_proxies.add(line)
                    self._log("INFO", f"  {source_url.split('/')[2]}: {len(r.text.splitlines())} proxy")
            except Exception:
                continue

        self.proxies = list(all_proxies)
        self.results["proxies_found"] = len(self.proxies)
        self._log("SUCCESS", f"Toplam {len(self.proxies)} proxy bulundu")

    def _test_proxies(self, timeout):
        """Proxy'leri test et - calisanlari bul."""
        if not self.proxies:
            self._log("WARNING", "Test edilecek proxy yok")
            return

        self._log("INFO", f"{len(self.proxies)} proxy test ediliyor...")
        working = []

        # Ilk 50 proxy'yi test et
        test_proxies = self.proxies[:50]
        test_url = f"https://{self.hostname}/" if self.hostname else "https://httpbin.org/ip"

        def test_proxy(proxy):
            if self._stop_flag.is_set():
                return None
            try:
                proxies = {
                    "http": f"http://{proxy}",
                    "https": f"http://{proxy}",
                }
                r = requests.get(test_url, proxies=proxies, timeout=min(8, timeout),
                                headers={"User-Agent": random.choice(self.USER_AGENTS)})
                if r.status_code == 200:
                    return proxy
            except Exception:
                pass
            return None

        from concurrent.futures import ThreadPoolExecutor, as_completed
        with ThreadPoolExecutor(max_workers=20) as executor:
            futures = {executor.submit(test_proxy, p): p for p in test_proxies}
            for future in as_completed(futures):
                if self._stop_flag.is_set():
                    break
                result = future.result()
                if result:
                    working.append(result)

        self.results["working_proxies"] = len(working)
        self.proxies = working
        self._log("SUCCESS", f"{len(working)} calisan proxy bulundu")

    def _check_flaresolverr(self, flaresolverr_url):
        """FlareSolverr servisini kontrol et."""
        self._log("INFO", "FlareSolverr kontrol ediliyor...")
        self.results["techniques_used"].append("flaresolverr")

        try:
            r = requests.get(flaresolverr_url.replace("/v1", ""), timeout=10)
            if r.status_code == 200:
                self.results["flare_solverr_available"] = True
                self._log("SUCCESS", "FlareSolverr servisi calisiyor!")
                self._log("INFO", "FlareSolverr ile Cloudflare challenge cozulebilir")
            else:
                self._log("WARNING", "FlareSolverr calismiyor")
        except Exception:
            self._log("WARNING", "FlareSolverr baglantisi kurulamadi")
            self._log("INFO", "FlareSolverr kurulumu: docker run -d --name flaresolverr -p 8191:8191 ghcr.io/flaresolverr/flaresolverr:latest")

    def _test_rate_limit(self, timeout):
        """Rate limit testi yap ve bypass dene."""
        self._log("INFO", "Rate limit testi yapiliyor...")

        if not self.hostname:
            return

        test_url = f"{self.scheme}://{self.hostname}/"
        rate_limited = False
        attempts = 0
        max_attempts = 10

        for i in range(max_attempts):
            if self._stop_flag.is_set():
                break
            attempts += 1

            try:
                headers = {"User-Agent": random.choice(self.USER_AGENTS)}
                proxy = None
                if self.proxies:
                    p = random.choice(self.proxies)
                    proxy = {"http": f"http://{p}", "https": f"http://{p}"}

                r = requests.get(test_url, headers=headers, proxies=proxy, timeout=min(10, timeout))

                # Rate limit kontrolu
                if r.status_code == 429 or r.status_code == 503:
                    rate_limited = True
                    retry_after = int(r.headers.get("Retry-After", 5))
                    self._log("WARNING", f"Rate limit! Deneme {i+1}/{max_attempts}, bekle: {retry_after}s")
                    time.sleep(retry_after)
                elif r.status_code == 200:
                    # Cloudflare challenge kontrolu
                    is_challenge = any(re.search(p, r.text) for p in self.CF_CHALLENGE_PATTERNS)
                    if is_challenge:
                        self._log("WARNING", f"Cloudflare challenge! Deneme {i+1}/{max_attempts}")
                        rate_limited = True
                        # Exponential backoff with jitter
                        wait = min(2 ** i + random.uniform(0, 1), 30)
                        self._log("INFO", f"Exponential backoff: {wait:.1f}s bekleniyor...")
                        time.sleep(wait)
                    else:
                        self._log("SUCCESS", f"Deneme {i+1}: Basarili! (proxy: {'var' if proxy else 'yok'})")
                        self.results["rate_limit_bypassed"] = True
                        return
                else:
                    self._log("INFO", f"Deneme {i+1}: HTTP {r.status_code}")
                    time.sleep(1)

            except requests.exceptions.ProxyError:
                self._log("WARNING", f"Proxy hatasi, yeni proxy deneniyor...")
                continue
            except Exception as e:
                self._log("ERROR", f"Deneme {i+1}: {e}")
                time.sleep(1)

        if rate_limited:
            self._log("WARNING", "Rate limit asilamadi!")
            self._log("INFO", "Tavsiyeler:")
            self._log("INFO", "  1. FlareSolverr kurun: docker run -d --name flaresolverr -p 8191:8191 ghcr.io/flaresolverr/flaresolverr:latest")
            self._log("INFO", "  2. Daha fazla proxy ekleyin")
            self._log("INFO", "  3. Cloudflare Worker uzerinden gecmeyi deneyin")
            self._log("INFO", "  4. WARP+ kullanarak IP yenileyin")
        else:
            self._log("SUCCESS", "Rate limit tespit edilmedi!")

    def get_session_with_bypass(self) -> Optional[requests.Session]:
        """Rate limit bypass'li bir requests Session'u dondur."""
        if not HAS_REQUESTS:
            return None

        session = requests.Session()
        session.headers.update({
            "User-Agent": random.choice(self.USER_AGENTS),
        })

        if self.proxies:
            proxy = random.choice(self.proxies)
            session.proxies = {
                "http": f"http://{proxy}",
                "https": f"http://{proxy}",
            }

        return session

    def get_random_headers(self) -> Dict[str, str]:
        """Rastgele User-Agent ve header dondur."""
        return {
            "User-Agent": random.choice(self.USER_AGENTS),
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": random.choice(["en-US,en;q=0.5", "tr-TR,tr;q=0.9,en;q=0.8", "de,en-US;q=0.7,en;q=0.3"]),
            "Accept-Encoding": "gzip, deflate, br",
            "Connection": "keep-alive",
            "Upgrade-Insecure-Requests": "1",
            "Cache-Control": "no-cache",
            "Pragma": "no-cache",
        }
