# x < 1,3
# x = 1,3
# x > 1,3

from __future__ import annotations

import sys
from pathlib import Path

# Папку с общими модулями (Mods) ищем вверх по дереву каталогов, а не отсчитываем
# "../.." вручную: ручной отсчёт ломается при любом переносе файла в другую папку.
MODULE_MARKER = "custom_assertions.py"
MODS_LOCATIONS = ("Mods", "04_Код/Mods", "Code/Mods")  # где папка модулей может лежать


def find_mods_dir(start: Path | None = None) -> Path | None:
    """Возвращает путь к папке Mods или None, если она не найдена.

    Проверяются и вложенные варианты (`04_Код/Mods`), потому что лабораторные
    лежат рядом с папкой кода, а не внутри неё.
    """
    current = (start or Path(__file__).resolve().parent).resolve()
    for candidate in (current, *current.parents):
        for location in MODS_LOCATIONS:
            folder = candidate / location
            if (folder / MODULE_MARKER).is_file():
                return folder
    return None


mods_path = find_mods_dir()
if mods_path is None:
    print(f"Модуль {MODULE_MARKER} не найден: папка Mods отсутствует в дереве каталогов")
    raise SystemExit(1)
if str(mods_path) not in sys.path:
    sys.path.insert(0, str(mods_path))

try:
    from custom_assertions import *  # noqa: E402,F403  (импорт после настройки sys.path)
except ImportError as e:
    print(f"Модуль custom_assertions не найден: {e}")
    raise SystemExit(1)

print(
    """Эта программа находит значение кусочно заданной функции:
    y = pi * (x**2) - (7 / (x**2)) # x < 1,3
    y = a * (x**3) + 7 * (x ** (1 / 2)) # x = 1,3
    y = ln(x + 7 * (x ** (1 / 2))) # x > 1,3
"""
)

import math as m

a = UserInput("Введите значение а: ", float)
x = UserInput("Введите значение х: ", float)

if x < 1.3:
    Fx = m.pi * (x**2) - (7 / (x**2))
    print(f"f(x) = {Fx}")
elif x == 1.3:
    Fx = a * (x**3) + 7 * (x ** (1 / 2))
    print(f"f(x) = {Fx}")
elif x > 1.3:
    Fx = m.log(x + 7 * (x ** (1 / 2)))
    print(f"f(x) = {Fx}")
