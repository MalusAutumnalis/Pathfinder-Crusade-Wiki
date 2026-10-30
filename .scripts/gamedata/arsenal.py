"""Домен арсенала: оружие, щиты, броня, снаряжение, протезы и модификации.

Записи для melee.json, ranged.json, gear.json, cybernetics.json,
armour_mods.json и weapon_mods.json в формах ассетов BC
(`internal/gamedata/*.go` чарника). Механика химии из BC — в bc.py.

Предмет — строка таблицы раздела; его описание — запись `####`, на якорь
которой ведёт ссылка в строке (у оружия — запись с тем же именем, если
есть). Несколько строк могут вести на одну общую запись (Hooded и Bullseye
Lantern → Lantern): каждая строка — свой предмет с описанием записи.
Записи, на которые не ведёт ни одна строка, — предметы сами по себе.
"""

import re

import wiki
from character import TRAITS_FILE, names

ARSENAL = "iv арсенал"
MELEE_FILES = ("1 рукопашное оружие/1 базовое.md", "1 рукопашное оружие/2 особое.md")
SHIELDS_FILE = "1 рукопашное оружие/3 щиты.md"
RANGED_FILES = ("2 дальнобойное оружие/1 базовое.md", "2 дальнобойное оружие/2 особое.md")
# Гранаты и бомбы — дальнобойное оружие класса grenade, entryType — раздел `##` таблицы.
GRENADES_FILE = "2 дальнобойное оружие/4 гранаты и бомбы.md"
# Боеприпасы — снаряжение; цены в вики за 10 выстрелов.
AMMO_FILE = "2 дальнобойное оружие/5 боеприпасы.md"
AMMO_UNIT = "10 выстрелов"
# Категория специального боеприпаса → уточнение имени: «Barbed (Arrows) / Зазубренная (стрелы)».
AMMO_CATEGORIES = {"Пули": "Bullets", "Дробь": "Shot", "Стрелы": "Arrows"}
ARMOUR_FILE = "3 броня/1 базовая.md"
ARMOUR_MODS_FILE = "3 броня/2 модификации.md"
WEAPON_MODS_FILES = (
    ("1 рукопашное оружие/4 модификации.md", "Рукопашное"),
    ("2 дальнобойное оружие/3 модификации.md", "Дальнобойное"),
)
CYBERNETICS_GLOB = "8 бионика и кибернетика/*.md"

# Снаряжение: (шаблон файлов, gearType или {группа `##` записи: gearType}).
# Первый подходящий шаблон решает; entryType — заголовок `#` файла.
GEAR_FILES = (
    ("4 экипировка/*.md", "gear"),
    ("5 инструмент/*.md", "tool"),
    ("6 химия/*.md", "consumable"),
    ("9 товары и услуги/01 *.md", "consumable"),
    ("9 товары и услуги/02 *.md", ""),
    ("9 товары и услуги/06 *.md", "tool"),
    ("9 товары и услуги/10 *.md", "tool"),
    ("9 товары и услуги/13 *.md", {"Животные": "mount", "Сбруя": "gear", "Повозки": "mount", "Суда": "mount"}),
    ("9 товары и услуги/*.md", "gear"),
)

# entryType оружия и брони: в BC — вид оружия, в вики — раздел арсенала.
MELEE_TYPE = "Рукопашное оружие"
SHIELD_TYPE = "Щиты"
RANGED_TYPE = "Дальнобойное оружие"
ARMOUR_TYPE = "Броня"

# Метки записей арсенала; остальные — в отчёт.
STAT_LABELS = ("Редкость", "Вес", "Цена")
QUALITY_LABELS = ("Poor.Q", "Comm.Q", "Good.Q", "Best.Q")
CHEMISTRY_LABELS = ("Приём", "Эффект", "Пост-Эффект", "Зависимость")
LABELS = STAT_LABELS + QUALITY_LABELS + CHEMISTRY_LABELS + ("Варианты", "Требование", "Пример")
# Метки, перед которыми описание BC ставит пустую строку.
BLOCK_LABELS = QUALITY_LABELS + ("Приём", "Варианты")

# Тип профиля рукопашного оружия (колонка «Тип») → select листа (MELEE_PROFILES).
MELEE_PROFILES = {
    "кулак": "fist", "кулак.б": "fist.a", "нож": "knife", "когти": "claws", "когти.р": "claws.h", "когти.п": "claws.a",
    "меч": "sword", "рапира": "rapier", "сабля": "saber", "топор": "axe", "крюк": "hook",
    "молот": "hammer", "булава": "mace", "кистень": "flail", "копьё": "spear", "посох": "staff",
    "глефа": "glaive", "кнут": "whip", "штык": "bayonet", "щит": "shield", "укус": "bite",
    "—": "no", "–": "no", "-": "no", "нет": "no",
}
MELEE_GROUPS = {"primary", "primary (shield)", "chain", "shock", "power", "exotic", "mechadendrite"}
SHIELD_SUBTYPES = {
    "баклер": "buckler", "тарг": "targ", "экю": "ecu", "круглый": "round", "каплевидный": "teardrop",
    "лёгкий башенный": "light tower", "башенный": "tower",
}
RANGED_CLASSES = {"pistol", "rifle", "long rifle", "heavy", "throwing", "grenade", "special"}
DAMAGE_TYPES = {"I", "I(Cr)", "R", "X", "X(Fr)", "E", "E(El)", "E(Ls)", "E(Fl)", "C", "C(Tx)"}

