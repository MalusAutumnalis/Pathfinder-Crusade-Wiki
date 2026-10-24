"""Домен персонажа: таланты, трейты, навыки и характеристики.

Записи для talents.json, traits.json и advancements.json (talent, skill,
characteristic). Заклинания, Искусства и элитные архетипы — в spells.py.
"""

import re

import pf
import wiki

TALENTS_GLOB = "iii продвижение/таланты/*.md"
TRAITS_FILE = "iii продвижение/трейты.md"
TRAIT_PAGES = ("i создание персонажа/расы/*.md", "i создание персонажа/архетипы/*.md")
SKILLS_FILE = "iii продвижение/навыки.md"
CHARACTERISTICS_FILE = "iii продвижение/характеристики.md"

OATHS_FILE = "i создание персонажа/архетипы/паладин/клятвы.md"
MONK_PATHS_GLOB = "i создание персонажа/архетипы/монах/*.md"

# «Свершение» — у способностей путей монаха: поступок, без которого способность не открыть.
TALENT_LABELS = ("Уровень", "Скл.", "Требования", "Специализации", "Действие", "Тип", "Свершение")
# Метки, которые идут в начало описания таланта.
TALENT_TEXT_LABELS = ("Свершение", "Специализации", "Действие", "Тип")
SKILL_CHAR_RE = re.compile(r"\s*\((WS|BS|S|T|A|I|P|W|F)\)\s*$")


def names(e):
    """{name, name_ru} записи; без английского имени name — русское (и проблема в отчёте)."""
    out = {"name": e.title.en or e.title.ru}
    if e.title.en and e.title.ru:
        out["name_ru"] = e.title.ru
    return out


def check_names(e, report, need_ru=True):
    """Пометки и имена заголовка в отчёт. Без русского имени можно только трейтам (need_ru=False)."""
    report.title(e)
    if not e.title.en:
        report.entry("name", e, "нет английского имени (нужно `English / Русское`)")
    elif need_ru and not e.title.ru:
        report.entry("name", e, "нет русского имени (нужно `English / Русское`)")


# ─── Таланты ────────────────────────────────────────────────────────────────


class Talent:
    """Разобранный талант: запись talents.json и запись опыта."""

    def __init__(self, e, fields, text, report):
        self.entry = e
        fmap, repeated = wiki.field_map(fields)
        for f in repeated:
            report.entry("label", e, f"метка «{f.label}» повторяется")
        for f in fields:
            if f.label not in TALENT_LABELS:
                report.entry("label", e, f"неизвестная метка «{f.label}»")

        self.level = parse_level(e, fmap.get("Уровень"), report)
        self.aptitudes = check_aptitudes(e, fmap.get("Скл."), report)
        req = fmap.get("Требования")
        self.requirements = None if req is None or pf.is_empty(req.value) else wiki.plain_inline(req.value).strip()

        extra = [f"{f.label}: {wiki.plain_inline(f.value)}" for f in fields if f.label in TALENT_TEXT_LABELS]
        self.description = "\n".join(extra + ([text] if text else []))

    def record(self):
        return {**names(self.entry), "description": self.description}

    def advancement(self):
        return {
            "type": "talent",
            **names(self.entry),
            "level": self.level,
            "aptitudes": self.aptitudes,
            "requirements": self.requirements,
        }

    def advancements(self):
        """Записи опыта: одна, у Power Rating — по записи на каждый PR, до которого его покупают."""
        rec = self.advancement()
        if self.entry.title.en != pf.POWER_RATING:
            return [rec]
        out = []
        for pr in pf.POWER_RATING_LEVELS:
            names = {k: f"{rec[k]} PR {pr}" for k in ("name", "name_ru") if k in rec}
            out.append({**rec, **names, "level": pr})
        return out


def parse_level(e, f, report):
    """Уровень таланта; «—» — талант без уровня (Sound Constitution, Power Rating)."""
    if f is None:
        report.entry("required", e, "нет «Уровень»")
        return None
    if pf.is_empty(f.value):
        return None
    m = re.match(r"^\s*(\d+)\s*(.*)$", f.value)
    if not m:
        report.entry("value", e, f"«Уровень: {f.value}» — не число")
        return None
    rest = m.group(2).strip(" ,|")
    if rest:
        report.entry("value", e, f"лишнее в строке уровня: «{rest}»")
    level = int(m.group(1))
    if level not in pf.TALENT_LEVELS:
        report.entry("value", e, f"уровень {level} вне 1–3")
    return level


