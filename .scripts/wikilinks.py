"""Ссылки на заголовки вики (An Otter Wiki v2.25).

    python .scripts/wikilinks.py check          проверить все ссылки
    python .scripts/wikilinks.py tables         показать, что поменяется в таблицах
    python .scripts/wikilinks.py tables --write записать изменения
    python .scripts/wikilinks.py archetypes     ссылки на навыки, таланты и трейты
                                                в архетипах (--write — записать)

id заголовка считается так же, как в движке: NFKD → выкинуть не-ASCII →
strip → lower → удалить пунктуацию → пробелы/дефисы в один дефис.
Поэтому «Steel / Сталь» → steel-, а заголовок только из кириллицы получает
номер по порядку (-1, -2…).
"""

import re
import sys
import unicodedata
from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import unquote

ROOT = Path(__file__).resolve().parent.parent
SKIP_DIRS = {".git", ".claude", ".scripts", "_docs"}
ITEM_SECTION = "iv арсенал/"

HEADING_RE = re.compile(r"^(#{1,6})[ \t]+(.*?)[ \t]*#*[ \t]*$")
FENCE_RE = re.compile(r"^[ \t]*(```|~~~)")
LINK_RE = re.compile(r"(?<!!)\[([^\]]*)\]\(([^)\s]*)\)")
WIKILINK_RE = re.compile(r"\[\[([^\]]+)\]\]")
TABLE_SEP_RE = re.compile(r"^\|?\s*:?-{3,}:?\s*(\|\s*:?-{3,}:?\s*)*\|?\s*$")


def slugify(text):
    s = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode()
    s = s.strip().lower()
    s = re.sub(r"[^\w\s-]", "", s)
    return re.sub(r"[-\s]+", "-", s)


def plain(text):
    """Текст ячейки/заголовка без разметки ссылок и выделения."""
    text = LINK_RE.sub(r"\1", text)
    return re.sub(r"[*_`]", "", text).strip()


def keys(text):
    """Варианты имени для сопоставления: целиком, английская и русская часть.

    Скобки в конце («(15 м)», «(тяжёлый)») отбрасываются.
    """
    text = plain(text).replace("’", "'").replace("ё", "е").replace("Ё", "Е")
    out = set()
    for part in [text, *text.split(" / ")]:
        part = re.sub(r"\s*\([^)]*\)\s*$", "", part).strip().lower()
        if part:
            out.add(part)
    return out


@dataclass
class Heading:
    text: str
    id: str
    line: int
    level: int = 0

    @property
    def stable(self):
        # Заголовок без латиницы получает номер по порядку и сдвигается.
        return slugify(self.text) != ""


@dataclass
class Page:
    path: Path
    lines: list = field(default_factory=list)
    headings: list = field(default_factory=list)

    @property
    def rel(self):
        return self.path.relative_to(ROOT).with_suffix("").as_posix()

    @property
    def url(self):
        # Как в рабочих ссылках: каждое слово с заглавной, пробелы как %20.
        parts = [" ".join(w[:1].upper() + w[1:] for w in p.split(" "))
                 for p in self.rel.split("/")]
        return "/" + "/".join(parts).replace(" ", "%20")

    @property
    def ids(self):
        return {h.id: h for h in self.headings}


def load_page(path):
    with open(path, encoding="utf-8", newline="") as f:
        lines = f.read().splitlines(keepends=True)
    page = Page(path, lines)
    seen = {}
    fenced = False
    for n, line in enumerate(lines, 1):
        if FENCE_RE.match(line):
            fenced = not fenced
            continue
        m = not fenced and HEADING_RE.match(line.rstrip("\r\n"))
        if not m:
            continue
        slug = slugify(m.group(2))
        if slug in seen:
            seen[slug] += 1
            hid = f"{slug}-{seen[slug]}"
        else:
            seen[slug] = 0
            hid = slug
        page.headings.append(Heading(m.group(2), hid, n, len(m.group(1))))
    return page


def load_wiki():
    pages = {}
    for path in sorted(ROOT.rglob("*.md")):
        if SKIP_DIRS & set(path.relative_to(ROOT).parts):
            continue
        page = load_page(path)
        pages[page.rel.lower()] = page
    return pages


def resolve(pages, page, target):
    """Разбирает адрес ссылки. Возвращает (страница, якорь) или текст ошибки."""
    path, _, anchor = target.partition("#")
    if not path:
        return page, anchor
    if not path.startswith("/"):
        return "относительный путь — откроется не та страница"
    other = pages.get(unquote(path).strip("/").lower())
    if other is None:
        return "страница не найдена"
    return other, anchor