# `2×M` — множитель массы заряда (Powder Charge).
DICE = r"(?:\d*d\d+|\d+(?:×M)?|[A-Z]{1,2}\.b)"
DAMAGE_RE = re.compile(rf"^{DICE}(?:[+\-–]{DICE})*$")
ROF_RE = re.compile(r"S|\d+|[–—-]")
EMPTY = {"", "-", "–", "—"}
# Нет значения у гранаты: урона (Smokestick) или магазина и перезарядки (†).
NO_VALUE = EMPTY | {"†"}
# Вес по формуле: M — масса пороха в заряде (Powder Charge).
FORMULA_WEIGHTS = {"M"}


def path(rel):
    return wiki.ROOT / ARSENAL / rel


# ─── Страницы и ссылки ──────────────────────────────────────────────────────


class Page:
    """Страница арсенала: записи `####`, их якоря и таблицы."""

    def __init__(self, doc):
        self.doc = doc
        self.anchors = doc.anchors()
        self.entries = wiki.entries(doc, 4)
        self.tables = wiki.tables(doc.numbered(1, len(doc.lines) + 1))
        self.used = set()  # номера заголовков записей, на которые ведут строки

    def heading(self):
        """Заголовок `#` страницы — раздел, entryType предметов."""
        h = next((h for h in self.doc.headings if h.level == 1), None)
        return wiki.parse_title(h.text).text if h else ""

    def section(self, line, level=2):
        """Заголовок уровня level над строкой line (без пометок) или ""."""
        h = next((h for h in reversed(self.doc.headings) if h.line < line and h.level == level), None)
        return wiki.parse_title(h.text).text if h else ""

    def by_name(self, en):
        """Запись с английским именем en (без учёта регистра) или None."""
        en = en.lower()
        return next((e for e in self.entries if e.title.en.lower() == en), None)


class Index:
    """Страницы арсенала по ключу ссылки (`iv арсенал/6 химия/2 наркотики`)."""

    def __init__(self):
        self.pages = {}

    def page(self, p):
        doc = wiki.read_document(p)
        if doc.key not in self.pages:
            self.pages[doc.key] = Page(doc)
        return self.pages[doc.key]

    def resolve(self, page, target):
        """Запись, на которую ведёт ссылка со страницы page: (Page, Entry) или (None, текст проблемы)."""
        key, anchor = wiki.link_target(page.doc, target)
        other = self.pages.get(key)
        if other is None:
            files = {wiki.rel(q).lower(): q for q in wiki.md_files("**/*.md")}
            if key + ".md" not in files:
                return None, f"ссылка «{target}» — страница не найдена"
            other = self.page(files[key + ".md"])
        i = other.anchors.get(anchor)
        if i is None:
            return None, f"ссылка «{target}» — нет такого заголовка"
        if other.doc.headings[i].level != 4:
            return None, f"ссылка «{target}» ведёт на раздел, а не на запись `####`"
        return other, wiki.make_entry(other.doc, i)


# ─── Значения ───────────────────────────────────────────────────────────────


def cell(value):
    return wiki.plain_inline(value).strip()


def parse_weight(value):
    """«1.5», «+1.5 кг», «2кг» → 1.5; пусто, «-», «по варианту», «+10%» → None."""
    s = cell(value).replace(",", ".")
    m = re.match(r"^\+?(\d+(?:\.\d+)?)\s*(?:кг)?$", s)
    return float(m.group(1)) if m else None


def weight_of(value, where, report, what="вес"):
    """Вес ячейки или поля; не число (кроме пустого и «по варианту») — в отчёт, 0."""
    w = parse_weight(value)
    if w is not None:
        return w
    s = cell(value)
    if s not in EMPTY and s not in FORMULA_WEIGHTS and s != "по варианту":
        report.add("value", where, f"{what} «{s}» — не число, выгружен 0", group=f"{what} не число")
    return 0.0


