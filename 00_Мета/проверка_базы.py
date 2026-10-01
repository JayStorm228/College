#!/usr/bin/env python3
"""Проверка базы конспектов: YAML, пустые заголовки, задачи, ссылки, код.

Запускается перед сдачей работы по дисциплине — чтобы «проверено» в [[Журнал_изменений]]
означало реально прогнанную проверку, а не обещание.

Что проверяется:

1. **YAML** — порядок ключей по контракту [[Соглашения]], обязательные поля, формат даты,
   допустимый `status`, минимум 3 тега. В лекциях, практиках и мини-проектах `02_Курсы/`
   дата запрещена; отсутствие или пустое значение `status` трактуется как `черновик`.
2. **Пустые заголовки** — заголовок без текста. Разрешён только как разделитель групп:
   если сразу за ним идёт заголовок более глубокого уровня, это нормально.
3. **Задачи** — открытые `- [ ] #task` в заметках со `status: готово`, и задачи без даты `📅`.
4. **Ссылки** — резолвятся ли `[[вики-ссылки]]`: файл, заголовок раздела, блок-якорь `^xxxxxx`,
   вложение; отдельно — неоднозначные (короткие имена, совпадающие у нескольких файлов).
5. **Код** — компилируются ли блоки ```python в конспектах.

Использование:
    python3 00_Мета/проверка_базы.py
    python3 00_Мета/проверка_базы.py --subject 02          # только одна дисциплина
    python3 00_Мета/проверка_базы.py --no-code             # без тяжёлой проверки кода

Код возврата: 0 — проблем нет, 1 — есть проблемы.
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

VAULT = Path(__file__).resolve().parent.parent
SUBJECTS_DIR = VAULT / "01_Дисциплины"
COURSES_DIR = VAULT / "02_Курсы"
ATTACH_DIRS = [VAULT / "Вложения", VAULT / "Диаграммы"]
# Папки, которые в проверку не входят: служебные и вложенные репозитории с кодом.
SKIP_DIRS = {".obsidian", "_Экспорт", ".git", "node_modules"}
VENDOR_MARKERS = ("pyproject.toml", ".gitignore", ".python-version")
# Служебные заметки внутри дисциплин: это не учебный материал, YAML-контракт к ним не применяется.
SERVICE_NAMES = {"README.md", "ПРОЧТИ_МЕНЯ.md"}

RUN_ORDER = ["date", "subject", "teacher", "type", "related_lecture", "tags", "author", "status"]
BASE_REQUIRED = ["subject", "type", "tags", "author", "status"]
STATUSES = {"черновик", "в работе", "готово"}
TYPES = {"лекция", "практика", "сообщение", "курс", "аудит", "контекст", "соглашение", "реестр", "бэклог", "журнал"}

FENCE = re.compile(r"^```(\w*)\s*$")
HEADING = re.compile(r"^(#{1,6})\s+(.*)$")
LINK = re.compile(r"!?\[\[([^\]\|#^]+)(?:#([^\]\|]+))?(?:\|[^\]]*)?\]\]")
ANCHOR = re.compile(r"\^([A-Za-z0-9]{4,})\s*$", re.MULTILINE)
TASK = re.compile(r"^- \[ \] #task(.*)$", re.MULTILINE)
TASK_PLAIN = re.compile(r"^- \[ \] (?!.*#task)(.*)$", re.MULTILINE)


class Report:
    def __init__(self) -> None:
        self.problems: list[str] = []
        self.warnings: list[str] = []

    def bad(self, where: Path | str, what: str) -> None:
        self.problems.append(f"{where}: {what}")

    def warn(self, where: Path | str, what: str) -> None:
        self.warnings.append(f"{where}: {what}")


def is_skipped(path: Path) -> bool:
    """Служебные папки, служебные заметки и вложенные репозитории (папка с кодом — не заметка)."""
    rel = path.relative_to(VAULT)
    if any(part in SKIP_DIRS for part in rel.parts):
        return True
    if path.name in SERVICE_NAMES:
        return True
    for parent in path.parents:
        if parent == VAULT:
            break
        if any((parent / marker).exists() for marker in VENDOR_MARKERS):
            return True
    return False


def notes_under(subject_filter: str | None) -> list[Path]:
    """Проверяемые заметки: дисциплины и курсы, кроме служебного и вложенных репозиториев."""
    roots: list[Path] = []
    for base in (SUBJECTS_DIR, COURSES_DIR):
        if base.is_dir():
            roots += [p for p in sorted(base.iterdir()) if p.is_dir()]
    if subject_filter:
        roots = [p for p in roots if p.name.startswith(subject_filter)]
    return sorted(p for r in roots for p in r.rglob("*.md") if not is_skipped(p))


def indexable_notes() -> list[Path]:
    """Все заметки хранилища — по ним резолвятся ссылки (в том числе в 00_Мета/)."""
    return sorted(p for p in VAULT.rglob("*.md") if not is_skipped(p))


def split_front_matter(text: str) -> tuple[dict[str, object], str]:
    """Возвращает (YAML как словарь, тело заметки). Понимает только простые ключи и списки."""
    m = re.match(r"^---\n(.*?)\n---\n?", text, re.S)
    if not m:
        return {}, text
    body = text[m.end():]
    data: dict[str, object] = {}
    keys_order: list[str] = []
    current: str | None = None
    for line in m.group(1).splitlines():
        if line.startswith("  - ") and current:
            if not isinstance(data.get(current), list):
                data[current] = []
            data[current].append(line[4:].strip())  # type: ignore[union-attr]
            continue
        if ":" in line and not line.startswith(" "):
            key, _, value = line.partition(":")
            current = key.strip()
            keys_order.append(current)
            data[current] = value.strip()
    data["__order__"] = keys_order  # type: ignore[assignment]
    return data, body


def is_course_material(path: Path) -> bool:
    """Заметка внутри папки отдельного курса, но не его оглавление."""
    try:
        relative = path.relative_to(COURSES_DIR)
    except ValueError:
        return False
    return len(relative.parts) > 1 and not path.name.startswith("00. ")


def is_course_outline(path: Path) -> bool:
    """Оглавление конкретного курса; именно в нём хранится дата создания курса."""
    try:
        relative = path.relative_to(COURSES_DIR)
    except ValueError:
        return False
    return len(relative.parts) > 1 and path.name.startswith("00. ")


def check_yaml(path: Path, fm: dict[str, object], rep: Report) -> str:
    rel = path.relative_to(VAULT)
    if not fm:
        rep.bad(rel, "нет YAML-заголовка")
        return "черновик"
    order = fm.get("__order__", [])
    assert isinstance(order, list)
    filtered = [k for k in order if k in RUN_ORDER]
    expected = [k for k in RUN_ORDER if k in filtered]
    if filtered != expected:
        rep.bad(rel, f"порядок ключей YAML: {filtered} вместо {expected}")

    required = BASE_REQUIRED.copy()
    course_outline = is_course_outline(path)
    if course_outline or not is_course_material(path):
        required.insert(0, "date")
    for key in required:
        if not str(fm.get(key, "")).strip():
            rep.bad(rel, f"пустое обязательное поле `{key}`")

    date = str(fm.get("date", "")).strip()
    if date and not re.fullmatch(r"\d{4}-\d{2}-\d{2}", date):
        rep.bad(rel, f"дата `{date}` не соответствует формату YYYY-MM-DD")
    if is_course_material(path) and date:
        rep.bad(rel, "поле `date` не используется в лекциях, практиках и мини-проектах курсов")

    raw_status = str(fm.get("status", "")).strip()
    status = raw_status or "черновик"
    if not raw_status:
        rep.warn(rel, "пустой или отсутствующий status трактуется как «черновик»")
    if status not in STATUSES:
        rep.bad(rel, f"недопустимый status «{status}»")
    type_ = str(fm.get("type", ""))
    if type_ and type_ not in TYPES:
        rep.warn(rel, f"необычный type «{type_}» (проверь [[Соглашения]])")
    tags = fm.get("tags")
    if isinstance(tags, list):
        n_tags = len(tags)
    elif isinstance(tags, str) and tags.strip():
        n_tags = len([t for t in re.split(r"[,\s]+", tags) if t])
    else:
        n_tags = 0
    if 0 < n_tags < 3:
        rep.bad(rel, f"тегов {n_tags} — по контракту минимум 3")
    return status


def body_lines(body: str) -> list[str]:
    """Строки тела без содержимого код-блоков: в конспекте код не считается текстом раздела."""
    out, in_fence, fence_marker = [], False, ""
    for line in body.splitlines():
        m = FENCE.match(line.strip())
        if m:
            marker = line.strip()
            if not in_fence:
                in_fence, fence_marker = True, marker
            elif marker.startswith(fence_marker[:3]):
                in_fence = False
            out.append("")
            continue
        out.append("" if in_fence else line)
    return out


def check_headings(path: Path, body: str, rep: Report) -> int:
    rel = path.relative_to(VAULT)
    lines = body_lines(body)
    empty = 0
    for i, line in enumerate(lines):
        m = HEADING.match(line)
        if not m:
            continue
        level = len(m.group(1))
        j = i + 1
        while j < len(lines) and not lines[j].strip():
            j += 1
        if j >= len(lines):
            if not m.group(2).strip():
                rep.bad(rel, "заголовок без названия в конце файла")
            else:
                empty += 1
            continue
        nxt = HEADING.match(lines[j])
        if nxt:
            if len(nxt.group(1)) <= level:  # нет дочерних — значит заголовок пустой
                empty += 1
                if not m.group(2).strip():
                    rep.bad(rel, f"заголовок без названия: `{line.strip()}`")
    return empty


def check_tasks(path: Path, body: str, status: str, rep: Report) -> int:
    rel = path.relative_to(VAULT)
    tasks = list(TASK.finditer(body)) + list(TASK_PLAIN.finditer(body))
    if status == "готово" and tasks:
        rep.bad(rel, f"status «готово», но открытых задач {len(tasks)}")
    for t in TASK.finditer(body):
        if "📅" not in t.group(1):
            rep.warn(rel, f"задача без даты 📅: {t.group(1).strip()[:60]}")
    return len(tasks)


def build_index(notes: list[Path]) -> tuple[dict[str, list[Path]], dict[str, Path]]:
    by_stem: dict[str, list[Path]] = {}
    for n in notes:
        for key in {n.stem.lower(), n.stem.lower().replace("_", " ")}:
            bucket = by_stem.setdefault(key, [])
            if n not in bucket:
                bucket.append(n)
    attachments: dict[str, Path] = {}
    for d in ATTACH_DIRS:
        if d.is_dir():
            for f in d.iterdir():
                attachments[f.name.lower()] = f
    return by_stem, attachments


def resolve_relative(target: str, notes: list[Path]) -> list[Path]:
    """Ссылка вида [[01_Технология_Разработки_ПО/00_Курс]] — поиск по хвосту пути."""
    needle = target.lower().strip("/")
    out = []
    for n in notes:
        rel = n.relative_to(VAULT).with_suffix("").as_posix().lower()
        if rel == needle or rel.endswith("/" + needle):
            out.append(n)
    return out


def headings_of(path: Path) -> set[str]:
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return set()
    return {HEADING.match(l).group(2).strip().lower() for l in text.splitlines() if HEADING.match(l)}


def check_links(
    path: Path,
    body: str,
    by_stem: dict[str, list[Path]],
    attachments: dict[str, Path],
    rep: Report,
    all_notes: list[Path] | None = None,
) -> tuple[int, int]:
    rel = path.relative_to(VAULT)
    checked = warnings = 0
    # внутри блоков кода (```...```) ссылок нет: там примеры, TOML-таблицы и т.п.
    searchable = re.sub(r"```.*?```", " ", body, flags=re.DOTALL)
    # внутри инлайн-кода (`...`) ссылки не работают и в Obsidian — там они просто текст
    searchable = re.sub(r"`[^`\n]*`", " ", searchable)
    for m in LINK.finditer(searchable):
        # в таблицах пайп экранируется: [[Заметка\|подпись]] — обратный слэш не часть имени
        target, section = m.group(1).strip().rstrip("\\").strip(), (m.group(2) or "").strip().rstrip("\\").strip()
        # `[[0, 2, 4]]` — это индексация в примерах NumPy, а не вики-ссылка.
        # Признак кода: ни одной буквы и есть запятая или пробел внутри.
        # Имена заметок вида `[[23-09-2026]]` так не отсеиваются.
        has_letter = re.search(r"[A-Za-zА-Яа-яЁё]", target)
        if not has_letter and ("," in target or " " in target):
            continue
        checked += 1
        if target.lower() in attachments:
            continue
        candidates = by_stem.get(target.lower(), [])
        if not candidates and "/" in target:
            candidates = resolve_relative(target, all_notes or [])
        if not candidates:
            rep.bad(rel, f"битая ссылка: [[{target}]]")
            continue
        if len(candidates) > 1:
            warnings += 1
            rep.warn(rel, f"неоднозначная ссылка [[{target}]] → {[str(c.relative_to(VAULT)) for c in candidates]}")
        note = candidates[0]
        if section:
            if section.startswith("^"):
                anchors = set(ANCHOR.findall(note.read_text(encoding="utf-8")))
                if section[1:] not in anchors:
                    rep.bad(rel, f"нет блок-якоря {section} в {note.name}")
            else:
                heads = headings_of(note)
                head = section.split("|")[0].strip().lower()
                if head not in heads and not any(h.startswith(head) for h in heads):
                    # ссылка может вести на подзаголовок внутри секции — считаем предупреждением
                    rep.warn(rel, f"ссылка на раздел «{section}» — точного заголовка нет в {note.name}")
    return checked, warnings


def check_code(path: Path, body: str, rep: Report) -> tuple[int, int]:
    rel = path.relative_to(VAULT)
    total = broken = 0
    for i, (lang, code) in enumerate(re.findall(r"```(\w*)\n(.*?)```", body, re.S), 1):
        if lang not in ("python", "py"):
            continue
        total += 1
        # Код может лежать внутри врезки: каждая строка начинается с "> ". Снимаем префикс,
        # иначе блок не компилируется и проверка ругается на исправный код.
        src = "\n".join(re.sub(r"^\s*>\s?", "", line) for line in code.splitlines())
        src = src.replace("\t", "    ")
        try:
            compile(src, f"{path.name}#{i}", "exec")
        except SyntaxError as e:
            broken += 1
            line_no = e.lineno or 1
            snippet = code.splitlines()[line_no - 1].strip() if 0 < line_no <= len(code.splitlines()) else ""
            rep.bad(rel, f"блок {i} не компилируется (строка {line_no}): {e.msg} | {snippet[:60]}")
    return total, broken


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--subject", help="проверять только дисциплину или курс с таким началом имени папки (например 02)")
    parser.add_argument("--no-code", action="store_true", help="не компилировать python-блоки")
    args = parser.parse_args()

    notes = notes_under(args.subject)
    if not notes:
        print("заметки не найдены", file=sys.stderr)
        return 1

    rep = Report()
    all_notes = indexable_notes()
    by_stem, attachments = build_index(all_notes)

    stat = {"заметок": len(notes), "python-блоков": 0, "сломанных блоков": 0,
            "пустых заголовков": 0, "задач": 0, "ссылок": 0, "неоднозначных ссылок": 0}

    for note in notes:
        text = note.read_text(encoding="utf-8")
        fm, body = split_front_matter(text)
        status = check_yaml(note, fm, rep)
        stat["пустых заголовков"] += check_headings(note, body, rep)
        stat["задач"] += check_tasks(note, body, status, rep)
        checked, warned = check_links(note, body, by_stem, attachments, rep, all_notes)
        stat["ссылок"] += checked
        stat["неоднозначных ссылок"] += warned
        if not args.no_code:
            total, broken = check_code(note, body, rep)
            stat["python-блоков"] += total
            stat["сломанных блоков"] += broken

    print("=== Проверка базы ===")
    for key, value in stat.items():
        print(f"  {key:<22} {value}")
    print(f"  проблем: {len(rep.problems)} | предупреждений: {len(rep.warnings)}")

    if rep.problems:
        print("\n--- ПРОБЛЕМЫ ---")
        for p in rep.problems:
            print("  ✗", p)
    if rep.warnings:
        print("\n--- ПРЕДУПРЕЖДЕНИЯ ---")
        for w in rep.warnings:
            print("  !", w)

    return 1 if rep.problems else 0


if __name__ == "__main__":
    raise SystemExit(main())
