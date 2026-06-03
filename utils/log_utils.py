#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Утилиты для логирования — форматированный вывод в консоль и файл,
цветные сообщения, ротация логов.
"""

import os
import sys
import logging
from datetime import datetime
from typing import Optional, TextIO
from enum import Enum


class LogLevel(Enum):
    """Уровни логирования с ANSI-цветами."""
    DEBUG = ("\033[36m", "DEBUG")      # Cyan
    INFO = ("\033[32m", "INFO")        # Green
    SUCCESS = ("\033[92m", "SUCCESS")  # Bright Green
    WARNING = ("\033[33m", "WARNING")  # Yellow
    ERROR = ("\033[31m", "ERROR")      # Red
    CRITICAL = ("\033[91m", "CRITICAL") # Bright Red
    RESET = "\033[0m"


class Logger:
    """
    Класс логгера с поддержкой цветного вывода в консоль,
    записи в файл и callback-функции для GUI.
    """

    def __init__(
        self,
        name: str = "BenjiHabboHack",
        log_file: Optional[str] = None,
        console_output: bool = True,
        gui_callback=None,
    ):
        """
        Инициализация логгера.

        :param name: Имя логгера
        :param log_file: Путь к файлу лога (опционально)
        :param console_output: Выводить ли в консоль
        :param gui_callback: Функция обратного вызова для GUI (принимает строку)
        """
        self.name = name
        self.console_output = console_output
        self.gui_callback = gui_callback
        self.log_file = log_file
        self._file_handle: Optional[TextIO] = None

        if log_file:
            log_dir = os.path.dirname(log_file)
            if log_dir and not os.path.exists(log_dir):
                os.makedirs(log_dir, exist_ok=True)
            try:
                self._file_handle = open(log_file, "a", encoding="utf-8")
            except Exception as e:
                self._write_console(
                    f"Не удалось открыть файл лога {log_file}: {e}",
                    LogLevel.ERROR,
                )

    def _write_console(self, message: str, level: LogLevel):
        """Записывает сообщение в консоль с ANSI-цветами."""
        if not self.console_output:
            return
        color_code, level_name = level.value
        timestamp = datetime.now().strftime("%H:%M:%S")
        formatted = (
            f"{color_code}[{timestamp}][{level_name}] {message}{LogLevel.RESET.value}"
        )
        stream = sys.stderr if level in (LogLevel.ERROR, LogLevel.CRITICAL) else sys.stdout
        print(formatted, file=stream)

    def _write_file(self, message: str, level: LogLevel):
        """Записывает сообщение в файл лога."""
        if self._file_handle and not self._file_handle.closed:
            _, level_name = level.value
            timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            self._file_handle.write(f"[{timestamp}][{level_name}] {message}\n")
            self._file_handle.flush()

    def _write_gui(self, message: str, level: LogLevel):
        """Отправляет сообщение в GUI через callback."""
        if self.gui_callback:
            _, level_name = level.value
            timestamp = datetime.now().strftime("%H:%M:%S")
            formatted = f"[{timestamp}][{level_name}] {message}"
            self.gui_callback(formatted)

    def _log(self, message: str, level: LogLevel):
        """Внутренний метод логирования."""
        self._write_console(message, level)
        self._write_file(message, level)
        self._write_gui(message, level)

    def debug(self, message: str):
        """Логирует отладочное сообщение."""
        self._log(message, LogLevel.DEBUG)

    def info(self, message: str):
        """Логирует информационное сообщение."""
        self._log(message, LogLevel.INFO)

    def success(self, message: str):
        """Логирует сообщение об успехе."""
        self._log(message, LogLevel.SUCCESS)

    def warning(self, message: str):
        """Логирует предупреждение."""
        self._log(message, LogLevel.WARNING)

    def error(self, message: str):
        """Логирует ошибку."""
        self._log(message, LogLevel.ERROR)

    def critical(self, message: str):
        """Логирует критическую ошибку."""
        self._log(message, LogLevel.CRITICAL)

    def separator(self, char: str = "=", length: int = 60):
        """Выводит разделительную линию."""
        self._log(char * length, LogLevel.INFO)

    def close(self):
        """Закрывает файл лога."""
        if self._file_handle and not self._file_handle.closed:
            self._file_handle.close()
            self._file_handle = None

    def __del__(self):
        self.close()


class LogManager:
    """
    Менеджер логов — управляет созданием и хранением логгеров.
    """

    _instances: dict = {}

    @classmethod
    def get_logger(
        cls,
        name: str = "BenjiHabboHack",
        log_file: Optional[str] = None,
        gui_callback=None,
    ) -> Logger:
        """
        Возвращает или создаёт логгер с указанным именем.

        :param name: Имя логгера
        :param log_file: Путь к файлу лога
        :param gui_callback: Callback для GUI
        :return: Экземпляр Logger
        """
        if name not in cls._instances:
            cls._instances[name] = Logger(
                name=name,
                log_file=log_file,
                gui_callback=gui_callback,
            )
        return cls._instances[name]

    @classmethod
    def set_gui_callback(cls, callback, name: str = "BenjiHabboHack"):
        """
        Устанавливает GUI-callback для существующего логгера.

        :param callback: Функция обратного вызова
        :param name: Имя логгера
        """
        logger = cls._instances.get(name)
        if logger:
            logger.gui_callback = callback

    @classmethod
    def close_all(cls):
        """Закрывает все логгеры."""
        for logger in cls._instances.values():
            logger.close()
        cls._instances.clear()