def entry_description(e, extra=(), body=None):
    """Описание записи как в BC: текст без строки «Редкость | Вес | Цена», поля «Метка: значение».

    extra — строки в начало описания; body — строки вместо тела записи
    (свой вариант из «Варианты:»). Возвращает (поля, текст).
    """
    fields, lines = [], []
    for n, t in (e.body() if body is None else body):
        fs = wiki.line_fields(t, n)
        fields += fs
        if fs and all(f.label in STAT_LABELS for f in fs):
            continue
        if fs and fs[0].label in BLOCK_LABELS and lines and lines[-1][1].strip() and not _after_block(lines):
            lines.append((n, ""))
        lines.append((n, t))
    text = wiki.plain_text(lines)
    return fields, "\n".join([*extra, text] if text else extra)


def _after_block(lines):
    """Уже был блок с меткой из BLOCK_LABELS (пустую строку ставим только перед первым)."""
    return any((fs := wiki.line_fields(t)) and fs[0].label in BLOCK_LABELS for _, t in lines)


# ─── Варианты ───────────────────────────────────────────────────────────────
# Общая запись с несколькими строками таблицы (Сундук малый/средний…) перечисляет их в
# «**Варианты:**» пунктами `- **Малый** (R-3). Текст. **Вес:** 11. **Цена:** 2 gp.`


def variants(e):
    """Пункты «Варианты:» записи: (строки до списка, [(ключ, пара строки)], строки после) или None."""
    body = e.body()
    start = next((k for k, (_, t) in enumerate(body)
                  if (fs := wiki.line_fields(t)) and fs[0].label == "Варианты" and not fs[0].value.strip()), None)
    if start is None:
        return None
    items, k = [], start + 1
    while k < len(body) and (body[k][1].lstrip().startswith("- ") or not body[k][1].strip()):
        t = body[k][1].strip()
        if t:
            items.append((variant_key(t[2:]), body[k]))
        k += 1
    return body[:start], items, body[k:]


def variant_key(text):
    """`**Малый** (R-3). …` → «малый»; без выделения — до первой точки (`R-2. …` → «r-2»)."""
    m = re.match(r"^\*\*([^*]+)\*\*", text)
    return norm_name(m.group(1) if m else text.split(". ")[0])


def norm_name(s):
    return wiki.plain_inline(s).lower().replace("ё", "е").strip(" .:")


def row_keys(r):
    """Как строка таблицы может называться в «Варианты:»: русское имя, без скобок, скобки, английское."""
    out = []
    for name in (r.title.ru, r.title.en):
        m = re.match(r"^(.*?)\s*\(([^()]*)\)\s*$", name)
        out += [name, m.group(1), m.group(2)] if m else [name]
    return [norm_name(x) for x in out if x]


def words(s):
    return set(re.findall(r"[\wё-]+", s))


def match_variant(r, items):
    """Пункт строки r: имя целиком («Квас»), все слова пункта в имени («Пеньковая» — «Пеньковая
    Верёвка», больше слов — лучше), начало («6 сек.» → «6 секунд»). None — не нашёлся."""
    keys = row_keys(r)
    item = next((it for k in keys for it in items if it[0] == k), None)
    if item is None:
        name = words(norm_name(r.title.ru))
        fits = [it for it in items if words(it[0]) <= name and any(len(w) >= 3 for w in words(it[0]))]
        item = max(fits, key=lambda it: len(words(it[0])), default=None)
    return item or next((it for k in keys for it in items if len(k) >= 3 and it[0].startswith(k)), None)


def variant_bodies(rs, report):
    """{id строки: строки описания по её пункту «Варианты:»} для строк, ведущих на общую запись.

    Строка без пары, если она одна такая у записи и пункт без строки тоже один, получает его
    («Склянка» — «Стеклянная»). Остальные без пары — в отчёт, им описание всей записи.
    """
    groups = {}
    for r in rs:
        if r.entry is not None:
            groups.setdefault((r.entry.path, r.entry.index), []).append(r)
    out = {}
    for group in groups.values():
        found = variants(group[0].entry)
        if found is None:
            continue
        before, items, after = found
        pairs = {id(r): match_variant(r, items) for r in group}
        lost = [r for r in group if pairs[id(r)] is None]
        free = [it for it in items if all(it is not p for p in pairs.values())]
        if len(lost) == 1 and len(free) == 1:
            pairs[id(lost[0])], lost = free[0], []
        for r in lost:
            report.add("link", r.where, f"{r.name}: нет своего пункта в «Варианты:» записи {r.entry.where} — описание всей записи",
                       group="строка без своего пункта в «Варианты:»")
        for r in group:
            if pairs[id(r)] is not None:
                n, text = pairs[id(r)][1]
                text = re.sub(r"\s*\*\*(?:Цена|Вес):\*\*[^*]*", "", text.strip()[2:]).strip()
                out[id(r)] = [*before, (n, ""), (n, text), *after]
    return out


def check_labels(e, fields, report, labels=LABELS):
    for f in fields:
        if f.label not in labels:
            report.entry("label", e, f"неизвестная метка «{f.label}»", group="неизвестная метка")


def field_value(fields, label):
    return next((f.value for f in fields if f.label == label), None)


