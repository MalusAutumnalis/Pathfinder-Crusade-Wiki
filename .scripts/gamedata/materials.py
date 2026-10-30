"""Материалы, камни инкрустации и зачарования предметов (Pathfinder Crusade).

materials.json — материалы из таблицы и записей `8 материалы.md` (entryType —
колонка «Тип») и камни из таблицы «Инкрустация» того же файла (entryType
«Инкрустация»); enchantments.json — зачарования: таблица `7 зачарования.md`
(категория → entryType, «Кратко» → short) и записи `7 зачарования/*.md`
(уровни). Формат записей — `_prd/item_materials/plan.md` чарника.

Механика, которую лист считает сам (conditions, special, weightFactor), — из
таблиц правил ниже: текст вики её не размечает. Правило, которое не нашло своей
записи или уровня, — в отчёт.
"""

import re

import wiki
from character import names

ARSENAL = "iv арсенал"
MATERIALS_FILE = "8 материалы.md"
ENCHANTMENTS_INDEX = "7 зачарования.md"
ENCHANTMENTS_GLOB = "7 зачарования/*.md"

INLAY_TYPE = "Инкрустация"
# В таблице камней только русские имена.
GEMS_EN = {"Кварц": "Quartz", "Оникс": "Onyx", "Рубин": "Ruby", "Изумруд": "Emerald", "Алмаз": "Diamond"}

MATERIAL_STATS = ("Редкость", "Цена", "Банк", "Вес", "Прочность", "Ёмкость", "AP", "Pen")
MATERIAL_TEXTS = ("Применение", "Особое", "Описание")
# Поле записи → колонка таблицы и ключ JSON.
MATERIAL_FIELDS = {
    "Редкость": ("R", "rarity"),
    "Цена": ("Цена", "priceFactor"),
    "Банк": ("Банк", "bankFactor"),
    "Вес": ("Вес", "weightFactor"),
    "Прочность": ("Прочность", "durability"),
    "Ёмкость": ("Ёмкость", "capacityFactor"),
    "AP": ("AP", "ap"),
    "Pen": ("Pen", "pen"),
}

# Записи условий (формы conditions ассетов) по материалу.
# CharacteristicCapBonus — «Cap Bonus»: поднимает Char. Cap характеристики (задача 4 плана).
MATERIAL_CONDITIONS = {
    "Mithral": [{"type": "CharacteristicCapBonus", "name": "A", "value": "20"}],
}

# Поля уровней зачарований по (имя, ёмкость). WeaponBonus — запись Weapon листа
# (weapon_bonus): name — какому оружию, «This item» — оружию, связанному с предметом
# (задача 5); значение «×2» — множитель (тоже задача 5).
ENCHANTMENT_LEVELS = {
    ("Feather", 2): {"weightFactor": 0.5},
    ("Feather", 4): {"weightFactor": 0.25},
    ("Feather", 11): {"weightFactor": 0},
    ("Distance", 3): {"conditions": [{"type": "WeaponBonus", "name": "This item", "field": "rng", "value": "×2"}]},
    ("Hurling", 2): {"conditions": [{"type": "WeaponBonus", "name": "Throwing, Grenade", "field": "rng", "value": "×1.5"}]},
    ("Hurling", 4): {"conditions": [{"type": "WeaponBonus", "name": "Throwing, Grenade", "field": "rng", "value": "×2"}]},
    ("Self-Balancing", 7): {"conditions": [{"type": "WeaponBonus", "name": "This item", "field": "balance", "value": "1"}]},
    ("Controlling", 2): {"conditions": [{"type": "WeaponBonus", "name": "This item", "field": "rngMax", "value": "1"}]},
    ("Controlling", 4): {"conditions": [{"type": "WeaponBonus", "name": "This item", "field": "rngMax", "value": "2"}]},
    ("Agile", 1): {"conditions": [{"type": "CharacteristicCapBonus", "name": "A", "value": "5"}]},
    ("Agile", 3): {"conditions": [{"type": "CharacteristicCapBonus", "name": "A", "value": "10"}]},
    ("Agile", 6): {"conditions": [{"type": "CharacteristicCapBonus", "name": "A", "value": "15"}]},
    ("Blurring", 2): {"conditions": [{"type": "SkillBonus", "name": "Stealth", "value": "10"},
                                     {"type": "SkillBonus", "name": "Dodge", "value": "5"}]},
}

# «Оружие получает свойство Flame (d10), тест A–20.» → Flame (d10).
GRANTS_RE = re.compile(r"получает свойство ([A-Z][\w\- ]*(?:\([^)]*\))?)")
CAPACITY_RE = re.compile(r"^\*\*Ёмкость(?:\s+(\d+))?:\*\*\s*(.*)$")
BARE_HEADING_RE = re.compile(r"^#{1,6}\s*$")
DASHES = {"—", "–", "-", ""}


def path(rel):
    return wiki.ROOT / ARSENAL / rel


def cell(value):
    return wiki.plain_inline(value).strip()


