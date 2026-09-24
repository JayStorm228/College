"""Шаблон для копирования в решения: подключает папку Mods с общими модулями.

Зачем этот файл нужен. Решения лежат в разных папках (Arkhipov/2.3.3, Arkhipov/Labs/…),
а общие проверки — в Mods/custom_assertions.py. Чтобы импорт работал из любого места,
папку с модулями ищут вверх по дереву, а не «отсчитывают точки вручную».

Как было раньше (так делать не надо):

    repo_root = os.path.abspath(os.path.join(current_file, "..", "..", ".."))
    mods_path = os.path.join(repo_root, "Mods")

Такая запись ломается от любого переезда файла: число «..» зависит от того,
насколько глубоко лежит скрипт. Здесь вместо этого — поиск папки по признаку.

Использование: скопировать блок ниже в начало скрипта и при необходимости вызвать
connect_mods() — он добавит папку Mods в sys.path и вернёт её путь.
"""

from __future__ import annotations

import sys
from pathlib import Path

MODULE_MARKER = "custom_assertions.py"  # по этому файлу узнаём папку с модулями
MODS_DIRNAME = "Mods"


def find_mods_dir(start: Path | None = None) -> Path | None:
    """Ищет папку Mods от текущего файла вверх по дереву каталогов.

    Параметры
    ----------
    start : Path | None
        С чего начинать поиск. По умолчанию — папка текущего файла.

    Возврат
    -------
    Path | None
        Путь к папке с модулями или None, если она не найдена.
    """
    current = (start or Path(__file__).resolve().parent).resolve()
    for candidate in (current, *current.parents):
        folder = candidate / MODS_DIRNAME
        if (folder / MODULE_MARKER).is_file():
            return folder
    return None


def connect_mods() -> Path:
    """Добавляет папку Mods в sys.path и возвращает её путь."""
    mods = find_mods_dir()
    if mods is None:
        raise FileNotFoundError(
            f"Папка {MODS_DIRNAME} с модулем {MODULE_MARKER} не найдена. "
            "Проверь, что шаблон скопирован внутрь 04_Код."
        )
    if str(mods) not in sys.path:
        sys.path.insert(0, str(mods))
    return mods


if __name__ == "__main__":
    # Проверка самого шаблона: где он видит папку с модулями.
    MODS = connect_mods()
    print(f"Папка с модулями: {MODS}")
    print(f"Файлы в ней: {[p.name for p in sorted(MODS.glob('*.py'))]}")
