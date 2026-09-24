#!/usr/bin/env python3
"""Сборка базы конспектов в файлы-источники для NotebookLM (Gemini Notebook).

Один файл на дисциплину. Берётся только папка 01_Дисциплины/.
Из текста вырезаются блоки dataview и строки блок-якорей Obsidian (^xxxxxx) —
в выгрузке это шум, который не несёт учебного смысла.

Использование:
    python3 00_Мета/экспорт_в_notebooklm.py
    python3 00_Мета/экспорт_в_notebooklm.py --out _Экспорт
"""
from __future__ import annotations

import argparse
import re
from pathlib import Path

VAULT = Path(__file__).resolve().parent.parent
SUBJECTS_DIR = VAULT / "01_Дисциплины"

DATAVIEW_BLOCK = re.compile(r"```dataview\n.*?```", re.DOTALL)
BLOCK_ANCHOR = re.compile(r"^\^[A-Za-z0-9]{4,}\s*$", re.MULTILINE)
EXTRA_BLANK = re.compile(r"\n{3,}")

# Вложенные репозитории с кодом (например CollegeProgramming-master) в выгрузку не идут:
# их README — служебный текст, а не учебный материал, и он попадал в источник NotebookLM.
VENDOR_MARKERS = ("pyproject.toml", ".gitignore", ".python-version")


def clean(text: str) -> str:
    """Убирает из markdown то, что в выгрузке является шумом."""
    text = DATAVIEW_BLOCK.sub("_(таблица строится плагином Dataview в Obsidian)_", text)
    text = BLOCK_ANCHOR.sub("", text)
    return EXTRA_BLANK.sub("\n\n", text).strip() + "\n"


def word_count(text: str) -> int:
    return len(re.findall(r"[\wА-Яа-яёЁ\-\+]+", text))


def in_vendored_repo(path: Path, stop: Path) -> bool:
    """Файл лежит внутри вложенного репозитория (папки с признаками проекта на Python)."""
    for parent in path.parents:
        if parent == stop:
            return False
        if any((parent / marker).exists() for marker in VENDOR_MARKERS):
            return True
    return False


def build_subject(subject_dir: Path) -> tuple[str, int, int]:
    """Склеивает все заметки дисциплины в один документ.

    Возвращает (текст, число заметок, число пропущенных файлов вложенных репозиториев).
    """
    all_md = sorted(subject_dir.rglob("*.md"))
    notes = [p for p in all_md if not in_vendored_repo(p, subject_dir)]
    skipped = len(all_md) - len(notes)
    parts = [
        f"# Дисциплина: {subject_dir.name}\n",
        f"Всего материалов: {len(notes)}\n",
    ]
    for note in notes:
        rel = note.relative_to(subject_dir).with_suffix("")
        parts.append(f"\n\n---\n\n<!-- материал: {rel} -->\n")
        parts.append(clean(note.read_text(encoding="utf-8")))
    return "".join(parts), len(notes), skipped


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", default="_Экспорт", help="папка назначения (относительно корня базы)")
    args = parser.parse_args()

    out_dir = VAULT / args.out
    out_dir.mkdir(parents=True, exist_ok=True)

    total_words = 0
    total_skipped = 0
    print(f"{'дисциплина':<44}{'заметок':>8}{'слов':>9}  файл")
    for subject_dir in sorted(p for p in SUBJECTS_DIR.iterdir() if p.is_dir()):
        body, n_notes, skipped = build_subject(subject_dir)
        target = out_dir / f"{subject_dir.name}.md"
        target.write_text(body, encoding="utf-8")
        words = word_count(body)
        total_words += words
        total_skipped += skipped
        tail = f"  (+{skipped} служебных пропущено)" if skipped else ""
        print(f"{subject_dir.name[:43]:<44}{n_notes:>8}{words:>9}  {target.relative_to(VAULT)}{tail}")

    limit = 500_000
    print(f"\nвсего слов: {total_words} (лимит NotebookLM — {limit} на источник)")
    if total_skipped:
        print(f"пропущено служебных .md (вложенные репозитории): {total_skipped}")
    print(f"готово, файлы в {out_dir.relative_to(VAULT)}/")


if __name__ == "__main__":
    main()
