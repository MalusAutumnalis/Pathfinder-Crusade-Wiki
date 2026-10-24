"""Разбор Markdown вики Pathfinder Crusade для выгрузки в gamedata.

Общий для всех доменов (персонаж, арсенал, статусы). Контракт формата —
`_prd/pathfinder_gamedata/wiki_plan.md` чарника, коротко:

- запись — заголовок `#### English / Русское`, пометки `#New`, `#Changed`,
  `#Review` в конце заголовка срезаются в `Title.tags`;
- поля — строки `**Метка:** значение` (несколько меток в строке можно
  разделять `,` или `|`);
- заголовки выше записи (`#`, `##`, `###`) — группировка, `Entry.groups`;
- таблицы — Markdown (`| a | b |`) или блок `{{datatable … }}`.

Модуль только читает: что делать с записью и что считать ошибкой, решает
домен. Проблемы разбора (заголовок без пары имён и т.п.) он возвращает
списком строк, домен кладёт их в отчёт.
"""

import re
import unicodedata
from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import unquote

ROOT = Path(__file__).resolve().parents[2]

KNOWN_TAGS = ("New", "Changed", "Review")

HEADING_RE = re.compile(r"^(#{1,6})[ \t]+(.*?)[ \t]*$")
FENCE_RE = re.compile(r"^[ \t]*(```|~~~)")
CYRILLIC_RE = re.compile(r"[А-Яа-яЁё]")
# Пометка в конце заголовка: «#New», «# TO DO».
TAG_TAIL_RE = re.compile(r"\s+#\s*([A-Za-zА-Яа-яЁё][\w .]*?)\s*$")
LABEL_RE = re.compile(r"\*\*([^*\n]+?):\*\*")
LINK_RE = re.compile(r"(?<!!)\[([^\]]*)\]\(([^)\s]*)(?:\s+\"[^\"]*\")?\)")
IMAGE_RE = re.compile(r"!\[[^\]]*\]\([^)]*\)")
WIKILINK_RE = re.compile(r"\[\[([^\]|]+)(?:\|([^\]]+))?\]\]")
HTML_TAG_RE = re.compile(r"</?(?:span|div|p|b|i|u|s|em|strong|small|sup|sub|font|center)\b[^>]*>", re.I)
BR_RE = re.compile(r"<br\s*/?>", re.I)
TABLE_SEP_RE = re.compile(r"^\|?\s*:?-{3,}:?\s*(\|\s*:?-{3,}:?\s*)*\|?\s*$")


# ─── Файлы и заголовки ──────────────────────────────────────────────────────


def rel(path):
    """Путь файла относительно корня вики, с прямыми слешами."""
    return Path(path).resolve().relative_to(ROOT).as_posix()


def is_template(path):
    return Path(path).stem.lower().endswith("template")


def md_files(*globs, root=ROOT):
    """Файлы вики по шаблонам `glob` от корня, без шаблонов `* template.md`, по порядку имён."""
    out = []
    for g in globs:
        out.extend(p for p in Path(root).glob(g) if p.is_file() and p.suffix == ".md" and not is_template(p))
    return sorted(set(out), key=lambda p: p.as_posix())


@dataclass
class Heading:
    level: int
    text: str  # как в файле, без `#`
    line: int  # номер строки, с 1


@dataclass
class Document:
    path: str  # относительно корня вики
    lines: list  # строки файла без `\n`
    headings: list  # Heading по порядку

    def section_end(self, i):
        """Строка (с 1), до которой (не включая) тянется заголовок i вместе с подзаголовками."""
        level = self.headings[i].level
        for h in self.headings[i + 1:]:
            if h.level <= level:
                return h.line
        return len(self.lines) + 1

    def own_end(self, i):
        """Строка, до которой тянется собственный текст заголовка i (до любого следующего заголовка)."""
        if i + 1 < len(self.headings):
            return self.headings[i + 1].line
        return len(self.lines) + 1

    def numbered(self, start, end):
        """Строки [start, end) как пары (номер, текст)."""
        return [(n, self.lines[n - 1]) for n in range(start, min(end, len(self.lines) + 1))]

    def groups(self, i):
        """Заголовки над заголовком i: {уровень: текст без пометок}."""
        out = {}
        level = self.headings[i].level
        for h in reversed(self.headings[:i]):
            if h.level < level and h.level not in out:
                out[h.level] = parse_title(h.text).text
                level = h.level
        return dict(sorted(out.items()))

    def anchors(self):
        """{id заголовка в движке вики: номер заголовка}, как `.scripts/wikilinks.py`."""
        out, seen = {}, {}
        for i, h in enumerate(self.headings):
            slug = slugify(h.text)
            if slug in seen:
                seen[slug] += 1
                out[f"{slug}-{seen[slug]}"] = i
            else:
                seen[slug] = 0
                out[slug] = i
        return out

    @property
    def key(self):
        """Путь страницы, как его пишут ссылки: без `.md`, в нижнем регистре."""
        return re.sub(r"\.md$", "", self.path).lower()


