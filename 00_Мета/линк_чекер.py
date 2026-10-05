#!/usr/bin/env python3
"""Проверка ссылок в заметках базы (включая 00_Мета, которую проверка_базы.py не сканирует).

Проверяет:
  * [[заметка]]                        — существует ли заметка;
  * [[заметка|текст]]                  — то же, алиас игнорируется;
  * [[заметка#Заголовок]]              — существует ли заголовок;
  * [[заметка#^якорь]]                 — существует ли блок-якорь;
  * [[папка/заметка]]                  — путь от корня хранилища;
  * неоднозначность: несколько заметок с одним именем.

Запуск:
    python3 00_Мета/линк_чекер.py                 # всё хранилище
    python3 00_Мета/линк_чекер.py 00_Мета         # только каталог
    python3 00_Мета/линк_чекер.py --strict        # неоднозначные ссылки = ошибка
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

VAULT = Path(__file__).resolve().parent.parent

WIKILINK = re.compile(r"\[\[([^\[\]\n]+?)\]\]")
HEADING = re.compile(r"^(#{1,6})\s+(.*?)\s*$")
BLOCK_ANCHOR = re.compile(r"\^([A-Za-z0-9][A-Za-z0-9-]*)\s*$")
FRONTMATTER = re.compile(r"\A---\n.*?\n---\n", re.S)
FENCED_BLOCK = re.compile(r"^(```|~~~)")
INLINE_CODE = re.compile(r"`[^`]*`")

SKIP_DIRS = {".git", ".obsidian", "node_modules", ".arena", ".cache", ".venv"}
ATTACH_DIRS = ["Вложения", "Диаграммы"]


def notes() -> list[Path]:
    out = []
    for p in VAULT.rglob("*.md"):
        if any(part in SKIP_DIRS for part in p.parts):
            continue
        out.append(p)
    return sorted(out)


def split_frontmatter(text: str) -> tuple[int, str]:
    # Возвращает (число строк YAML-шапки, тело): номера строк совпадают с файлом.
    m = FRONTMATTER.match(text)
    if not m:
        return 0, text
    return m.group(0).count("\n"), text[m.end():]


class Index:
    def __init__(self) -> None:
        self.by_stem: dict[str, list[Path]] = {}
        self.by_relpath: dict[str, Path] = {}
        self.headings: dict[Path, set[str]] = {}
        self.anchors: dict[Path, set[str]] = {}
        for p in notes():
            rel = p.relative_to(VAULT).as_posix()
            self.by_relpath[rel] = p
            self.by_relpath[rel[:-3]] = p  # без .md
            self.by_stem.setdefault(p.stem, []).append(p)
            heads: set[str] = set()
            anchors: set[str] = set()
            for line in split_frontmatter(p.read_text(encoding="utf-8"))[1].splitlines():
                m = HEADING.match(line)
                if m:
                    # якорь в конце заголовка — часть разметки, а не текста заголовка
                    heads.add(BLOCK_ANCHOR.sub("", m.group(2)).strip())
                a = BLOCK_ANCHOR.search(line)
                if a:
                    anchors.add(a.group(1))
            self.headings[p] = heads
            self.anchors[p] = anchors
        # вложения: [[Pasted image ….png]] и [[Схема.drawio.svg]]
        for d in ATTACH_DIRS:
            base = VAULT / d
            if not base.is_dir():
                continue
            for p in base.rglob("*"):
                if not p.is_file():
                    continue
                rel = p.relative_to(VAULT).as_posix()
                self.by_relpath[rel] = p
                self.by_relpath[p.name] = p
                self.by_relpath[p.stem] = p
                self.headings[p] = set()
                self.anchors[p] = set()

    def resolve(self, target: str) -> tuple[Path | None, list[Path]]:
        """Возвращает (точное совпадение, список кандидатов при неоднозначности).

        Obsidian разрешает путь не только от корня хранилища, но и по любому
        окончанию пути (`[[папка/заметка]]`), поэтому проверяем и суффиксы.
        """
        target = target.strip()
        if target in self.by_relpath:
            return self.by_relpath[target], []
        suffix = "/" + target if not target.startswith("/") else target
        hits = [p for rel, p in self.by_relpath.items() if rel.endswith(suffix)]
        if len(hits) == 1:
            return hits[0], []
        if len(hits) > 1:
            return hits[0], list(dict.fromkeys(hits))
        cand = self.by_stem.get(target, [])
        if len(cand) == 1:
            return cand[0], []
        if len(cand) > 1:
            return cand[0], cand
        return None, []


def check(root: Path | None, strict: bool) -> int:
    idx = Index()
    files = [p for p in notes() if root is None or root in p.parents or p.parent == root]
    problems: list[str] = []
    warnings: list[str] = []
    total = 0
    for p in files:
        rel = p.relative_to(VAULT).as_posix()
        in_fence = False
        offset, body = split_frontmatter(p.read_text(encoding="utf-8"))
        for n, raw_line in enumerate(body.splitlines(), start=offset + 1):
            if FENCED_BLOCK.match(raw_line.strip()):
                in_fence = not in_fence
                continue
            if in_fence:
                continue
            line = INLINE_CODE.sub("", raw_line)  # ссылки-примеры внутри `кода` не проверяем
            for m in WIKILINK.finditer(line):
                inner = m.group(1).strip()
                # `[[0, 2, 6]]` и `[[1.0, 2.0]]` в коде — не ссылки, а литералы списков
                if re.fullmatch(r"[\d\s.,\[\]]+", inner):
                    continue
                # алиас отделяется символом |; внутри таблиц его экранируют как \|
                link_part = re.split(r"\\\||\|", inner, maxsplit=1)[0].strip()
                raw = link_part
                total += 1
                target, _, fragment = raw.partition("#")
                fragment = fragment.strip()
                note, ambiguous = idx.resolve(target) if target else (p, [])
                if note is None:
                    problems.append(f"{rel}:{n}: битая ссылка [[{raw}]]")
                    continue
                if ambiguous:
                    msg = f"{rel}:{n}: неоднозначная ссылка [[{raw}]] — {len(ambiguous)} заметок"
                    (problems if strict else warnings).append(msg)
                if fragment.startswith("^"):
                    if fragment[1:] not in idx.anchors[note]:
                        problems.append(
                            f"{rel}:{n}: нет блок-якоря {fragment} в "
                            f"{note.relative_to(VAULT).as_posix()}"
                        )
                elif fragment and fragment not in idx.headings[note]:
                    problems.append(
                        f"{rel}:{n}: нет заголовка «{fragment}» в "
                        f"{note.relative_to(VAULT).as_posix()}"
                    )
    print(f"проверено файлов: {len(files)} | ссылок: {total}")
    print(f"проблем: {len(problems)} | предупреждений: {len(warnings)}")
    for w in warnings:
        print("  !", w)
    for pr in problems:
        print("  x", pr)
    return 1 if problems else 0


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("root", nargs="?", help="каталог внутри хранилища (например 00_Мета)")
    ap.add_argument("--strict", action="store_true", help="неоднозначные ссылки считать ошибкой")
    args = ap.parse_args()
    root = (VAULT / args.root) if args.root else None
    if root and not root.exists():
        print(f"нет каталога {root}")
        return 2
    return check(root, args.strict)


if __name__ == "__main__":
    sys.exit(main())