def check_aptitudes(e, f, report):
    """Склонности через запятую. Повтор (`Gen, Gen`) — намеренно; «—» или словами
    («Как у Навыка») — склонностей у записи нет, лист их не считает."""
    if f is None:
        report.entry("required", e, "нет «Скл.»")
        return ""
    value = wiki.plain_inline(f.value)
    apts, bad = pf.parse_aptitudes(value)
    good = [a for a in apts if a not in bad]
    if pf.is_empty(value) or (not good and wiki.has_cyrillic(value)):
        return ""
    if bad:
        report.entry("value", e, f"склонность не из списка: «{f.value}»")
    return ", ".join(good)


def parse_talent(e, report):
    check_names(e, report)
    fields, rest = wiki.split_fields(e.body())
    return Talent(e, fields, wiki.plain_text(rest), report)


def talents(report):
    out = []
    for path in wiki.md_files(TALENTS_GLOB):
        doc = wiki.read_document(path)
        out += [parse_talent(e, report) for e in wiki.entries(doc, 4)]
    return out


# ─── Трейты ─────────────────────────────────────────────────────────────────


def parse_trait(e, report):
    check_names(e, report, need_ru=False)
    return {**names(e), "description": wiki.plain_text(e.body())}, e


def traits(report):
    """Трейты из трейты.md и разделов `## Трейты` рас и архетипов: [(запись, wiki.Entry)]."""
    out = []
    doc = wiki.read_document(wiki.ROOT / TRAITS_FILE)
    out += [parse_trait(e, report) for e in wiki.entries(doc, 4)]
    seen = set()
    for path in wiki.md_files(*TRAIT_PAGES):
        doc = wiki.read_document(path)
        for e in wiki.entries(doc, 4, within=lambda g: g.get(2) == "Трейты"):
            # Трейт нескольких рас (Vicious Strikes у орка и полуорка) — одна запись, первая.
            if e.name.lower() not in seen:
                seen.add(e.name.lower())
                out.append(parse_trait(e, report))
    return out


# ─── Клятвы паладина ────────────────────────────────────────────────────────


def oaths(report, doc=None):
    """Клятвы `паладин/клятвы.md` как трейты: [(запись, wiki.Entry)].

    Клятва — раздел `## Oath of X` (кредо, способность, Искусство клятвы),
    её способность — запись `####` в разделе. Обе — трейты: клятву ищут по
    имени клятвы, способность — по своему. doc — вместо файла (тесты).
    """
    doc = doc or wiki.read_document(wiki.ROOT / OATHS_FILE)
    out = []
    for oath in wiki.sections(doc, 2):
        check_names(oath, report, need_ru=False)
        abilities = oath.children(4)
        if not abilities:
            report.entry("required", oath, "нет способности клятвы (`#### English / Русское`)")
        lines, traits = [wiki.plain_text(oath.own_body()), ""], []
        for a in abilities:
            check_names(a, report)
            text = wiki.plain_text(a.body())
            traits.append(({**names(a), "description": f"Способность клятвы {oath.title.text}.\n{text}"}, a))
            lines.append(f"Способность клятвы: {a.title.text}")
            art = next((f for n, t in a.body() for f in wiki.line_fields(t, n) if f.label == "Искусство клятвы"), None)
            if art is not None:
                lines.append(f"Искусство клятвы: {wiki.plain_inline(art.value).strip()}")
        out.append(({**names(oath), "description": "\n".join(lines).strip()}, oath))
        out += traits
    return out


# ─── Пути монаха ────────────────────────────────────────────────────────────


class PathAbility(Talent):
    """Способность пути культивации: покупается как талант; без уровня (черновик) — без записи опыта."""

    def __init__(self, e, path, report):
        check_names(e, report)
        fields, rest = wiki.split_fields(e.body(), known=TALENT_LABELS)
        super().__init__(e, fields, wiki.plain_text(rest), report)
        self.description = f"Способность пути культивации «{path}».\n{self.description}"

    def advancements(self):
        return [] if self.level is None else super().advancements()


