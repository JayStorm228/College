#!/usr/bin/env python3
"""Аудит базы по контракту [[Соглашения]] — без правки текстов, только замер.

Считает по каждой заметке:
  * YAML: наличие, обязательные поля, порядок ключей, значения `type`/`status`;
  * структуру: обязательные разделы лекции/практики (по префиксу заголовка H1);
  * правило Р6: Mermaid-диаграммы, пояснение «для чайника», академический H1;
  * самодостаточность: блок «Связи с другими темами»;
  * объём в словах.

Отчёт печатается таблицей по разделам и списком приоритетов. Файлы не изменяются.

Запуск:
    python3 00_Мета/аудит_базы.py                  # сводка
    python3 00_Мета/аудит_базы.py --csv audit.csv  # + построчная выгрузка
    python3 00_Мета/аудит_базы.py --only 02_Курсы  # один раздел
"""

from __future__ import annotations

import argparse
import csv
import re
from collections import Counter, defaultdict
from pathlib import Path

VAULT = Path(__file__).resolve().parent.parent
ROOTS = ["01_Дисциплины", "02_Курсы"]

REQUIRED_YAML = ["subject", "type", "tags", "author", "status"]
YAML_ORDER = ["date", "subject", "teacher", "type", "related_lecture", "tags", "author", "status"]
TYPES = {"лекция", "практика", "сообщение", "курс", "аудит", "контекст", "соглашение",
         "реестр", "бэклог", "журнал"}
STATUSES = {"черновик", "в работе", "готово"}

# Обязательные разделы: проверяем по префиксу заголовка H1, суффиксы допустимы
# («Типичные заблуждения — коротко», «Связи» и т. п.).
LECTURE_SECTIONS = ["Ключевые термины", "Типичные заблуждения", "Связи"]
PRACTICE_SECTIONS = ["Ход работы", "Вывод", "Связи"]

FRONTMATTER = re.compile(r"\A---\n(.*?)\n---\n", re.S)
HEADING1 = re.compile(r"^#\s+(.*)$")
MERMAID = re.compile(r"```mermaid")
TEA = re.compile(r"для чайника|Пояснение для начинающих|для начинающих", re.I)
SKIP_DIRS = {".git", ".obsidian", "node_modules"}


def parse_yaml(text: str) -> dict[str, str]:
    m = FRONTMATTER.match(text)
    if not m:
        return {}
    out: dict[str, str] = {}
    last = None
    for line in m.group(1).splitlines():
        kv = re.match(r"^([A-Za-z_][A-Za-z0-9_]*):\s*(.*)$", line)
        if kv:
            out[kv.group(1)] = kv.group(2).strip()
            last = kv.group(1)
            continue
        item = re.match(r"^\s+-\s+(.*)$", line)
        if item and last:  # элемент списка (tags:)
            out[last] = (out[last] + " " + item.group(1).strip()).strip()
    return out


def headings(text: str) -> list[str]:
    body = FRONTMATTER.sub("", text)
    return [m.group(1).strip() for m in (HEADING1.match(l) for l in body.splitlines()) if m]


def section_missing(hs: list[str], prefix: str) -> bool:
    return not any(h.lower().startswith(prefix.lower()) for h in hs)


