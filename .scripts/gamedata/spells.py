"""Заклинания, Искусства и элитные архетипы.

psychic_powers.json — профиль заклинания (ключи BC, `_prd/pathfinder_gamedata/spells.md`),
advancements.json — записи `psychic power`, Искусства как `talent`, `elite archetype`.
"""

import copy
import re

import character
import pf
import wiki

SPELLS_GLOB = "v магия/5 заклинания/**/*.md"
ARTS_GLOB = "v магия/искусства/*.md"
ELITE_GLOB = "iii продвижение/элитные архетипы/*.md"

SPELL_LABELS = ("Стоимость", "Требования", "Действие", "Поддержание", "Тест магии", "Дальность", "Тип", "Эффект")
SPELL_REQUIRED = SPELL_LABELS
ARTS_LABELS = ("Уровень", "Скл.", "Требования", "Тест магии")
ARTS_TEST_ALIASES = ("Навык",)
DAMAGE_TYPE_RE = re.compile(r"^[RIEX](\([A-Za-z]+\))?$")
COST_RE = re.compile(r"^\s*(\d[\d\s]*)\s*XP\s*$", re.I)


def parse_cost(value):
    m = COST_RE.match(value)
    return int(re.sub(r"\s", "", m.group(1))) if m else None


# ─── Профиль атаки ──────────────────────────────────────────────────────────


def attack_profile(e, lines, report):
    """Таблица `Rng | RoF | Dmg | Pen | Свойства` в тексте: (поля профиля, строки без неё)."""
    profile = {k: "" for k in ("weaponRange", "damage", "pen", "damageType", "rofSingle", "rofShort", "rofLong", "special")}
    for t in wiki.tables(lines):
        rng, dmg = t.column("Rng"), t.column("Dmg")
        if rng is None or dmg is None:
            continue
        if not t.rows:
            break
        if t.header != ["Rng", "RoF", "Dmg", "Pen", "Свойства"]:
            report.entry("format", e, f"шапка таблицы атаки «{' | '.join(t.header)}» (нужно Rng | RoF | Dmg | Pen | Свойства)")
        row = t.rows[0]
        cell = lambda k: wiki.plain_inline(row[k]).strip() if k is not None and k < len(row) else ""
        profile["weaponRange"] = cell(rng)
        damage = cell(dmg)
        parts = damage.rsplit(" ", 1)
        if len(parts) == 2 and DAMAGE_TYPE_RE.match(parts[1]):
            profile["damage"], profile["damageType"] = parts
        else:
            profile["damage"] = damage
            if not pf.is_empty(damage):
                report.entry("value", e, f"у урона «{damage}» нет типа последним токеном (R, I, E, X…)")
        profile["pen"] = cell(t.column("Pen"))
        profile["special"] = cell(t.column("Свойства"))
        rof = t.column("RoF")
        if rof is not None:
            # «S\–\–»: разделитель — обратный слеш (или «/»).
            raw = row[rof] if rof < len(row) else ""
            parts = [p.strip() for p in re.split(r"[\\/]", raw)]
            if len(parts) == 3:
                profile["rofSingle"], profile["rofShort"], profile["rofLong"] = parts
            else:
                report.entry("value", e, f"RoF «{raw}» — не три части")
                profile["rofSingle"] = wiki.plain_inline(raw)
        return profile, wiki.without_lines(lines, t.line, t.end)
    return profile, lines


# ─── Заклинания ─────────────────────────────────────────────────────────────


