"""Константы Pathfinder Crusade, которых нет в разметке вики, и разбор тестов."""

import re

# Характеристики PF (без Inf, Cor, Fa) в порядке листа.
CHARACTERISTICS = ("WS", "BS", "S", "T", "A", "I", "P", "W", "F")

APTITUDES = CHARACTERISTICS + ("Off", "Fin", "Def", "Mag", "Tec", "Knw", "Soc", "FC", "Gen")

# Склонности характеристик, пока их нет в `характеристики.md` (`**Скл.:**`
# там читается первым): таблица BC, Psy → Mag.
DEFAULT_CHARACTERISTIC_APTITUDES = {
    "WS": "WS, Off",
    "BS": "BS, Fin",
    "S": "S, Off",
    "T": "T, Def",
    "A": "A, Fin",
    "I": "I, Knw",
    "P": "P, FC",
    "W": "W, Mag",
    "F": "F, Soc",
}

# Уровни продвижения как в BC (`EXPERIENCE_LEVELS_BY_TYPE` листа).
SKILL_LEVELS = ("- -> +0", "+0 -> +10", "+10 -> +20", "+20 -> +30")
CHARACTERISTIC_LEVELS = ("+0 -> +5", "+5 -> +10", "+10 -> +15", "+15 -> +20", "+20 -> +25")
TALENT_LEVELS = (1, 2, 3)

# Класс Искусств по файлу списка: англ. для типа `Arts (X)`, рус. для имени.
ARTS_CLASSES = {
    "искусства барда": ("Bard", "Бард"),
    "искусства паладина": ("Paladin", "Паладин"),
    "искусства следопыта": ("Ranger", "Следопыт"),
}

EMPTY_VALUES = {"", "-", "–", "—", "нет"}


def is_empty(value):
    return value.strip().lower() in EMPTY_VALUES


def parse_aptitudes(value):
    """`I, FC` → (['I', 'FC'], [непонятные])."""
    names = [a.strip() for a in re.split(r"[,;]", value) if a.strip()]
    bad = [a for a in names if a not in APTITUDES]
    return names, bad


def test_base(test, skills):
    """С чего начинается тест магии: ('cs'|'characteristic'|'skill', имя) или (None, токен).

    Берётся первая альтернатива (до « или »); skills — английские имена
    навыков PF. `Trade(Bardic)(F)` → навык Trade.
    """
    s = test.strip().replace("−", "-").replace("–", "-")
    s = re.split(r"\s+или\s+", s)[0]
    if re.match(r"^Cs(?![A-Za-z])", s):
        return "cs", "Cs"
    m = re.match(r"^(WS|BS|S|T|A|I|P|W|F)(?![A-Za-z])", s)
    if m:
        return "characteristic", m.group(1)
    for name in sorted(skills, key=len, reverse=True):
        if s.lower().startswith(name.lower()) and not re.match(r"[A-Za-z]", s[len(name):len(name) + 1]):
            return "skill", name
    token = re.match(r"^[^\s(+\-]*", s).group(0) or s[:20]
    return None, token