def monk_paths(report, docs=None):
    """Пути `монах/*.md` (страницы с `**Характеристика:**`): (способности как таланты, обеты как трейты).

    Способности — записи `####` прямо под `# Путь`; записи в `## Обеты` (Отшельник) — трейты.
    docs — вместо файлов (тесты).
    """
    abilities, vows = [], []
    for doc in docs or map(wiki.read_document, wiki.md_files(MONK_PATHS_GLOB)):
        top = wiki.sections(doc, 1)
        if not top:
            continue
        fields, _ = wiki.split_fields(top[0].own_body())
        if not any(f.label == "Характеристика" for f in fields):
            continue  # общие правила путей, не путь
        name = top[0].title.text
        for e in wiki.entries(doc, 4):
            if e.groups.get(2) == "Обеты":
                vows.append(parse_trait(e, report))
            elif 2 not in e.groups:
                abilities.append(PathAbility(e, name, report))
    return abilities, vows


# ─── Навыки ─────────────────────────────────────────────────────────────────


class Skill:
    def __init__(self, en, ru, aptitudes, e):
        self.en, self.ru, self.aptitudes, self.entry = en, ru, aptitudes, e

    def advancements(self):
        out = []
        for level, step in enumerate(pf.SKILL_LEVELS, 1):
            rec = {"type": "skill", "name": f"{self.en} {step}"}
            if self.ru:
                rec["name_ru"] = f"{self.ru} {step}"
            rec["level"] = level
            rec["aptitudes"] = self.aptitudes
            out.append(rec)
        return out


def skill_names(e):
    ru = SKILL_CHAR_RE.sub("", e.title.ru)
    en = SKILL_CHAR_RE.sub("", e.title.en)
    return en, ru


def skill_aptitudes(e, report):
    fields, _ = wiki.split_fields(e.own_body())
    fmap, _ = wiki.field_map(fields)
    for f in fields:
        if f.label not in ("Скл.", "Действие"):
            report.entry("label", e, f"неизвестная метка «{f.label}»")
    if "Скл." not in fmap:
        return None
    return check_aptitudes(e, fmap["Скл."], report)


def skills(report):
    """Навыки навыки.md: [Skill]; специализация `#####` — «Common Lore (Religion)»."""
    doc = wiki.read_document(wiki.ROOT / SKILLS_FILE)
    out = []
    for e in wiki.entries(doc, 4):
        check_names(e, report)
        en, ru = skill_names(e)
        apts = skill_aptitudes(e, report)
        specs = e.children(5)
        if not specs:
            if apts is None:
                report.entry("required", e, "нет «Скл.»")
            out.append(Skill(en, ru, apts or "", e))
            continue
        for s in specs:
            check_names(s, report)
            sen, sru = skill_names(s)
            own = skill_aptitudes(s, report)
            if own is None and apts is None:
                report.entry("required", s, "нет «Скл.» ни у навыка, ни у специализации")
            out.append(Skill(f"{en} ({sen})", f"{ru} ({sru})" if ru and sru else "", own or apts or "", s))
    return out


def skill_groups(skill_list):
    """Английские имена навыков для проверки тестов: «Common Lore», «Acrobatics»…"""
    out = set()
    for s in skill_list:
        out.add(s.en)
        out.add(re.sub(r"\s*\(.*\)$", "", s.en))
    return out


# ─── Характеристики ─────────────────────────────────────────────────────────


def characteristics(report):
    """Записи опыта characteristic: 9 характеристик PF × 5 уровней."""
    doc = wiki.read_document(wiki.ROOT / CHARACTERISTICS_FILE)
    found = {}
    for i, h in enumerate(doc.headings):
        m = re.match(r"^\((\w+)\)\s*(.*)$", h.text)
        if not m:
            continue
        e = wiki.make_entry(doc, i)
        fields, _ = wiki.split_fields(e.own_body())
        fmap, _ = wiki.field_map(fields)
        title = wiki.parse_title(m.group(2))
        found[m.group(1)] = (title.ru, check_aptitudes(e, fmap["Скл."], report) if "Скл." in fmap else None)

    out = []
    for c in pf.CHARACTERISTICS:
        ru, apts = found.get(c, ("", None))
        if c not in found:
            report.add("required", CHARACTERISTICS_FILE, f"нет заголовка характеристики ({c})")
        elif apts is None:
            report.add("required", CHARACTERISTICS_FILE, f"нет «**Скл.:**» у ({c})")
        for level, step in enumerate(pf.CHARACTERISTIC_LEVELS, 1):
            rec = {"type": "characteristic", "name": f"{c} {step}"}
            if ru:
                rec["name_ru"] = f"{ru} {step}"
            rec["level"] = level
            rec["aptitudes"] = apts or ""
            out.append(rec)
    return out