def parse_damage(text, where, report):
    """`1d10–3+S.b R` → ('1d10–3+S.b', 'R'): тип урона — последний токен; «—», «†» — без урона."""
    s = cell(text)
    if s in NO_VALUE:
        return s, ""
    m = re.match(r"^(.*\S)\s+(\S+)$", s)
    if not m:
        report.add("profile", where, f"Dmg «{s}» — нет типа урона")
        return s, ""
    damage, kind = m.group(1), m.group(2)
    if kind not in DAMAGE_TYPES:
        report.add("profile", where, f"тип урона «{kind}» не из списка листа ({', '.join(sorted(DAMAGE_TYPES))})")
    if not DAMAGE_RE.match(damage.replace(" ", "")):
        report.add("profile", where, f"Dmg «{damage}» — не выражение урона")
    return damage, kind


def parse_rof(text, where, report):
    """`S\\–\\–`, `S/2/–` → ('S', '–', '–')."""
    s = cell(text)
    parts = [p.strip() for p in s.split("/")] if "/" in s else ROF_RE.findall(s)
    if len(parts) != 3 or ("/" not in s and "".join(parts) != s.replace(" ", "")):
        report.add("profile", where, f"RoF «{s}» — не три значения S/x/x")
        parts = (parts + ["", "", ""])[:3]
    return [p if p not in ("-", "—") else "–" for p in parts]


def parse_ap(text, where, report):
    """`–/4/4/4` → {head, torso, arms, legs}."""
    s = cell(text)
    parts = [p.strip() for p in s.split("/")]
    if len(parts) != 4 or not all(re.match(r"^(\d+|[–—-])$", p) for p in parts):
        report.add("profile", where, f"AP «{s}» — не четыре значения голова/торс/руки/ноги")
        parts = (parts + ["", "", "", ""])[:4]
    parts = ["–" if p in ("-", "—") else p for p in parts]
    return dict(zip(("head", "torso", "arms", "legs"), parts))


# ─── Строки таблиц ──────────────────────────────────────────────────────────


class Row:
    """Строка таблицы: имя, запись описания и ячейки по шапке."""

    def __init__(self, page, table, k, name_col):
        self.page = page
        self.cells = table.dicts()[k]
        self.line = table.row_lines[k]
        text, self.target = wiki.cell_link(self.cells[name_col])
        self.title = wiki.parse_title(text)
        self.entry = None  # wiki.Entry описания
        self.entry_page = None

    @property
    def where(self):
        return f"{self.page.doc.path}:{self.line}"

    @property
    def name(self):
        return self.title.en or self.title.ru

    def names(self):
        """{name, name_ru}: из строки, русское — из записи, если в строке его нет."""
        en = self.title.en or (self.entry.title.en if self.entry and not self.title.ru else "")
        ru = self.title.ru or (self.entry.title.ru if self.entry and self.entry.title.en.lower() == self.title.en.lower() else "")
        out = {"name": en or ru}
        if en and ru:
            out["name_ru"] = ru
        return out


def rows(page, index, report, link_required=True):
    """Строки всех таблиц страницы с найденными записями описаний."""
    out = []
    for t in page.tables:
        col = t.column("Название", "Модификация", "Боеприпас")
        if col is None:
            report.add("format", f"{page.doc.path}:{t.line}", f"таблица без колонки «Название»: {t.header}")
            continue
        for k in range(len(t.rows)):
            r = Row(page, t, k, t.header[col])
            for p in r.title.problems:
                report.add("format", r.where, p)
            for tag in r.title.tags:
                report.tags[tag] += 1
            if not r.title.en:
                report.add("name", r.where, f"{r.name}: нет английского имени в строке таблицы (нужно `[English / Русское](#якорь)`)")
            if r.target:
                other, e = index.resolve(page, r.target)
                if other is None:
                    report.add("link", r.where, f"{r.name}: {e}")
                else:
                    r.entry_page, r.entry = other, e
                    if other is page:  # строка другой страницы — ссылка, запись там остаётся предметом
                        other.used.add(e.index)
            else:
                e = page.by_name(r.title.en) if r.title.en else None
                if e is not None:
                    r.entry_page, r.entry = page, e
                    page.used.add(e.index)
                    report.add("link", r.where, f"{r.name}: строка без ссылки на запись {e.where}", group="строка без ссылки на запись")
                elif link_required:
                    report.add("link", r.where, f"{r.name}: строка без ссылки и без записи", group="строка без ссылки и без записи")
            out.append(r)
    return out


def row_description(r):
    """Описание строки — текст её записи (поля записи проверяются один раз, в check_entries)."""
    if r.entry is None:
        return ""
    return entry_description(r.entry)[1]


# ─── Оружие ─────────────────────────────────────────────────────────────────