class Spell:
    def __init__(self, e, report, skills, discipline=None, subdiscipline=None):
        self.entry = e
        character.check_names(e, report)
        fields, rest = wiki.split_fields(e.body(), open_labels=("Эффект",))
        fmap, repeated = wiki.field_map(fields)
        for f in repeated:
            report.entry("label", e, f"метка «{f.label}» повторяется")
        for f in fields:
            if f.label not in SPELL_LABELS:
                report.entry("label", e, f"неизвестная метка «{f.label}»")
        for label in SPELL_REQUIRED:
            if label not in fmap:
                report.entry("required", e, f"нет «{label}»")
            elif not fmap[label].value.strip() and not (label == "Эффект" and rest):
                report.entry("required", e, f"пустое «{label}»")
        val = lambda label: wiki.plain_inline(fmap[label].value).strip() if label in fmap else ""

        self.discipline = e.groups.get(1, "") if discipline is None else discipline
        self.subdiscipline = e.groups.get(2, "") if subdiscipline is None else subdiscipline
        self.cost = None
        if "Стоимость" in fmap:
            self.cost = parse_cost(val("Стоимость"))
            if self.cost is None:
                report.entry("value", e, f"«Стоимость: {val('Стоимость')}» — не «N XP»")
        req = val("Требования")
        self.requirements = None if pf.is_empty(req) else req

        profile, rest = attack_profile(e, rest, report)
        effect = val("Эффект")
        tail = wiki.plain_text(rest)
        effect = "\n".join(p for p in (effect, tail) if p)

        self.test = val("Тест магии")
        if self.test:
            check_test(e, self.test, skills, report)

        self.power = {
            **character.names(e),
            "type": self.discipline,
            "subtypes": val("Тип"),
            "range": val("Дальность"),
            "psychotest": self.test,
            "action": val("Действие"),
            "sustained": val("Поддержание"),
            **profile,
            "effect": effect,
        }

    def advancement(self):
        return {
            "type": "psychic power",
            **character.names(self.entry),
            "discipline": self.discipline,
            "subdiscipline": self.subdiscipline,
            "experienceCost": self.cost,
            "requirements": self.requirements,
        }


def check_test(e, test, skills, report):
    kind, token = pf.test_base(test, skills)
    if kind is None:
        report.entry("test", e, f"«{test}» начинается с «{token}»", group=f"тесты начинаются с «{token}»")


def spells(report, skills):
    out = []
    for path in wiki.md_files(SPELLS_GLOB):
        doc = wiki.read_document(path)
        out += [Spell(e, report, skills) for e in wiki.entries(doc, 4)]
    return out


# ─── Искусства ──────────────────────────────────────────────────────────────


class Art:
    """Искусство класса: заклинание с профилем базового и талант."""

    def __init__(self, e, cls, base, report, skills):
        self.entry = e
        self.cls_en, self.cls_ru = cls
        character.check_names(e, report)
        fields, rest = wiki.split_fields(e.body())
        fmap, repeated = wiki.field_map(fields)
        for f in repeated:
            report.entry("label", e, f"метка «{f.label}» повторяется")
        for f in fields:
            if f.label in ARTS_TEST_ALIASES and "Тест магии" not in fmap:
                report.entry("label", e, f"«**{f.label}:**» вместо «**Тест магии:**»")
                fmap["Тест магии"] = f
            elif f.label not in ARTS_LABELS:
                report.entry("label", e, f"неизвестная метка «{f.label}»")
        self.level = character.parse_level(e, fmap.get("Уровень"), report)
        self.aptitudes = character.check_aptitudes(e, fmap.get("Скл."), report)
        req = fmap.get("Требования")
        self.requirements = None if req is None or pf.is_empty(req.value) else wiki.plain_inline(req.value).strip()
        test = fmap.get("Тест магии")
        self.test = wiki.plain_inline(test.value).strip() if test else ""
        if not test:
            report.entry("required", e, "нет «Тест магии»")
        elif self.test:
            check_test(e, self.test, skills, report)
        self.note = wiki.plain_text(rest)

        self.base = base
        ru = e.title.ru or (base.entry.title.ru if base and e.title.en else "")
        self.name = f"{e.title.en or e.title.ru} ({self.cls_en})"
        self.name_ru = f"{ru} ({self.cls_ru})" if e.title.en and ru else ""
        if base is None:
            report.entry("arts", e, "нет базового заклинания с этим английским именем — профиль пустой")
        elif e.title.ru and base.entry.title.ru and norm(e.title.ru) != norm(base.entry.title.ru):
            report.entry("arts", e, f"русское имя «{e.title.ru}», у базового заклинания — «{base.entry.title.ru}»")

    def names(self):
        return {"name": self.name, **({"name_ru": self.name_ru} if self.name_ru else {})}

    def power(self):
        arts_type = f"Arts ({self.cls_en})"
        if self.base:
            p = copy.deepcopy(self.base.power)
            subtypes = ", ".join(s for s in (p["subtypes"], arts_type) if s)
            effect = "\n\n".join(s for s in (self.note, p["effect"]) if s)
        else:
            p = {"type": self.entry.groups.get(2, ""), "range": "", "action": "", "sustained": "",
                 "weaponRange": "", "damage": "", "pen": "", "damageType": "",
                 "rofSingle": "", "rofShort": "", "rofLong": "", "special": ""}
            subtypes, effect = arts_type, self.note
        out = {**self.names(), "type": p["type"], "subtypes": subtypes, "level": self.level}
        for k, v in p.items():
            if k not in ("name", "name_ru", "type", "subtypes", "effect"):
                out[k] = v
        out["psychotest"] = self.test
        out["effect"] = effect
        return out

    def talent(self):
        lines = [f"Даёт Искусство «{self.entry.title.text}» ({self.entry.groups.get(1, '')}).",
                 f"Тест магии: {self.test}" if self.test else ""]
        if self.note:
            lines.append(self.note)
        return {**self.names(), "description": "\n".join(l for l in lines if l)}

    def advancement(self):
        return {
            "type": "talent",
            **self.names(),
            "level": self.level,
            "aptitudes": self.aptitudes,
            "requirements": self.requirements,
        }