def check(pages):
    problems = 0
    for page in pages.values():
        fenced = False
        for n, line in enumerate(page.lines, 1):
            if FENCE_RE.match(line):
                fenced = not fenced
            if fenced:
                continue
            for m in LINK_RE.finditer(line):
                text, target = m.groups()
                if not target or re.match(r"^[a-z]+:", target):
                    continue
                res = resolve(pages, page, target)
                if isinstance(res, str):
                    msg = res
                else:
                    other, anchor = res
                    h = other.ids.get(anchor) if anchor else None
                    if anchor and h is None:
                        msg = "якоря нет"
                        hint = find_heading(pages, page, text)
                        if isinstance(hint, tuple):
                            msg += f"; по тексту подходит {link_target(page, *hint)}"
                    elif h is not None and not h.stable:
                        msg = f"якорь на заголовок без латиницы «{h.text}» — сдвинется"
                    else:
                        continue
                problems += 1
                print(f"{page.rel}.md:{n}: [{text}]({target}) — {msg}")
            for m in WIKILINK_RE.finditer(line):
                inner = m.group(1)
                target = inner.split("|", 1)[1] if "|" in inner else inner
                path = target.partition("#")[0].strip("/").lower()
                if path and path not in pages:
                    problems += 1
                    print(f"{page.rel}.md:{n}: [[{inner}]] — страница не найдена")
    print(f"\nпроблем: {problems}")
    return problems


def find_heading(pages, page, text):
    """Ищет карточку для имени: сначала на этой странице, потом в том же разделе.

    Возвращает (страница, заголовок) или текст ошибки.
    """
    want = keys(text)
    if not want:
        return "пустое имя"
    section = page.rel.split("/")[0]
    scopes = [[page], [p for p in pages.values()
                       if p is not page and p.rel.split("/")[0] == section]]
    for scope in scopes:
        found = [(p, h) for p in scope for h in p.headings
                 if h.line > 1 and want & keys(h.text)]
        if len(found) == 1:
            p, h = found[0]
            if not h.stable:
                return f"карточка «{h.text}» без английской части — якорь сдвинется"
            return found[0]
        if found:
            where = ", ".join(f"{p.rel}#{h.id}" for p, h in found)
            return f"несколько карточек: {where}"
    return "карточка не найдена"


def link_target(page, other, heading):
    prefix = "" if other is page else other.url
    return f"{prefix}#{heading.id}"


def split_row(line):
    body = line.rstrip("\r\n")
    eol = line[len(body):]
    cells = re.split(r"(?<!\\)\|", body)
    return cells, eol


def table_rows(page):
    """Строки данных таблиц страницы, сгруппированные по таблицам: [[индекс строки]]."""
    tables, rows = [], None
    for i, line in enumerate(page.lines):
        stripped = line.strip()
        if not stripped.startswith("|"):
            rows = None
        elif TABLE_SEP_RE.match(stripped):
            rows = []
            tables.append(rows)
        elif rows is not None:
            rows.append(i)
    return tables


def name_cell_fix(pages, page, name):
    """Что сделать с ячейкой названия.

    Возвращает (новый текст или None, ошибка или None, есть ли у строки карточка).
    """
    m = LINK_RE.search(name)
    if m:
        res = resolve(pages, page, m.group(2))
        if not isinstance(res, str):
            other, anchor = res
            if not anchor or anchor in other.ids:
                return None, None, True  # ссылка рабочая, не трогаем
        found = find_heading(pages, page, m.group(1))
        if isinstance(found, str):
            return None, f"ссылка сломана, {found}", True
        return name[:m.start(2)] + link_target(page, *found) + name[m.end(2):], None, True
    found = find_heading(pages, page, name)
    if isinstance(found, str):
        return None, found, False
    return f"[{name}]({link_target(page, *found)})", None, True


def tables(pages, write):
    """Ссылки из первого столбца таблиц Арсенала на карточки предметов.

    Таблицы, где ни у одной строки нет карточки (базовое оружие, таблицы
    внутри карточек), пропускаются молча.
    """
    changed = unresolved = 0
    for page in pages.values():
        if not page.rel.startswith(ITEM_SECTION):
            continue
        dirty = False
        for rows in table_rows(page):
            results = []
            for i in rows:
                cells, eol = split_row(page.lines[i])
                name = cells[1].strip() if len(cells) > 2 else ""
                if not re.search(r"[A-Za-zА-Яа-яЁё]", name):
                    continue
                results.append((i, cells, eol, name, *name_cell_fix(pages, page, name)))
            if not any(has_card for *_, has_card in results):
                continue
            for i, cells, eol, name, new, error, _ in results:
                where = f"{page.rel}.md:{i + 1}"
                if error:
                    unresolved += 1
                    print(f"{where}: {name} — {error}")
                elif new:
                    print(f"{where}: {name}  →  {new}")
                    cells[1] = cells[1].replace(name, new, 1)
                    page.lines[i] = "|".join(cells) + eol
                    dirty = True
                    changed += 1
        if dirty and write:
            with open(page.path, "w", encoding="utf-8", newline="") as f:
                f.write("".join(page.lines))
    verb = "изменено" if write else "будет изменено"
    print(f"\n{verb}: {changed}, не удалось: {unresolved}")