class Weapon:
    """Строка таблицы оружия или щита: записи melee/ranged и gear."""

    def __init__(self, row, record, weight, entry_type):
        self.row, self.record, self.weight, self.entry_type = row, record, weight, entry_type

    @property
    def name(self):
        return self.record["name"]

    @property
    def where(self):
        return self.row.where

    def gear(self):
        return gear_record(self.record, self.weight, self.record["description"], self.entry_type, "weapon")


def gear_record(name_fields, weight, description, entry_type, gear_type, armour=None, conditions=None):
    out = {"name": name_fields["name"]}
    if "name_ru" in name_fields:
        out["name_ru"] = name_fields["name_ru"]
    out.update({
        "weight": weight,
        "armour": armour or {},
        "conditions": conditions or [],
        "description": description,
        "entryType": entry_type,
        "gearType": gear_type,
    })
    return out


def split_profiles(r, columns, report):
    """Колонки с профилями через `<br>`: [{колонка: значение}] по профилям."""
    parts = {c: wiki.split_br(r.cells.get(c, "")) for c in columns}
    n = max(len(v) for v in parts.values())
    for c, v in parts.items():
        if len(v) not in (1, n):
            report.add("profile", r.where, f"{r.name}: в «{c}» {len(v)} профилей через <br>, в других {n}")
    return [{c: (v[k] if k < len(v) else v[-1]) for c, v in parts.items()} for k in range(n)]


def melee_weapon(r, report, shield=False):
    c = r.cells
    group = cell(c.get("Группа", ""))
    if group.lower() not in MELEE_GROUPS:
        report.add("profile", r.where, f"{r.name}: группа «{group}» не из списка листа")
    tabs = []
    for p in split_profiles(r, ("Тип", "Rng", "Dmg", "Pen", "Свойства") if not shield else ("Rng", "Dmg", "Pen", "Свойства"), report):
        damage, kind = parse_damage(p["Dmg"], r.where, report)
        profile = ""
        if not shield:
            raw = cell(p["Тип"])
            profile = MELEE_PROFILES.get(raw.lower(), "")
            if raw.lower() not in MELEE_PROFILES:
                report.add("profile", r.where, f"{r.name}: тип профиля «{raw}» не из списка листа")
        tabs.append({
            "profile": profile,
            "range": cell(p["Rng"]),
            "damage": damage,
            "pen": cell(p["Pen"]),
            "damageType": kind,
            "special": cell(p["Свойства"]),
        })
    shield_rec = {}
    if shield:
        raw = cell(c.get("Подтип", ""))
        subtype = SHIELD_SUBTYPES.get(raw.lower(), "")
        if not subtype:
            report.add("profile", r.where, f"{r.name}: подтип щита «{raw}» не из списка листа")
        ap = cell(c.get("AP", ""))
        if not ap.isdigit():
            report.add("profile", r.where, f"{r.name}: AP щита «{ap}» — не число")
        sectors = cell(c.get("Защита", ""))
        shield_rec = {"subtype": subtype, "ap": int(ap) if ap.isdigit() else 0,
                      "defenseSectors": "" if sectors in EMPTY else sectors}
    return {
        **r.names(),
        "group": group,
        "grip": cell(c.get("Хват", "")),
        "balance": cell(c.get("Bl", "")),
        "upgrades": "",
        "tabs": tabs,
        "shield": shield_rec,
        "description": row_description(r),
    }


def ranged_weapon(r, report):
    c = r.cells
    kinds = wiki.split_br(c.get("Тип", ""))
    cls = cell(kinds[-1]).lower() if len(kinds) > 1 else ""
    if cls not in RANGED_CLASSES:
        report.add("profile", r.where, f"{r.name}: класс «{cell(c.get('Тип', ''))}» — нужно `Вид<br>класс`, класс из {sorted(RANGED_CLASSES)}")
    damage, kind = parse_damage(c.get("Dmg", ""), r.where, report)
    rof = parse_rof(c.get("RoF", ""), r.where, report)
    # † у гранат: магазина и перезарядки нет, как пустые поля гранат BC.
    clip = "" if cell(c.get("Clip", "")) == "†" else cell(c.get("Clip", ""))
    reload = "" if cell(c.get("Rld", "")) == "†" else cell(c.get("Rld", ""))
    return {
        **r.names(),
        "class": cls,
        "range": cell(c.get("Rng", "")),
        "damage": damage,
        "pen": cell(c.get("Pen", "")),
        "damageType": kind,
        "rofSingle": rof[0],
        "rofShort": rof[1],
        "rofLong": rof[2],
        "clipCur": clip,
        "clipMax": clip,
        "reload": reload,
        "special": cell(c.get("Свойства", "")),
        "upgrades": "",
        "description": row_description(r),
    }


def table_weight(r, report):
    if "Wt" not in r.cells:
        return 0.0
    s = cell(r.cells["Wt"])
    if "кг" in s:
        report.add("value", r.where, f"{r.name}: Wt «{s}» с единицей — в таблицах вес без «кг»", group="Wt с единицей")
    return weight_of(r.cells["Wt"], r.where, report, "Wt")