def norm(s):
    return s.lower().replace("ё", "е").strip()


def find_base(by_name, e):
    """Базовое заклинание Искусства: то же английское имя, при дублях — та же дисциплина (`##`)."""
    found = by_name.get(e.title.en.lower(), []) if e.title.en else []
    same = [s for s in found if norm(s.discipline) == norm(e.groups.get(2, ""))]
    return (same or found or [None])[0]


def arts(report, spell_list, skills):
    by_name = {}
    for s in spell_list:
        by_name.setdefault(s.entry.title.en.lower(), []).append(s)
    out = []
    for path in wiki.md_files(ARTS_GLOB):
        cls = pf.ARTS_CLASSES.get(path.stem.lower())
        if cls is None:
            report.add("format", wiki.rel(path), "файл Искусств не из списка классов (Bard, Paladin, Ranger)")
            continue
        doc = wiki.read_document(path)
        for e in wiki.entries(doc, 4):
            out.append(Art(e, cls, find_base(by_name, e), report, skills))
    return out


# ─── Элитные архетипы ───────────────────────────────────────────────────────


class EliteArchetype:
    def __init__(self, doc, report, skills):
        self.doc = doc
        tops = wiki.sections(doc, 1)
        self.entry = tops[0] if tops else None
        self.spells, self.talents, self.traits = [], [], []
        self.cost, self.requirements = None, None
        if self.entry is None:
            report.add("format", doc.path, "нет заголовка `# English / Русское`")
            return
        e = self.entry
        character.check_names(e, report)
        name = e.title.text

        req = next((s for s in wiki.sections(doc, 2) if s.title.text == "Требования"), None)
        if req is None:
            report.entry("required", e, "нет раздела «## Требования»")
        else:
            fields, rest = wiki.split_fields(req.own_body())
            parts = []
            for f in fields:
                if f.label == "Стоимость":
                    self.cost = parse_cost(wiki.plain_inline(f.value))
                    if self.cost is None:
                        report.entry("value", e, f"«Стоимость: {f.value}» — не «N XP»")
                elif not pf.is_empty(f.value):
                    parts.append(wiki.plain_inline(f.value).strip())
            self.requirements = ", ".join(parts) or None
            if self.cost is None:
                for n, text in rest:
                    cost = parse_cost(text)
                    if cost is not None:
                        self.cost = cost
                        report.add("format", f"{doc.path}:{n}",
                                   f"{e.name}: стоимость строкой «{text.strip()}» — нужно «**Стоимость:** {cost} XP»")
                        break
            if self.cost is None:
                report.entry("required", e, "нет «Стоимость»")

        for x in wiki.entries(doc, 4):
            groups = set(x.groups.values())
            if "Дополнительные таланты" in groups or "Таланты" in groups:
                self.talents.append(character.parse_talent(x, report))
            elif "Заклинания" in groups:
                self.spells.append(Spell(x, report, skills, discipline=name, subdiscipline=""))
            elif "Трейты" in groups:
                self.traits.append(character.parse_trait(x, report))

    def advancement(self):
        return {
            "type": "elite archetype",
            **character.names(self.entry),
            "experienceCost": self.cost,
            "requirements": self.requirements,
        }


def elite_archetypes(report, skills):
    return [EliteArchetype(wiki.read_document(p), report, skills) for p in wiki.md_files(ELITE_GLOB)]