# --- Архетипы: ссылки на навыки, таланты и трейты ---------------------------

ARCHETYPE_DIRS = ("i создание персонажа/архетипы/", "iii продвижение/элитные архетипы/")
SKILLS_PAGE = "iii продвижение/навыки"
TALENTS_DIR = "iii продвижение/таланты/"
TRAITS_PAGE = "iii продвижение/трейты"

# Имя в архетипе → имя в заголовке, когда они расходятся.
ALIASES = {
    "navigate": "navigation",
    "interrogation": "interrogate",
    "meditate": "meditation",
    "wrestle": "wrestler",
}
# Имена, которые ведут на целую страницу, а не на заголовок.
PAGE_LINKS = {"bardic art": "v магия/искусства/искусства барда"}

START_SECTIONS = {"стартовые навыки": "skill", "стартовые таланты": "talent"}
REQ_RE = re.compile(r"^\*\*(Трейты|Навыки|Таланты):\*\*[ \t]*")
REQ_KINDS = {"Трейты": "trait", "Навыки": "skill", "Таланты": "talent"}
# Английское имя и, если есть, скобки сразу за ним: «Trade (Chymist)».
ITEM_RE = re.compile(r"(?P<name>[A-Za-z][A-Za-z'’-]*(?: [A-Za-z][A-Za-z'’-]*)*)"
                     r"(?P<arg> ?\((?P<inner>[^()]*)\))?")


def norm(text):
    text = text.replace("’", "'").replace("ё", "е").replace("-", " ")
    text = re.sub(r"\s+", " ", text).strip().lower()
    return ALIASES.get(text, text)


def heading_names(heading):
    """Английская часть заголовка: (целиком, без скобок в конце)."""
    eng = re.sub(r"\s*#\w+$", "", plain(heading.text).split(" / ")[0])
    return norm(eng), norm(re.sub(r"\s*\([^)]*\)$", "", eng))


class Index:
    """Заголовки, на которые ведут ссылки, по английскому имени."""

    def __init__(self, entries):
        self.full, self.base = {}, {}
        for page, h in entries:
            full, base = heading_names(h)
            self.full.setdefault(full, []).append((page, h))
            self.base.setdefault(base, []).append((page, h))

    def find(self, name, inner=None):
        """Возвращает ((страница, заголовок), взяты ли скобки) или текст ошибки.

        Сначала «Имя (скобки)» целиком, потом просто «Имя». Если под
        именем несколько заголовков на одной странице (Heightened Senses,
        Two Weapon Wielder) — первый из них.
        """
        name = norm(name)
        if inner and f"{name} ({norm(inner)})" in self.full:
            return self.full[f"{name} ({norm(inner)})"][0], True
        hits = self.base.get(name) or self.full.get(name)
        if not hits:
            return "заголовок не найден"
        if len({p.rel for p, _ in hits}) > 1:
            return "несколько заголовков: " + ", ".join(f"{p.rel}#{h.id}" for p, h in hits)
        return hits[0], False


def build_indexes(pages):
    skills = pages[SKILLS_PAGE]
    groups, children, group = [], {}, None
    for h in skills.headings:
        if h.level == 4:
            group = h
            groups.append((skills, h))
            children[h.id] = []
        elif h.level == 5 and group:
            children[group.id].append((skills, h))
    talents = [(p, h) for p in pages.values() if p.rel.startswith(TALENTS_DIR)
               and not p.path.name.startswith("_") for h in p.headings if h.level > 1]
    traits = [(pages[TRAITS_PAGE], h) for h in pages[TRAITS_PAGE].headings if h.level == 4]
    return {
        "skill": Index(groups),
        "skill children": {gid: Index(c) for gid, c in children.items() if c},
        "talent": Index(talents),
        "trait": Index(traits),
        "pages": {name: pages[rel] for name, rel in PAGE_LINKS.items()},
    }


def split_top(text, seps):
    """Делит строку по разделителям вне скобок, разделители остаются в списке."""
    parts, depth, start, i = [], 0, 0, 0
    while i < len(text):
        c = text[i]
        depth += (c == "(") - (c == ")")
        sep = depth == 0 and next((s for s in seps if text.startswith(s, i)), None)
        if sep:
            parts += [text[start:i], sep]
            i = start = i + len(sep)
            continue
        i += 1
    return parts + [text[start:]]


def md_link(text, target):
    other, heading = target
    return f"[{text}]({other.url}#{heading.id})"