def weapons(index, report):
    """(melee, ranged, щиты): списки Weapon в порядке таблиц."""
    melee, ranged, shields = [], [], []
    for f in MELEE_FILES:
        page = index.page(path(f))
        check_entries(page, report)
        for r in rows(page, index, report, link_required=False):
            rec = melee_weapon(r, report)
            melee.append(Weapon(r, {**rec, "entryType": MELEE_TYPE}, table_weight(r, report), MELEE_TYPE))
    page = index.page(path(SHIELDS_FILE))
    check_entries(page, report)
    for r in rows(page, index, report, link_required=False):
        rec = melee_weapon(r, report, shield=True)
        shields.append(Weapon(r, {**rec, "entryType": SHIELD_TYPE}, table_weight(r, report), SHIELD_TYPE))
    for f in RANGED_FILES:
        page = index.page(path(f))
        check_entries(page, report)
        for r in rows(page, index, report, link_required=False):
            rec = ranged_weapon(r, report)
            ranged.append(Weapon(r, {**rec, "entryType": RANGED_TYPE}, table_weight(r, report), RANGED_TYPE))
    page = index.page(path(GRENADES_FILE))
    check_entries(page, report)
    for r in rows(page, index, report):
        kind = page.section(r.line) or RANGED_TYPE  # «Гранаты», «Бомбы»
        rec = ranged_weapon(r, report)
        ranged.append(Weapon(r, {**rec, "entryType": kind}, table_weight(r, report), kind))
    return melee, ranged, shields


# ─── Естественное оружие ────────────────────────────────────────────────────

# Трейты с таблицей профилей естественного оружия; X рейтинга трейта лист
# добавляет сам (задача 6 `_prd/item_materials/plan.md`), в записи его нет.
NATURAL_WEAPON_TRAITS = ("Natural Weapons (X)", "Deadly Natural Weapons (X)")
NATURAL_WEAPON_TYPE = "Трейт"
NATURAL_WEAPONS_EN = {"Кулаки": "Fists", "Когти": "Claws", "Косы": "Scythes", "Щупальца": "Tentacles",
                      "Рога": "Horns", "Укус": "Bite", "Копыта": "Hooves"}
NATURAL_DAMAGE_RE = re.compile(r"^(\d*d\d+)\+X\s+(\S+)$")


def natural_weapons(report, doc=None):
    """Профили трейтов Natural Weapons и Deadly Natural Weapons — записи melee.json.

    Имя — «Claws (Natural Weapons)» / «Когти (Естественное Оружие)»; поле trait —
    имя трейта в traits.json; урон без +X, Pen 0 (X у Deadly добавляет лист).
    """
    doc = doc or wiki.read_document(wiki.ROOT / TRAITS_FILE)
    by_name = {e.title.en: e for e in wiki.entries(doc, 4)}
    out = []
    for trait in NATURAL_WEAPON_TRAITS:
        e = by_name.get(trait)
        if e is None:
            report.add("required", doc.path, f"нет трейта «{trait}» — естественное оружие не выгружено")
            continue
        body = e.own_body()
        table = next(iter(wiki.tables(body)), None)
        if table is None:
            report.entry("format", e, "нет таблицы профилей естественного оружия")
            continue
        description = wiki.plain_text([(n, t) for n, t in body if n >= table.end])
        en_kind = trait.removesuffix(" (X)")
        ru_kind = e.title.ru
        for row, line in zip(table.dicts(), table.row_lines):
            where = f"{doc.path}:{line}"
            ru = cell(row.get("Оружие", ""))
            en = NATURAL_WEAPONS_EN.get(ru)
            if en is None:
                report.add("name", where, f"{trait}: оружие «{ru}» — нет английского имени в NATURAL_WEAPONS_EN")
                continue
            raw = cell(row.get("Тип", ""))
            if raw.lower() not in MELEE_PROFILES:
                report.add("profile", where, f"{trait}, {ru}: тип профиля «{raw}» не из списка листа")
            m = NATURAL_DAMAGE_RE.match(cell(row.get("Dmg", "")))
            if m is None:
                report.add("profile", where, f"{trait}, {ru}: Dmg «{cell(row.get('Dmg', ''))}» — нужно «1d10+X R»")
                continue
            if m.group(2) not in DAMAGE_TYPES:
                report.add("profile", where, f"{trait}, {ru}: тип урона «{m.group(2)}» не из списка листа")
            pen = cell(row.get("Pen", ""))
            if pen not in ("0", "X"):
                report.add("profile", where, f"{trait}, {ru}: Pen «{pen}» — ждём 0 или X")
            out.append({
                "name": f"{en} ({en_kind})",
                "name_ru": f"{ru} ({ru_kind})",
                "group": "Primary",
                "grip": "",
                "balance": cell(row.get("Bl", "")),
                "upgrades": "",
                "tabs": [{
                    "profile": MELEE_PROFILES.get(raw.lower(), ""),
                    "range": cell(row.get("Rng", "")),
                    "damage": m.group(1),
                    "pen": "0",
                    "damageType": m.group(2),
                    "special": cell(row.get("Свойства", "")),
                }],
                "shield": {},
                "description": description,
                "entryType": NATURAL_WEAPON_TYPE,
                "trait": trait,
            })
    return out


