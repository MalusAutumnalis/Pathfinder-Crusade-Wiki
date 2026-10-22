"""Условия conditions.json: статусы вики и механика BC.

Записи — в форме BC (`name`, `name_ru`, `x`, `conditions`). Механики в вики
нет, она приходит из BC (bc.py):
- статусы `ii механика/06 раны и урон/1 статусы.md` — по английскому имени
  (пока в вики только русские заголовки `##` — английское из bc_names.json);
- урон характеристик PF (Characteristic Damage (WS) …);
- химия — по таблице имён PF → BC («Coffee» ← «Recaf», «… (Post-Effect)»);
- заклинания, Искусства, таланты и трейты PF с английским именем условия BC
  (Glacial Carapace, Frenzy (Cold Fury)).
"""

import re

import bc as bcmod
import pf
import wiki

STATUSES_FILE = "ii механика/06 раны и урон/1 статусы.md"
CHARACTERISTIC_DAMAGE = "Characteristic Damage"
NUMBER_RE = re.compile(r"\d+")


class Status:
    def __init__(self, e, en, ru):
        self.entry, self.en, self.ru = e, en, ru

    @property
    def where(self):
        return self.entry.where

    def text(self):
        return wiki.plain_text(self.entry.own_body())


def statuses(bc, report, doc=None):
    """Статусы вики: записи `####`, а пока их нет — разделы `##` (и их `#####`)."""
    doc = doc or wiki.read_document(wiki.ROOT / STATUSES_FILE)
    level = 4 if any(h.level == 4 for h in doc.headings) else 2
    found = []
    for e in wiki.sections(doc, level):
        found.append(e)
        found += [c for c in e.children() if c.level > level]
    out = []
    for e in found:
        report.title(e)
        en, ru = e.title.en, e.title.ru
        if not en:
            en = bc.status_names.get(ru, "")
            if en:
                report.entry("name", e, f"нет английского имени — взято «{en}» из bc_names.json "
                                        f"(нужно `#### {en} / {ru}`)", group="статус без английского имени")
            else:
                report.entry("name", e, "нет английского имени и его нет в bc_names.json — выгружен с русским")
        elif not ru:
            report.entry("name", e, "нет русского имени (нужно `English / Русское`)")
        out.append(Status(e, en, ru))
    return out


def record(en, ru, x=None, conditions=()):
    out = {"name": en or ru}
    if en and ru:
        out["name_ru"] = ru
    out["x"] = x
    out["conditions"] = list(conditions)
    return out


def check_numbers(rec, text, source, where, report):
    """Числа механики BC, которых нет в тексте PF, — в отчёт: механику проверить руками."""
    have = set(NUMBER_RE.findall(text))
    missing = []
    for c in rec["conditions"]:
        nums = [n for n in NUMBER_RE.findall(str(c.get("value") or "")) if n != "0"]
        entry = f"{c.get('type')} {c.get('name', '')} {c.get('value')}".replace("  ", " ")
        if any(n not in have for n in nums) and entry not in missing:
            missing.append(entry)
    if missing:
        report.add("bc_check", where, f"{rec['name']} ← {source}: в тексте PF нет {'; '.join(missing)}")


def build(bc, chemistry_pairs, powers, report, status_doc=None):
    """conditions.json. chemistry_pairs — [(arsenal.Item, имя BC)] из bc.chemistry;
    powers — [(имя, русское имя, текст, место)] заклинаний, Искусств, талантов и трейтов PF."""
    out, seen = [], set()

    def add(rec, source, text, where, renamed):
        key = rec["name"].lower()
        if key in seen:
            report.add("duplicate", where, f"условие «{rec['name']}» уже есть")
            return
        seen.add(key)
        out.append(rec)
        if renamed and source.lower() != rec["name"].lower():
            report.add("bc_moved", where, f"{rec['name']} ← {source}")
        elif renamed:
            report.add("bc_moved", where, rec["name"], group="механика BC по тому же имени")
        if text is not None:
            check_numbers(rec, text, source, where, report)

    for s in statuses(bc, report, status_doc):
        moved = bc.conditions_for(s.en, s.en, s.ru) if s.en else []
        if not moved:
            add(record(s.en, s.ru), None, None, s.where, False)
        for rec, source in moved:
            add(rec, source, s.text(), s.where, False)

    damage = {f"{CHARACTERISTIC_DAMAGE} ({c})".lower() for c in pf.CHARACTERISTICS}
    for c in bc.conditions:
        if c["name"].lower() in damage:
            add(record(c["name"], c.get("name_ru", ""), c.get("x"), copy(c)), c["name"], None, "BC conditions.json", False)

    for it, base in chemistry_pairs:
        for rec, source in bc.conditions_for(base, it.name, it.record.get("name_ru", "")):
            add(rec, source, it.record["description"], it.where, source.lower() != rec["name"].lower())

    by_name = {}
    for p in powers:
        by_name.setdefault(p[0].lower(), p)
    for c in bc.conditions:
        name = c["name"]
        if name.lower() in seen:
            continue
        p, suffix = by_name.get(name.lower()), ""
        if p is None:
            base = bcmod.SUFFIX_RE.sub("", name)
            p, suffix = by_name.get(base.lower()), name[len(base):]
        if p is None:
            continue
        en, ru, text, where = p
        m = bcmod.SUFFIX_RE.search(c.get("name_ru") or "")
        rec_ru = ru + (m.group(1) if suffix and m else "") if ru else ""
        add(record(en + suffix, rec_ru, c.get("x"), copy(c)), name, text, where, True)
    return out


def copy(c):
    return [dict(x) for x in c.get("conditions") or []]