def number(value):
    """«×0.5» → 0.5, «−3» → -3, «+1» → 1, «—» → None; не число → ValueError."""
    s = cell(value).replace("−", "-").replace("–", "-").lstrip("×").replace(",", ".")
    if s in DASHES:
        return None
    n = float(s)
    return int(n) if n.is_integer() else n


# ─── Материалы ──────────────────────────────────────────────────────────────


def _table(doc, first_column):
    """Таблица, чья первая колонка — first_column, или None."""
    for t in wiki.tables(doc.numbered(1, len(doc.lines) + 1)):
        if t.header and t.header[0] == first_column:
            return t
    return None


def _material_fields(e):
    """Поля записи материала: {метка: сырое значение}; текстовые метки тянутся до следующей метки."""
    out, current, extra = {}, None, []
    for n, t in e.own_body():
        fs = wiki.line_fields(t, n)
        if fs:
            current = None
            for f in fs:
                out[f.label] = [f.value] if f.label in MATERIAL_TEXTS else f.value
                if f.label in MATERIAL_TEXTS:
                    current = f.label
                elif f.label not in MATERIAL_STATS:
                    extra.append(f.label)
            continue
        if current is not None:
            out[current].append(t)
    for label in MATERIAL_TEXTS:
        if label in out:
            out[label] = wiki.plain_text(out[label])
    return out, extra


def materials(report, doc=None):
    """Материалы и камни инкрустации: записи для materials.json."""
    doc = doc or wiki.read_document(path(MATERIALS_FILE))
    anchors = doc.anchors()
    table = _table(doc, "Материал")
    if table is None:
        report.add("format", doc.path, "нет таблицы материалов (первая колонка «Материал»)")
        return []

    out = []
    seen = set()
    for row, line in zip(table.dicts(), table.row_lines):
        where = f"{doc.path}:{line}"
        label, target = wiki.cell_link(row["Материал"])
        i = anchors.get(target.lstrip("#")) if target.startswith("#") else None
        if i is None or doc.headings[i].level != 4:
            report.add("link", where, f"материал «{label}»: ссылка «{target}» не ведёт на запись `####`")
            continue
        e = wiki.make_entry(doc, i)
        seen.add(i)
        if not e.title.en or not e.title.ru:
            report.entry("name", e, "нужно `English / Русское`")
        fields, extra = _material_fields(e)
        for lab in extra:
            report.entry("label", e, f"неизвестная метка «{lab}»")

        rec = {**names(e), "entryType": cell(row["Тип"]), "use": fields.get("Применение") or cell(row["Применение"])}
        for label_, (column, key) in MATERIAL_FIELDS.items():
            raw = fields.get(label_, row.get(column, ""))
            try:
                value, from_table = number(raw), number(row.get(column, ""))
            except ValueError:
                report.entry("value", e, f"{label_} «{cell(raw)}» / в таблице «{cell(row.get(column, ''))}» — не число")
                value = from_table = None
            if value != from_table:
                report.entry("value", e, f"{label_}: в записи {cell(raw)}, в таблице {cell(row.get(column, ''))}")
            rec[key] = value
        short = cell(row.get("Особое", ""))
        rec["short"] = "" if short in DASHES else short
        rec["special"] = fields.get("Особое", "")
        rec["description"] = fields.get("Описание", "")
        rec["conditions"] = MATERIAL_CONDITIONS.get(rec["name"], [])
        out.append(rec)

    for e in wiki.entries(doc, 4):
        if e.index not in seen:
            report.entry("link", e, "материала нет в таблице материалов — не выгружен")
    for name in MATERIAL_CONDITIONS:
        if not any(r["name"] == name for r in out):
            report.add("value", doc.path, f"правило условий материала «{name}»: нет такого материала")
    return out + inlays(doc, report)


def inlays(doc, report):
    """Камни таблицы «Инкрустация»: имя, редкость, цена (как в вики, без единицы), бонус Ёмкости."""
    table = _table(doc, "Камень")
    if table is None:
        report.add("format", doc.path, "нет таблицы инкрустации (первая колонка «Камень»)")
        return []
    out = []
    for row, line in zip(table.dicts(), table.row_lines):
        where = f"{doc.path}:{line}"
        ru = cell(row["Камень"])
        en = GEMS_EN.get(ru)
        if en is None:
            report.add("name", where, f"камень «{ru}»: нет английского имени в GEMS_EN (.scripts/gamedata/materials.py)")
            en = ru
        try:
            rarity, price, bonus = number(row["Редкость"]), number(row["Цена"]), number(row["Ёмкость"])
        except ValueError:
            report.add("value", where, f"камень «{ru}»: редкость, цена или Ёмкость — не число")
            continue
        out.append({"name": en, "name_ru": ru, "entryType": INLAY_TYPE,
                    "rarity": rarity, "price": price, "capacityBonus": bonus})
    return out


# ─── Зачарования ────────────────────────────────────────────────────────────


