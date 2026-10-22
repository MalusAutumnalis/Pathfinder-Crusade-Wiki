"""Отчёт генератора: что поправить в вики, сгруппировано по видам проблем."""

from collections import Counter, defaultdict

# Порядок и заголовки разделов отчёта.
KINDS = {
    "format": "Формат записи",
    "label": "Неизвестные или лишние метки",
    "required": "Нет обязательного поля",
    "value": "Значение поля не читается",
    "name": "Имена",
    "duplicate": "Дубли английских имён",
    "test": "Тест магии не на Cs, характеристику или навык PF",
    "arts": "Искусства",
    "link": "Строки таблиц арсенала и ссылки на записи",
    "profile": "Профили оружия и брони (Dmg, RoF, AP, тип, класс)",
    "bc": "Механика BC: нет пары, непохожий текст",
    "review": "Пометка #Review (выгружено как есть)",
    "bc_check": "Механика BC: числа, которых нет в тексте PF (проверить руками)",
    "bc_moved": "Механика BC, перенесённая под другим именем или по заклинанию, таланту, трейту",
}

# Справочные разделы: не проблемы вики.
INFO_KINDS = {"review", "bc_check", "bc_moved"}


class Report:
    def __init__(self):
        self.items = defaultdict(list)  # kind → [(where, message, group)]
        self.tags = Counter()  # (tag) → сколько записей
        self.counts = {}  # файл выгрузки → записей
        self.notes = []

    def add(self, kind, where, message, group=None):
        """Проблема в месте where («файл:строка»).

        group — общая формулировка однотипных проблем: больше GROUP_MIN таких
        в одном файле сворачиваются в одну строку со списком записей.
        """
        if kind not in KINDS:
            raise ValueError(f"unknown report kind {kind}")
        item = (where, message, group)
        if item not in self.items[kind]:
            self.items[kind].append(item)

    def entry(self, kind, e, message, group=None):
        """Проблема записи e (wiki.Entry)."""
        self.add(kind, e.where, f"{e.name}: {message}" if e.name else message, group)

    def title(self, e):
        """Пометки и проблемы заголовка записи."""
        for t in e.title.tags:
            self.tags[t] += 1
        if "Review" in e.title.tags:
            self.add("review", e.where, e.name)
        for p in e.title.problems:
            self.add("format", e.where, p)

    def note(self, message):
        self.notes.append(message)

    def problems(self):
        return sum(len(v) for k, v in self.items.items() if k not in INFO_KINDS)

    def render(self):
        out = ["Pathfinder Crusade → gamedata: отчёт", ""]
        out.append("Выгружено:")
        for f, n in self.counts.items():
            out.append(f"  {f}: {n}")
        if self.tags:
            out.append("Пометки: " + ", ".join(f"#{t} {n}" for t, n in sorted(self.tags.items())))
        out.append(f"Проблем: {self.problems()}, #Review: {len(self.items['review'])}")
        for note in self.notes:
            out.append(f"Примечание: {note}")
        for kind, head in KINDS.items():
            items = self.items.get(kind)
            if not items:
                continue
            out += ["", f"## {head} ({len(items)})"]
            for where, message in _collapse(items):
                out.append(f"- {where} — {message}")
        return "\n".join(out) + "\n"


GROUP_MIN = 3


def _collapse(items):
    """(место, текст) по порядку; группы больше GROUP_MIN в одном файле — одной строкой."""
    groups = defaultdict(list)
    for where, message, group in items:
        if group:
            groups[(where.rpartition(":")[0] or where, group)].append((where, message))
    out, done = [], set()
    for where, message, group in items:
        key = (where.rpartition(":")[0] or where, group)
        if group and len(groups[key]) > GROUP_MIN:
            if key not in done:
                done.add(key)
                names = ", ".join(m.split(":")[0] for _, m in groups[key])
                out.append((key[0], f"{group} — {len(groups[key])} записей: {names}"))
            continue
        out.append((where, message))
    return sorted(out, key=lambda i: _sort_key(i[0]))


def _sort_key(where):
    path, _, line = where.rpartition(":")
    if line.isdigit():
        return (path, int(line))
    return (where, 0)