def parse_document(text, path=""):
    lines = text.replace("\r\n", "\n").replace("\r", "\n").lstrip("\ufeff").split("\n")
    headings = []
    fence = False
    for n, line in enumerate(lines, 1):
        if FENCE_RE.match(line):
            fence = not fence
            continue
        if fence:
            continue
        m = HEADING_RE.match(line)
        if m:
            headings.append(Heading(len(m.group(1)), m.group(2), n))
    return Document(path, lines, headings)


def read_document(path):
    p = Path(path).resolve()
    try:
        name = rel(p)
    except ValueError:
        name = p.as_posix()
    return parse_document(p.read_text(encoding="utf-8"), name)


# ─── Заголовок записи ───────────────────────────────────────────────────────


@dataclass
class Title:
    text: str  # без пометок
    en: str
    ru: str
    tags: list = field(default_factory=list)  # известные пометки: New, Changed, Review
    problems: list = field(default_factory=list)  # строки для отчёта


def parse_title(raw):
    """`Bite (X) / Укус #New` → Title(en='Bite (X)', ru='Укус', tags=['New'])."""
    text = plain_inline(raw).strip()
    tags, problems = [], []
    while True:
        m = TAG_TAIL_RE.search(text)
        if not m:
            break
        tag = m.group(1).strip()
        known = next((t for t in KNOWN_TAGS if t.lower() == tag.lower()), None)
        if known:
            tags.insert(0, known)
        else:
            problems.append(f"пометка «#{tag}» вместо #New/#Changed/#Review")
            tags.insert(0, "Review")
        text = text[: m.start()].rstrip()
    if "#" in text:
        problems.append(f"«#» внутри заголовка «{text}»")

    en, ru = split_names(text, problems)
    return Title(text, en, ru, tags, problems)


def split_names(text, problems):
    parts = re.split(r"\s+/\s+", text)
    if len(parts) == 2:
        en, ru = parts
    elif len(parts) > 2:
        # «A / B / Русское»: русская часть — последняя.
        en, ru = " / ".join(parts[:-1]), parts[-1]
        problems.append(f"несколько « / » в заголовке «{text}»")
    else:
        # «Leaf/ Лист»: разделитель без пробелов, справа кириллица.
        m = re.match(r"^(.*?[^\s/])\s*/\s*([А-Яа-яЁё].*)$", text)
        if m and not CYRILLIC_RE.search(m.group(1)):
            en, ru = m.group(1), m.group(2)
            problems.append(f"разделитель имён без пробелов: «{text}» (нужно « / »)")
        elif CYRILLIC_RE.search(text):
            en, ru = "", text
        else:
            en, ru = text, ""
    en, ru = en.strip(), ru.strip()
    # «Battle Cant (<Организация>)»: подстановка в угловых скобках — не имя.
    if en and CYRILLIC_RE.search(re.sub(r"<[^>]*>", "", en)):
        problems.append(f"кириллица в английском имени «{en}»")
    return en, ru


# ─── Записи ─────────────────────────────────────────────────────────────────


