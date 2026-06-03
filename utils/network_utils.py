#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Утилиты для сетевых операций — HTTP-запросы, DNS-резолвинг,
SSL-сканирование и работа с заголовками.
"""

import socket
import ssl
import json
import re
import dns.resolver
import dns.reversename
import requests
from typing import Optional, Dict, List, Tuple, Any
from urllib.parse import urlparse, urljoin
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime

# Глобальная сессия с переиспользованием соединений
_session = requests.Session()
_session.headers.update({
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.5",
    "Accept-Encoding": "gzip, deflate, br",
    "Connection": "keep-alive",
    "Upgrade-Insecure-Requests": "1",
})


def resolve_dns(domain: str, record_type: str = "A") -> List[str]:
    """
    Разрешает DNS-записи указанного типа для домена.

    :param domain: Целевой домен
    :param record_type: Тип DNS-записи (A, AAAA, MX, NS, TXT, CNAME)
    :return: Список строк с результатами разрешения
    """
    results = []
    try:
        answers = dns.resolver.resolve(domain, record_type, lifetime=10)
        for rdata in answers:
            results.append(str(rdata))
    except dns.resolver.NoAnswer:
        pass
    except dns.resolver.NXDOMAIN:
        pass
    except Exception as e:
        pass
    return results


def reverse_dns_lookup(ip_address: str) -> Optional[str]:
    """
    Выполняет обратный DNS-запрос (PTR) для IP-адреса.

    :param ip_address: IP-адрес для обратного запроса
    :return: Доменное имя или None
    """
    try:
        rev_name = dns.reversename.from_address(ip_address)
        answers = dns.resolver.resolve(rev_name, "PTR", lifetime=10)
        return str(answers[0])
    except Exception:
        return None


def get_http_headers(url: str, timeout: int = 15) -> Optional[Dict[str, str]]:
    """
    Выполняет GET-запрос и возвращает HTTP-заголовки ответа.

    :param url: Полный URL для запроса
    :param timeout: Таймаут запроса в секундах
    :return: Словарь заголовков или None при ошибке
    """
    try:
        resp = _session.get(url, timeout=timeout, allow_redirects=True)
        return dict(resp.headers)
    except requests.RequestException:
        return None


def get_ssl_certificate(hostname: str, port: int = 443, timeout: int = 10) -> Optional[Dict[str, Any]]:
    """
    Получает SSL-сертификат хоста и извлекает информацию.

    :param hostname: Хост для подключения
    :param port: Порт (обычно 443)
    :param timeout: Таймаут соединения
    :return: Словарь с полями сертификата или None
    """
    try:
        ctx = ssl.create_default_context()
        with socket.create_connection((hostname, port), timeout=timeout) as sock:
            with ctx.wrap_socket(sock, server_hostname=hostname) as ssock:
                cert = ssock.getpeercert()
                if cert:
                    info = {
                        "subject": dict(x[0] for x in cert.get("subject", [])),
                        "issuer": dict(x[0] for x in cert.get("issuer", [])),
                        "version": cert.get("version"),
                        "serialNumber": cert.get("serialNumber"),
                        "notBefore": cert.get("notBefore"),
                        "notAfter": cert.get("notAfter"),
                        "subjectAltName": cert.get("subjectAltName", []),
                        "OCSP": cert.get("OCSP"),
                        "caIssuers": cert.get("caIssuers"),
                    }
                    return info
    except Exception:
        return None


def fetch_url_content(url: str, timeout: int = 15) -> Optional[str]:
    """
    Загружает содержимое страницы по URL.

    :param url: Целевой URL
    :param timeout: Таймаут запроса
    :return: Текст ответа или None
    """
    try:
        resp = _session.get(url, timeout=timeout, allow_redirects=True)
        if resp.status_code == 200:
            return resp.text
        return None
    except requests.RequestException:
        return None


def scan_common_ports(host: str, ports: List[int] = None, timeout: float = 2.0) -> Dict[int, bool]:
    """
    Сканирует список портов на хосте.

    :param host: IP-адрес или домен
    :param ports: Список портов (по умолчанию 80, 443, 8080, 8443, 2096, 3000, 3306, 21, 22)
    :param timeout: Таймаут на порт
    :return: Словарь {порт: открыт/закрыт}
    """
    if ports is None:
        ports = [21, 22, 80, 443, 8080, 8443, 2096, 3000, 3306, 5432, 6379, 8888, 9090]

    results = {}
    for port in ports:
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.settimeout(timeout)
                result = s.connect_ex((host, port))
                results[port] = (result == 0)
        except Exception:
            results[port] = False
    return results


def extract_links_from_html(html: str, base_url: str) -> List[str]:
    """
    Извлекает все ссылки из HTML-кода.

    :param html: HTML-контент
    :param base_url: Базовый URL для преобразования относительных ссылок
    :return: Список абсолютных URL
    """
    links = set()
    # Поиск href
    for match in re.finditer(r'href=["\'](.*?)["\']', html, re.IGNORECASE):
        url = match.group(1)
        if url and not url.startswith(('javascript:', '#', 'mailto:', 'tel:')):
            absolute = urljoin(base_url, url)
            links.add(absolute)
    # Поиск src
    for match in re.finditer(r'src=["\'](.*?)["\']', html, re.IGNORECASE):
        url = match.group(1)
        if url:
            absolute = urljoin(base_url, url)
            links.add(absolute)
    return list(links)


def check_cloudflare(headers: Dict[str, str]) -> bool:
    """
    Проверяет, использует ли сайт Cloudflare по заголовкам.

    :param headers: HTTP-заголовки ответа
    :return: True если Cloudflare обнаружен
    """
    cf_headers = [
        "CF-Ray", "CF-Cache-Status", "CF-Request-ID",
        "Cloudflare", "__cfduid"
    ]
    server = headers.get("Server", "")
    if "cloudflare" in server.lower():
        return True
    for h in cf_headers:
        if h.lower() in {k.lower() for k in headers.keys()}:
            return True
    return False


def get_public_ip() -> Optional[str]:
    """
    Получает внешний IP-адрес текущей машины.

    :return: Внешний IP или None
    """
    services = [
        "https://api.ipify.org",
        "https://icanhazip.com",
        "https://checkip.amazonaws.com",
    ]
    for service in services:
        try:
            resp = _session.get(service, timeout=10)
            if resp.status_code == 200:
                ip = resp.text.strip()
                if re.match(r'^\d+\.\d+\.\d+\.\d+$', ip):
                    return ip
        except Exception:
            continue
    return None


def parallel_requests(urls: List[str], timeout: int = 10, max_workers: int = 10) -> List[Tuple[str, Optional[str], Optional[Dict]]]:
    """
    Выполняет параллельные HTTP-запросы к списку URL.

    :param urls: Список URL
    :param timeout: Таймаут на запрос
    :param max_workers: Количество потоков
    :return: Список кортежей (url, текст_ответа, заголовки)
    """
    results = []

    def fetch(url):
        try:
            resp = _session.get(url, timeout=timeout, allow_redirects=True)
            return url, resp.text, dict(resp.headers)
        except Exception as e:
            return url, None, None

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {executor.submit(fetch, url): url for url in urls}
        for future in as_completed(futures):
            results.append(future.result())

    return results


def is_valid_ip(address: str) -> bool:
    """
    Проверяет, является ли строка валидным IPv4-адресом.

    :param address: Строка для проверки
    :return: True если это валидный IPv4
    """
    pattern = r'^(\d{1,3})\.(\d{1,3})\.(\d{1,3})\.(\d{1,3})$'
    match = re.match(pattern, address)
    if not match:
        return False
    for octet in match.groups():
        if int(octet) > 255:
            return False
    return True


def extract_domain(url: str) -> str:
    """
    Извлекает домен из URL.

    :param url: Полный URL
    :return: Доменное имя
    """
    parsed = urlparse(url)
    return parsed.netloc or parsed.hostname or url


def normalize_url(url: str) -> str:
    """
    Нормализует URL, добавляя схему если её нет.

    :param url: Исходный URL
    :return: Нормализованный URL
    """
    if not url.startswith(('http://', 'https://')):
        url = 'https://' + url
    return url.rstrip('/')
