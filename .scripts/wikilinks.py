"""Ссылки на заголовки вики (An Otter Wiki v2.25).

    python .scripts/wikilinks.py check          проверить все ссылки
    python .scripts/wikilinks.py tables         показать, что поменяется в таблицах
    python .scripts/wikilinks.py tables --write записать изменения

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
SKIP_DIRS = {".git", ".scripts", "_docs"}
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
        page.headings.append(Heading(m.group(2), hid, n))
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


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    args = sys.argv[1:]
    if not args or args[0] not in {"check", "tables"}:
        print(__doc__)
        return 2
    pages = load_wiki()
    if args[0] == "check":
        return 1 if check(pages) else 0
    tables(pages, write="--write" in args)
    return 0


if __name__ == "__main__":
    sys.exit(main())
