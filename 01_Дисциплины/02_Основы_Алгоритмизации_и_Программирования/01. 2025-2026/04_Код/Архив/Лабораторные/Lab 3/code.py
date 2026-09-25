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
    """"Эта программа вычисляет кусочно заданную функцию
      z = 1 - e^(xy + ab) # xy > 0
      z = b - min{ax, y} # xy = 0
      z = max{x^3, e^y, ( |ln y^2| )^( 1/2 )} # xy <0
"""
)

import random as r
import math as m

x, a = -1, -4  # r.randint(-10, 10), r.randint(-10, 10)
b, y = -4, -4  # r.randint(-10, 10), r.randint(-10, 10)

Accuracy = UserInput("Введите количество знаков после запятой: ", int)

if x * y > 0:
    Fx = 1 - m.e ** (x * y + a * b)
    StrFx = "1 - e ^ (xy + ab)  # xy > 0"
elif x * y == 0:
    Fx = b - min(a * x, y)
    StrFx = "z = b - min{ax, y} # xy = 0"
elif x * y < 0:
    Fx = max(x**3, m.e**y, abs(m.log(y**2)) ** (1 / 2))
    StrFx = "max{x^3, e^y, ( |ln y^2| )^( 1/2 )} # xy <0"

print(
    f"""
Исходные значения:
    x = {x}
    y = {y}
    a = {a}
    b = {b}
Значение функции z при текущих значениях: {round(Fx, Accuracy)}
Подходящий отрезок кусочно заданной функции: {StrFx}
Точность вычисления: до {Accuracy} знака
"""
)
input("\nНажмите ENTER, чтобы выйти.")