@dataclass
class Entry:
    doc: Document
    index: int  # номер заголовка в doc.headings
    title: Title
    groups: dict  # {уровень: текст} заголовков выше

    @property
    def path(self):
        return self.doc.path

    @property
    def line(self):
        return self.doc.headings[self.index].line

    @property
    def level(self):
        return self.doc.headings[self.index].level

    @property
    def name(self):
        """Английское имя, а без него — русское (для ключей и отчёта)."""
        return self.title.en or self.title.ru

    @property
    def where(self):
        return f"{self.path}:{self.line}"

    def body(self):
        """Строки записи до следующего заголовка того же или старшего уровня, с подзаголовками."""
        return self.doc.numbered(self.line + 1, self.doc.section_end(self.index))

    def own_body(self):
        """Строки записи до любого следующего заголовка."""
        return self.doc.numbered(self.line + 1, self.doc.own_end(self.index))

    def children(self, level=None):
        """Подзаголовки записи как записи (по умолчанию — ближайшего уровня)."""
        end = self.doc.section_end(self.index)
        subs = [i for i in range(self.index + 1, len(self.doc.headings)) if self.doc.headings[i].line < end]
        if not subs:
            return []
        level = level or min(self.doc.headings[i].level for i in subs)
        return [make_entry(self.doc, i) for i in subs if self.doc.headings[i].level == level]


def make_entry(doc, i):
    return Entry(doc, i, parse_title(doc.headings[i].text), doc.groups(i))


def entries(doc, level=4, within=None):
    """Записи уровня level. within — фильтр по группам: функция groups → bool."""
    out = []
    for i, h in enumerate(doc.headings):
        if h.level != level:
            continue
        e = make_entry(doc, i)
        if within is None or within(e.groups):
            out.append(e)
    return out


def sections(doc, level):
    """Заголовки уровня level как записи (для `## Трейты` и т.п.)."""
    return [make_entry(doc, i) for i, h in enumerate(doc.headings) if h.level == level]


# ─── Поля ───────────────────────────────────────────────────────────────────


@dataclass
class Field:
    label: str
    value: str  # сырой Markdown значения, без хвостовых `,`/`|`
    line: int


def line_fields(text, line=0):
    """Поля строки `**A:** 1, **B:** x | **C:** y`, если строка начинается с метки; иначе []."""
    s = text.strip()
    if not LABEL_RE.match(s):
        return []
    marks = list(LABEL_RE.finditer(s))
    out = []
    for k, m in enumerate(marks):
        end = marks[k + 1].start() if k + 1 < len(marks) else len(s)
        value = s[m.end():end].strip()
        value = re.sub(r"[\s,|]+$", "", value)
        out.append(Field(m.group(1).strip(), value, line))
    return out


def split_fields(lines, open_labels=(), known=None):
    """Блок полей в начале записи и остаток.

    lines — пары (номер, текст). Блок — подряд идущие строки с метками в
    начале (пустые строки между ними пропускаются). Метка из open_labels
    (например «Эффект») заканчивает блок: её значение продолжается текстом
    ниже, и он попадает в остаток. known — метки блока: строка, которая
    начинается с другой метки («**Пассивно:**»), — уже текст записи.

    Возвращает (поля, остаток строк).
    """
    fields = []
    k = 0
    while k < len(lines):
        n, text = lines[k]
        if not text.strip():
            k += 1
            continue
        fs = line_fields(text, n)
        if not fs or (known is not None and fs[0].label not in known):
            break
        fields.extend(fs)
        k += 1
        if any(f.label in open_labels for f in fs):
            break
    return fields, lines[k:]


def field_map(fields):
    """{метка: первое поле}; повторы метки — во втором значении."""
    out, repeated = {}, []
    for f in fields:
        if f.label in out:
            repeated.append(f)
        else:
            out[f.label] = f
    return out, repeated


# ─── Текст ──────────────────────────────────────────────────────────────────


def unescape(text):
    """Markdown-экранирование `\\*`, `\\|`, `\\–` → символ."""
    return re.sub(r"\\([^\w\s])", r"\1", text)


def plain_inline(text):
    """Строка без разметки: ссылки → текст, без `**`/`__`, HTML-тегов и экранирования."""
    text = IMAGE_RE.sub("", text)
    text = LINK_RE.sub(r"\1", text)
    text = WIKILINK_RE.sub(lambda m: m.group(2) or m.group(1), text)
    text = BR_RE.sub("\n", text)
    text = HTML_TAG_RE.sub("", text)
    text = text.replace("**", "").replace("__", "")
    return unescape(text)


def plain_text(lines):
    """Абзацы записи как простой текст: строки через `\\n`, абзацы через пустую строку.

    lines — пары (номер, текст) или строки. Заголовки внутри становятся
    строками текста, разметка ссылок и выделения снимается.
    """
    out = []
    for item in lines:
        text = item[1] if isinstance(item, tuple) else item
        m = HEADING_RE.match(text)
        if m:
            text = m.group(2)
        out.append(plain_inline(text).rstrip())
    s = "\n".join(out)
    s = re.sub(r"[ \t]+\n", "\n", s)
    s = re.sub(r"\n{3,}", "\n\n", s)
    return s.strip()