def audit_note(rel: Path) -> dict:
    p = VAULT / rel
    text = p.read_text(encoding="utf-8")
    y = parse_yaml(text)
    hs = headings(text)
    typ = y.get("type", "").strip('"')
    need = PRACTICE_SECTIONS if typ == "практика" else LECTURE_SECTIONS
    missing = [s for s in need if section_missing(hs, s)] if typ in ("лекция", "практика") else []
    keys = [k for k in y if k in YAML_ORDER]
    ordered = keys == sorted(keys, key=YAML_ORDER.index)
    return {
        "path": rel.as_posix(),
        "раздел": rel.parts[0],
        "курс/дисциплина": rel.parts[1] if len(rel.parts) > 2 else "",
        "файл": rel.name,
        "type": typ or "—",
        "status": y.get("status", "") or "—",
        "yaml": 0 if not y else 1,
        "нет_полей": ",".join(k for k in REQUIRED_YAML if not y.get(k)),
        "порядок_yaml": 1 if ordered else 0,
        "type_верный": 1 if typ in TYPES else 0,
        "status_верный": 1 if y.get("status", "") in STATUSES else 0,
        "mermaid": len(MERMAID.findall(text)),
        "чайник": 1 if TEA.search(text) else 0,
        "нет_разделов": ",".join(missing),
        "слов": len(re.findall(r"\S+", FRONTMATTER.sub("", text))),
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--csv", help="построчная выгрузка в CSV")
    ap.add_argument("--only", help="проверить только этот раздел (01_Дисциплины / 02_Курсы)")
    args = ap.parse_args()

    rows = []
    for root in ROOTS:
        if args.only and root != args.only:
            continue
        base = VAULT / root
        for p in sorted(base.rglob("*.md")):
            if any(part in SKIP_DIRS for part in p.parts):
                continue
            rows.append(audit_note(p.relative_to(VAULT)))

    total = len(rows)
    lect = [r for r in rows if r["type"] == "лекция"]
    prac = [r for r in rows if r["type"] == "практика"]

    print(f"=== Аудит базы по контракту [[Соглашения]] (замер, без правок) ===")
    print(f"заметок: {total}  |  лекций: {len(lect)}  практик: {len(prac)}  "
          f"оглавлений: {sum(1 for r in rows if r['type'] == 'курс')}")
    print()

    def line(label: str, bad: list[dict], note: str = "") -> None:
        print(f"{label:<46} {len(bad):>4}  {note}")

    print("--- Соответствие контракту ---")
    line("без YAML-шапки", [r for r in rows if not r["yaml"]])
    line("не хватает обязательных полей YAML", [r for r in rows if r["нет_полей"]])
    line("нарушен порядок ключей YAML", [r for r in rows if r["yaml"] and not r["порядок_yaml"]])
    line("неизвестное значение type", [r for r in rows if r["yaml"] and not r["type_верный"]])
    line("неизвестное значение status", [r for r in rows if r["yaml"] and not r["status_верный"]])
    line("нет обязательных разделов (лекция/практика)",
         [r for r in rows if r["нет_разделов"]])
    print()

    print("--- Правило Р6: наглядность и «для чайника» ---")
    line("лекции без Mermaid", [r for r in lect if r["mermaid"] == 0], "(нужно 1–2)")
    line("лекции с 1 диаграммой", [r for r in lect if r["mermaid"] == 1], "(эталон 3–5)")
    line("лекции без пояснения «для чайника»", [r for r in lect if not r["чайник"]])
    # «академический заголовок» из Р6 не автоматизируется: «Жизненный цикл ПО» академичен,
    # а формальный список слов-маркеров даёт десятки ложных срабатываний. Проверяется глазами.
    print()

    print("--- Статусы ---")
    for st, n in Counter(r["status"] for r in rows).most_common():
        print(f"  {st:<12} {n}")
    gotovo_no_mer = [r for r in lect if r["status"] == "готово" and r["mermaid"] == 0]
    print(f"  из них «готово» без единой диаграммы: {len(gotovo_no_mer)}")
    print()

    print("--- Разбивка по разделам ---")
    by = defaultdict(list)
    for r in rows:
        by[r["курс/дисциплина"] or r["раздел"]].append(r)
    print(f"{'раздел':<44} {'n':>4} {'безMer':>7} {'безЧай':>7} {'безРазд':>8}")
    for k in sorted(by):
        g = by[k]
        print(f"{k[:43]:<44} {len(g):>4} "
              f"{sum(1 for r in g if r['type'] == 'лекция' and r['mermaid'] == 0):>7} "
              f"{sum(1 for r in g if r['type'] == 'лекция' and not r['чайник']):>7} "
              f"{sum(1 for r in g if r['нет_разделов']):>8}")

    if args.csv:
        out = Path(args.csv)
        with out.open("w", encoding="utf-8", newline="") as f:
            w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
            w.writeheader()
            w.writerows(rows)
        print(f"\nCSV: {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