# ─── Броня ──────────────────────────────────────────────────────────────────


class Item:
    """Предмет снаряжения (строка таблицы или запись): запись gear.json и место для отчёта."""

    def __init__(self, record, where, entry=None, row=None):
        self.record, self.where, self.entry, self.row = record, where, entry, row

    @property
    def name(self):
        return self.record["name"]


def armour(index, report):
    page = index.page(path(ARMOUR_FILE))
    out = []
    for r in rows(page, index, report):
        c = r.cells
        cap = cell(c.get("Max.A", ""))
        conditions = []
        if cap not in EMPTY:
            if cap.isdigit():
                conditions.append({"type": "CharacteristicCap", "name": "A", "value": cap})
            else:
                report.add("profile", r.where, f"{r.name}: Max.A «{cap}» — не число")
        rec = gear_record(r.names(), table_weight(r, report), row_description(r), ARMOUR_TYPE, "armour",
                          armour={"ap": parse_ap(c.get("AP", ""), r.where, report),
                                  "special": cell(c.get("Свойства", "")), "upgrades": ""},
                          conditions=conditions)
        out.append(Item(rec, r.where, r.entry, r))
    check_entries(page, report)
    return out


def check_entries(page, report, labels=LABELS, need_ru=False):
    """Имена и метки записей страницы; записи без строки в таблице — в отчёт."""
    for e in page.entries:
        report.title(e)
        if not e.title.en:
            report.entry("name", e, "нет английского имени (нужно `English / Русское`)")
        elif need_ru and not e.title.ru:
            report.entry("name", e, "нет русского имени (нужно `English / Русское`)", group="нет русского имени")
        fields, _ = entry_description(e)
        check_labels(e, fields, report, labels)


# ─── Снаряжение ─────────────────────────────────────────────────────────────


def gear_type_for(rule, e):
    if isinstance(rule, str):
        return rule
    group = e.groups.get(2, "") if e is not None else ""
    return rule.get(group, "gear")


def page_items(page, index, report, gear_type, entry_type):
    """Предметы страницы снаряжения: строки таблиц, потом записи без строк."""
    out = []
    page_rows = rows(page, index, report)
    bodies = variant_bodies(page_rows, report)
    for r in page_rows:
        if r.entry is not None and r.entry_page is not page and r.entry.title.en.lower() == r.title.en.lower():
            continue  # ссылка на предмет другой страницы (Coffee в «Еде» → Наркотики): он выгружен там
        weight = table_weight(r, report) if "Wt" in r.cells else None
        if weight is None and r.entry is not None:
            fields, _ = entry_description(r.entry)
            w = field_value(fields, "Вес")
            weight = weight_of(w, r.entry.where, report) if w is not None else 0.0
        unit = cell(r.cells.get("Единица", ""))
        extra = [f"Единица: {unit}"] if unit else []
        if weight is None or weight == 0.0 and unit:
            weight = parse_weight(unit) or 0.0
        description = (entry_description(r.entry, extra, bodies.get(id(r)))[1] if r.entry is not None
                       else "\n".join(extra))
        rec = gear_record(r.names(), weight or 0.0, description, entry_type, gear_type_for(gear_type, r.entry))
        out.append(Item(rec, r.where, r.entry, r))
    for e in page.entries:
        if e.index in page.used:
            continue
        fields, description = entry_description(e)
        if page.tables and is_group_note(fields):
            if variants(e) is not None:
                report.entry("link", e, "у пунктов «Варианты:» нет строк в таблице раздела — не выгружены")
            continue
        report_unlisted(page, e, report)
        w = field_value(fields, "Вес")
        weight = weight_of(w, e.where, report) if w is not None else 0.0
        out.append(Item(gear_record(names(e), weight, description, entry_type, gear_type_for(gear_type, e)), e.where, e))
    return out


def is_group_note(fields):
    """Запись без строки в таблице и с «Цена: по варианту» — общее описание группы (Drinks), не предмет."""
    price = field_value(fields, "Цена")
    return price is not None and cell(price).lower().startswith("по варианту")


def report_unlisted(page, e, report):
    if page.tables:
        report.entry("link", e, "запись без строки в таблице раздела — выгружена отдельным предметом",
                     group="запись без строки в таблице")