def _index_rows(doc, report):
    """Строки таблицы зачарований: [(имя, ссылка, категория, [ёмкости], кратко, место)]."""
    table = _table(doc, "Зачарование")
    if table is None:
        report.add("format", doc.path, "нет таблицы зачарований (первая колонка «Зачарование»)")
        return []
    out = []
    for row, line in zip(table.dicts(), table.row_lines):
        where = f"{doc.path}:{line}"
        name, target = wiki.cell_link(row["Зачарование"])
        caps = []
        for part in cell(row["Ёмкость"]).split("/"):
            try:
                caps.append(int(part.strip()))
            except ValueError:
                report.add("value", where, f"{name}: Ёмкость «{cell(row['Ёмкость'])}» — не числа через /")
                caps = []
                break
        out.append((name, target, cell(row["Категория"]), caps, cell(row["Кратко"]), where))
    return out


def parse_levels(e, report):
    """Описание, требование и уровни записи зачарования.

    Уровни — строки `**Ёмкость N:** текст` (текст тянется до следующего уровня) или
    одна пара `**Ёмкость:** N` + `**Эффект:** текст`. Строки до первого уровня —
    описание, кроме поля «Требования».
    """
    head, levels, requirement = [], [], ""
    single, effect = None, None
    current = None
    for n, t in e.own_body():
        # `####` без имени — не заголовок для Markdown, но конец записи.
        if BARE_HEADING_RE.match(t):
            report.add("name", f"{e.path}:{n}", f"заголовок `{t.strip()}` без имени — запись не выгружена")
            break
        m = CAPACITY_RE.match(t.strip())
        if m and m.group(1):
            current = {"capacity": int(m.group(1)), "lines": [m.group(2)]}
            levels.append(current)
            continue
        if m:
            try:
                single = int(cell(m.group(2)))
            except ValueError:
                report.entry("value", e, f"Ёмкость «{cell(m.group(2))}» — не число")
            continue
        fs = wiki.line_fields(t, n)
        if fs and fs[0].label in ("Требования", "Требование"):
            requirement = cell(fs[0].value)
            continue
        if fs and fs[0].label == "Эффект":
            effect = [fs[0].value]
            current = None
            continue
        if effect is not None and not levels:
            effect.append(t)
        elif current is not None:
            current["lines"].append(t)
        else:
            head.append(t)

    if single is not None:
        if levels:
            report.entry("format", e, "и «**Ёмкость:** N», и «**Ёмкость N:**» — выгружены уровни")
        else:
            levels = [{"capacity": single, "lines": effect or []}]
            if effect is None:
                report.entry("required", e, "«**Ёмкость:** N» без «**Эффект:**»")
    out = []
    for lv in levels:
        text = wiki.plain_text(lv["lines"])
        m = GRANTS_RE.search(text)
        out.append({"capacity": lv["capacity"], "text": text, "special": m.group(1).strip() if m else ""})
    return wiki.plain_text(head), requirement, out


def enchantments(report, index_doc=None, docs=None):
    """Зачарования: записи для enchantments.json в порядке таблицы `7 зачарования.md`."""
    index_doc = index_doc or wiki.read_document(path(ENCHANTMENTS_INDEX))
    if docs is None:
        docs = [wiki.read_document(p) for p in wiki.md_files(f"{ARSENAL}/{ENCHANTMENTS_GLOB}")]

    by_name = {}
    for d in docs:
        for e in wiki.entries(d, 4):
            if not e.name:
                report.entry("name", e, "запись без имени — не выгружена")
                continue
            if e.name.lower() in by_name:
                report.entry("duplicate", e, f"зачарование «{e.name}» уже есть: {by_name[e.name.lower()].where}")
                continue
            by_name[e.name.lower()] = e

    out, used = [], set()
    for name, target, category, caps, short, where in _index_rows(index_doc, report):
        e = by_name.get(name.lower())
        rec = {"name": name, "entryType": category, "short": short}
        if e is None:
            report.add("link", where, f"{name}: нет записи `#### {name}` в {ENCHANTMENTS_GLOB} — уровни выгружены по таблице, текст — «Кратко»")
            rec["levels"] = [{"capacity": c, "text": short, "special": ""} for c in caps]
        else:
            used.add(name.lower())
            key, anchor = wiki.link_target(index_doc, target)
            if key != e.doc.key or anchor != wiki.slugify(e.doc.headings[e.index].text):
                report.add("link", where, f"{name}: ссылка «{target}» не ведёт на запись (она в {e.where})")
            description, requirement, levels = parse_levels(e, report)
            if requirement:
                rec["requirement"] = requirement
            if description:
                rec["description"] = description
            if [lv["capacity"] for lv in levels] != caps:
                report.entry("value", e, f"Ёмкость уровней {[lv['capacity'] for lv in levels]}, в таблице {caps} — выгружены уровни записи")
            rec["levels"] = levels
        out.append(rec)

    for key, e in by_name.items():
        if key not in used:
            report.entry("link", e, "зачарования нет в таблице `7 зачарования.md` — не выгружено")

    found = {(r["name"], lv["capacity"]): lv for r in out for lv in r["levels"]}
    for key, extra in ENCHANTMENT_LEVELS.items():
        lv = found.get(key)
        if lv is None:
            report.add("value", index_doc.path, f"правило уровня {key[0]} (Ёмкость {key[1]}): нет такого уровня")
            continue
        lv.update(extra)
    return out