def link_item(idx, kind, item):
    """Ставит ссылки в один пункт списка. Возвращает (новый текст, [заметки])."""
    if "](" in item or not item.strip():
        return item, []
    m = ITEM_RE.search(item)
    if not m or m.start() > len(item) - len(item.lstrip()):
        return item, []  # «500 XP на заклинания» и прочий текст без имени
    name, arg, inner = m.group("name", "arg", "inner")
    if re.fullmatch(r"[A-Z]{1,3}", name):
        return item, []  # PR 2, XP
    head, tail = item[:m.start()], item[m.end():]
    arg = arg or ""
    if norm(name) in idx["pages"]:
        return f"{head}[{name}]({idx['pages'][norm(name)].url}){arg}{tail}", []

    found = idx[kind].find(name, inner)
    if isinstance(found, str):
        return item, [f"{name}{arg} — {found}"]
    target, took_arg = found
    notes = [] if target[1].stable else [f"{name} — заголовок без латиницы, якорь сдвинется"]
    if took_arg:
        return f"{head}{md_link(name + arg, target)}{tail}", notes

    if kind == "skill" and inner:
        # Специализация навыка: «Common Lore (War)» → заголовок War под Common Lore.
        kids = idx["skill children"].get(target[1].id)
        child = kids and kids.find(inner)
        if child and not isinstance(child, str):
            return f"{head}{md_link(name + arg, child[0])}{tail}", notes
        # Список специализаций в скобках: «Trade (2 из списка: Dancer, Musician)».
        if kids:
            prefix, colon, names = inner.rpartition(":")
            pieces = split_top(names, [", "])
            linked = []
            for piece in pieces:
                hit = kids.find(piece.strip()) if piece.strip() else None
                if hit and not isinstance(hit, str):
                    piece = piece.replace(piece.strip(), md_link(piece.strip(), hit[0]))
                elif colon and re.fullmatch(r"[A-Za-z][A-Za-z '’-]*", piece.strip()):
                    notes.append(f"{name} ({piece.strip()}) — специализации нет")
                linked.append(piece)
            new_inner = prefix + colon + "".join(linked)
            if new_inner != inner:
                arg = arg.replace(f"({inner})", f"({new_inner})")
            elif re.fullmatch(r"[A-Za-z][A-Za-z '’-]*", inner):
                notes.append(f"{name} ({inner}) — специализации нет, ссылка на группу")
    return f"{head}{md_link(name, target)}{arg}{tail}", notes


def archetype_lines(page):
    """Строки со списками навыков/талантов/трейтов: [(индекс строки, вид, текст)]."""
    out, kind = [], None
    for i, line in enumerate(page.lines):
        text = line.rstrip("\r\n")
        m = HEADING_RE.match(text)
        if m:
            kind = START_SECTIONS.get(m.group(2).strip().lower())
            continue
        req = REQ_RE.match(text)
        if req:
            out.append((i, REQ_KINDS[req.group(1)], req.end()))
        elif kind and text.strip():
            out.append((i, kind, 0))
    return out


def archetypes(pages, write):
    idx = build_indexes(pages)
    changed = unresolved = 0
    for page in pages.values():
        if not page.rel.startswith(ARCHETYPE_DIRS) or "template" in page.rel:
            continue
        dirty = False
        for i, kind, start in archetype_lines(page):
            line = page.lines[i]
            body = line.rstrip("\r\n")
            content = body.rstrip()
            trail = line[len(content):]
            seps = [" или ", " or "] + ([", "] if start else [])
            parts = split_top(content[start:], seps)
            new_parts = []
            for n, part in enumerate(parts):
                if n % 2:  # разделитель
                    new_parts.append(part)
                    continue
                new, notes = link_item(idx, kind, part)
                new_parts.append(new)
                for note in notes:
                    unresolved += 1
                    print(f"{page.rel}.md:{i + 1}: {note}")
            new_content = content[:start] + "".join(new_parts)
            if new_content != content:
                print(f"{page.rel}.md:{i + 1}: {new_content}")
                page.lines[i] = new_content + trail
                dirty = True
                changed += 1
        if dirty and write:
            with open(page.path, "w", encoding="utf-8", newline="") as f:
                f.write("".join(page.lines))
    verb = "изменено строк" if write else "будет изменено строк"
    print(f"\n{verb}: {changed}, замечаний: {unresolved}")


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    args = sys.argv[1:]
    if not args or args[0] not in {"check", "tables", "archetypes"}:
        print(__doc__)
        return 2
    pages = load_wiki()
    if args[0] == "check":
        return 1 if check(pages) else 0
    if args[0] == "archetypes":
        archetypes(pages, write="--write" in args)
        return 0
    tables(pages, write="--write" in args)
    return 0


if __name__ == "__main__":
    sys.exit(main())