def gear_files():
    """[(путь, правило gearType)] файлов снаряжения по GEAR_FILES."""
    out, seen = [], set()
    for pattern, rule in GEAR_FILES:
        for p in wiki.md_files(f"{ARSENAL}/{pattern}"):
            if p not in seen:
                seen.add(p)
                out.append((p, rule))
    return out


def gear(index, report):
    """Снаряжение разделов 4, 5, 6, 9 и боеприпасы: [Item]."""
    out = []
    for p, rule in gear_files():
        page = index.page(p)
        check_entries(page, report, need_ru=True)
        out += page_items(page, index, report, rule, page.heading())
    return out + ammunition(index, report)


def ammunition(index, report, page=None):
    """Боеприпасы: стандартные (строки без записей) и специальные (`Barbed (Arrows)`).

    Специальный боеприпас называется по категории таблицы: «Rope» стрелы — не верёвка,
    «Ball» дроби — не пуля. page — вместо файла (тесты).
    """
    page = page or index.page(path(AMMO_FILE))
    check_entries(page, report, need_ru=True)
    out = []
    for r in rows(page, index, report, link_required=False):
        c = r.cells
        names_ = r.names()
        extra = [f"{h}: {cell(c[h])}" for h in ("Оружие",) if cell(c.get(h, ""))]
        extra.append(f"Единица: {AMMO_UNIT}")
        cat = cell(c.get("Категория", ""))
        if cat:
            en = AMMO_CATEGORIES.get(cat)
            if en is None:
                report.add("value", r.where, f"{r.name}: категория «{cat}» не из {', '.join(AMMO_CATEGORIES)}")
            else:
                names_["name"] = f"{names_['name']} ({en})"
                if "name_ru" in names_:
                    names_["name_ru"] = f"{names_['name_ru']} ({cat.lower()})"
        description = entry_description(r.entry, extra)[1] if r.entry is not None else "\n".join(extra)
        out.append(Item(gear_record(names_, 0.0, description, page.heading(), "consumable"), r.where, r.entry, r))
    for e in page.entries:
        if e.index not in page.used:
            report_unlisted(page, e, report)
    return out


def cybernetics(index, report):
    out = []
    for p in wiki.md_files(f"{ARSENAL}/{CYBERNETICS_GLOB}"):
        page = index.page(p)
        check_entries(page, report, need_ru=True)
        for it in page_items(page, index, report, "gear", page.heading()):
            rec = {k: v for k, v in it.record.items() if k in ("name", "name_ru")}
            rec.update({"conditions": [], "description": it.record["description"], "entryType": it.record["entryType"]})
            out.append(Item(rec, it.where, it.entry, it.row))
    return out


# ─── Модификации ────────────────────────────────────────────────────────────


def mods(page, index, report, entry_type):
    """Модификации страницы: записи `####` с категорией `##`; таблица — оглавление."""
    rows(page, index, report)  # ссылки оглавления → в отчёт
    check_entries(page, report, need_ru=True)
    out = []
    for e in page.entries:
        if e.index not in page.used:
            report_unlisted(page, e, report)
        fields, _ = entry_description(e)
        raw = field_value(fields, "Вес")
        weight = parse_weight(raw) if raw is not None else None
        extra = []
        if raw is not None and weight is None and cell(raw) not in EMPTY:
            extra.append(f"Вес: {cell(raw)}")  # +20% или ×2 от веса оружия
        _, description = entry_description(e, extra)
        rec = {**names(e), "weight": weight or 0.0, "description": description,
               "entryType": entry_type(e)}
        out.append(Item(rec, e.where, e))
    return out


def armour_mods(index, report):
    page = index.page(path(ARMOUR_MODS_FILE))
    out = mods(page, index, report, lambda e: e.groups.get(2, ""))
    for it in out:
        rec = it.record
        it.record = {**{k: rec[k] for k in ("name", "name_ru") if k in rec}, "weight": rec["weight"],
                     "conditions": [], "description": rec["description"], "entryType": rec["entryType"]}
    return out


def weapon_mods(index, report):
    out = []
    for f, kind in WEAPON_MODS_FILES:
        page = index.page(path(f))
        out += mods(page, index, report, lambda e, kind=kind: f"{kind}: {e.groups.get(2, '')}")
    return disambiguate(out, report)


def disambiguate(items, report):
    """Одноимённые модификации разных разделов (Chain рукопашного и дальнобойного) → «Chain (Рукопашное)»."""
    count = {}
    for it in items:
        count[it.name.lower()] = count.get(it.name.lower(), 0) + 1
    for it in items:
        if count[it.name.lower()] > 1:
            name, kind = it.name, it.record["entryType"].split(":")[0]
            it.record["name"] = f"{name} ({kind})"
            if "name_ru" in it.record:
                it.record["name_ru"] = f"{it.record['name_ru']} ({kind.lower()})"
            report.add("duplicate", it.where, f"модификация «{name}» есть и в другом разделе — выгружена как «{it.record['name']}»")
    return items