def has_cyrillic(text):
    return bool(CYRILLIC_RE.search(text))


# ─── Ссылки ─────────────────────────────────────────────────────────────────


def slugify(text):
    """id заголовка в An Otter Wiki: «Steel / Сталь» → `steel-` (кириллица пропадает)."""
    s = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode()
    s = s.strip().lower()
    s = re.sub(r"[^\w\s-]", "", s)
    return re.sub(r"[-\s]+", "-", s)


def link_target(doc, target):
    """Адрес ссылки со страницы doc → (ключ страницы, якорь); `#a` — та же страница."""
    path, _, anchor = target.partition("#")
    if not path:
        return doc.key, anchor
    return unquote(path).strip("/").lower(), anchor


# ─── Таблицы ────────────────────────────────────────────────────────────────


@dataclass
class Table:
    header: list  # заголовки колонок, простым текстом
    rows: list  # строки: списки ячеек (сырой Markdown)
    line: int  # строка шапки
    end: int  # строка после таблицы (или после `}}` блока datatable)
    options: dict = field(default_factory=dict)  # `|paging=false` блока datatable
    row_lines: list = field(default_factory=list)  # номера строк rows

    def dicts(self):
        """Строки как словари {шапка: ячейка}; лишние ячейки отбрасываются, недостающие — ""."""
        return [{h: (row[k] if k < len(row) else "") for k, h in enumerate(self.header)} for row in self.rows]

    def column(self, *names):
        """Индекс первой колонки, чья шапка (без пробелов, регистр не важен) есть в names, или None."""
        want = {n.lower() for n in names}
        for k, h in enumerate(self.header):
            if h.strip().lower() in want:
                return k
        return None


def split_row(text):
    """`| a | b\\|c |` → ['a', 'b\\|c'] (экранированный `|` остаётся в ячейке)."""
    s = text.strip()
    if s.startswith("|"):
        s = s[1:]
    if s.endswith("|") and not s.endswith("\\|"):
        s = s[:-1]
    cells = re.split(r"(?<!\\)\|", s)
    return [c.strip() for c in cells]


def split_br(cell):
    """Профили ячейки, разделённые `<br>`."""
    return [p.strip() for p in BR_RE.split(cell)]


def cell_link(cell):
    """`[Имя / Name](#anchor)` → ('Имя / Name', '#anchor'); без ссылки → (текст, '')."""
    m = LINK_RE.search(cell)
    if m:
        return plain_inline(m.group(1)).strip(), m.group(2)
    return plain_inline(cell).strip(), ""


def tables(lines):
    """Таблицы в строках (пары (номер, текст)): Markdown и `{{datatable … }}`."""
    out = []
    k = 0
    while k < len(lines):
        n, text = lines[k]
        s = text.strip()
        options = {}
        if s.lower().startswith("{{datatable"):
            k += 1
            while k < len(lines) and re.match(r"^\s*\|\s*\w+\s*=", lines[k][1]):
                key, _, value = lines[k][1].strip()[1:].partition("=")
                options[key.strip()] = value.strip()
                k += 1
            if k >= len(lines):
                break
            n, text = lines[k]
            s = text.strip()
        if (s.startswith("|") and k + 1 < len(lines) and TABLE_SEP_RE.match(lines[k + 1][1].strip())):
            header = [plain_inline(c).strip() for c in split_row(s)]
            rows, row_lines = [], []
            k += 2
            while k < len(lines) and lines[k][1].strip().startswith("|"):
                rows.append(split_row(lines[k][1]))
                row_lines.append(lines[k][0])
                k += 1
            if options or (k < len(lines) and lines[k][1].strip() == "}}"):
                if k < len(lines) and lines[k][1].strip() == "}}":
                    k += 1
            end = lines[k][0] if k < len(lines) else (lines[-1][0] + 1 if lines else n + 1)
            out.append(Table(header, rows, n, end, options, row_lines))
            continue
        k += 1
    return out


def without_lines(lines, start, end):
    """Строки (пары) без диапазона номеров [start, end)."""
    return [(n, t) for n, t in lines if not (start <= n < end)]
