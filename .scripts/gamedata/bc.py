"""Механика из ассетов Black Crusade: `conditions` предметов и условия conditions.json.

Вики механику не хранит: химия PF в основном переименована из BC, статусы и
баффы заклинаний совпадают с BC по английскому имени. Имена PF → BC, где они
разные, — в `bc_names.json` рядом. Пары сверяются по тексту описания, пары с
непохожим текстом и предметы PF без пары в BC идут в отчёт.
"""

import difflib
import json
import re
from pathlib import Path

import wiki

HERE = Path(__file__).resolve().parent
NAMES_FILE = HERE / "bc_names.json"
DEFAULT_ASSETS = wiki.ROOT.parent / "CharacterSheet" / "internal" / "gamedata" / "assets"

# Ниже этой похожести описаний пара PF ↔ BC идёт в отчёт.
SIMILAR = 0.75
# Хвост имени условия BC после имени предмета: « (Post-Effect)», « – Hypex».
SUFFIX_RE = re.compile(r"(\s+–\s+.*|\s+\(.*\))$")


def load_names(path=NAMES_FILE):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


class BC:
    """Ассеты BC (gear.json, conditions.json) и таблица имён PF → BC."""

    def __init__(self, gear, conditions, names):
        self.gear = gear
        self.conditions = conditions
        self.names = names.get("gear", {})
        self.status_names = names.get("status_names", {})
        self.gear_by_name = {g["name"].lower(): g for g in gear}

    @classmethod
    def load(cls, assets=DEFAULT_ASSETS, names_file=NAMES_FILE):
        def read(name):
            with open(Path(assets) / name, encoding="utf-8") as f:
                return json.load(f)

        return cls(read("gear.json"), read("conditions.json"), load_names(names_file))

    def bc_name(self, en):
        return self.names.get(en, en)

    def gear_matches(self, en):
        """Предметы BC для предмета PF: с тем же именем или его варианты «Имя – Вариант»."""
        bc = self.bc_name(en).lower()
        exact = self.gear_by_name.get(bc)
        if exact is not None:
            return [exact]
        return [g for g in self.gear if g["name"].lower().startswith(bc + " – ")]

    def item_conditions(self, en):
        """`conditions` предмета BC для предмета PF (у вариантов — первого)."""
        ms = self.gear_matches(en)
        return [dict(c) for c in ms[0].get("conditions") or []] if ms else []

    def conditions_for(self, base_bc, en, ru):
        """Условия BC предмета base_bc (сам он и «base (Post-Effect)», «base – Hypex») под именами PF."""
        out = []
        b = base_bc.lower()
        for c in self.conditions:
            name = c["name"]
            if name.lower() != b and not (name.lower().startswith(b) and SUFFIX_RE.fullmatch(name[len(b):])):
                continue
            suffix = name[len(b):]
            rec = {"name": en + suffix}
            if ru:
                m = SUFFIX_RE.search(c.get("name_ru") or "")
                rec["name_ru"] = ru + (m.group(1) if m and suffix else "")
            rec["x"] = c.get("x")
            rec["conditions"] = [dict(x) for x in c.get("conditions") or []]
            out.append((rec, name))
        return out


def normalize(text):
    text = text.lower().replace("ё", "е").replace("—", "–").replace("−", "–")
    return re.sub(r"\s+", " ", text).strip()


def similarity(a, b):
    """Похожесть описаний: всего текста или, если выше, строки «Эффект:» (вступление часто переписано)."""
    ratio = lambda x, y: difflib.SequenceMatcher(None, normalize(x), normalize(y)).ratio()
    ea, eb = effect(a), effect(b)
    return max(ratio(a, b), ratio(ea, eb) if ea and eb else 0.0)


def effect(text):
    """Текст «Эффект:» описания до следующей строки с меткой."""
    m = re.search(r"^Эффект:(.*?)(?=^[\w.-]+:|\Z)", text, re.M | re.S)
    return m.group(1).strip() if m else ""


def chemistry(items, bc, report):
    """Сверка химии PF с BC: `conditions` из BC, пары без похожего текста и без пары — в отчёт.

    items — arsenal.Item раздела «Химия». Возвращает [(Item, имя BC)] найденных пар.
    """
    pairs = []
    pf_names = {it.name.lower() for it in items}
    for pf_en in bc.names:
        if pf_en.lower() not in pf_names:
            report.add("bc", bc_names_where(), f"«{pf_en}» → «{bc.names[pf_en]}»: в химии PF нет «{pf_en}»")
    for it in items:
        ms = bc.gear_matches(it.name)
        if not ms:
            if it.name in bc.names:
                report.add("bc", it.where, f"{it.name}: в bc_names.json → «{bc.names[it.name]}», но в BC нет такого предмета")
            else:
                report.add("bc", it.where, f"{it.name}: нет пары в BC — механики нет", group="нет пары в BC")
            continue
        score = max(similarity(it.record["description"], g["description"]) for g in ms)
        if score < SIMILAR:
            report.add("bc", it.where, f"{it.name} ↔ {ms[0]['name']}: описания похожи на {score:.2f} — проверить пару")
        it.record["conditions"] = bc.item_conditions(it.name)
        pairs.append((it, bc.bc_name(it.name)))
    used = {b.lower() for _, b in pairs}
    left = [g["name"] for g in bc.gear
            if g["gearType"] == "consumable"
            and not any(g["name"].lower() == u or g["name"].lower().startswith(u + " – ") for u in used)]
    if left:
        report.note(f"химия BC без пары в PF ({len(left)}): {', '.join(left)}")
    return pairs


def bc_names_where():
    return wiki.rel(NAMES_FILE)
