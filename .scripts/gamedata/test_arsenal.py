"""Тесты арсенала и механики BC: `cd .scripts/gamedata && python -m unittest`."""

import textwrap
import unittest

import arsenal
import bc as bcmod
import conditions
import wiki
from report import Report


def doc(text, path="iv арсенал/test/1 тест.md"):
    return wiki.parse_document(textwrap.dedent(text).lstrip("\n"), path)


def index(*docs):
    """arsenal.Index со страницами docs (без чтения файлов)."""
    idx = arsenal.Index()
    for d in docs:
        idx.pages[d.key] = arsenal.Page(d)
    return idx, [idx.pages[d.key] for d in docs]


def messages(r, kind):
    return [m for _, m, _ in r.items.get(kind, [])]


class AnchorsTest(unittest.TestCase):
    def test_slugify_drops_cyrillic(self):
        self.assertEqual(wiki.slugify("Backpack / Рюкзак"), "backpack-")
        self.assertEqual(wiki.slugify("Craftsman's Tools / Инструменты"), "craftsmans-tools-")
        self.assertEqual(wiki.slugify("Buckler"), "buckler")

    def test_anchors_number_repeats(self):
        d = doc("""
            # Раздел
            ## Огонь
            #### Lantern / Фонарь
            ## Масло
            #### Lantern / Фонарь
        """)
        a = d.anchors()
        self.assertEqual((a["lantern-"], a["lantern--1"]), (2, 4))
        self.assertEqual((a[""], a["-1"], a["-2"]), (0, 1, 3))

    def test_link_target(self):
        d = doc("x")
        self.assertEqual(wiki.link_target(d, "#coffee-"), ("iv арсенал/test/1 тест", "coffee-"))
        self.assertEqual(wiki.link_target(d, "/Iv%20Арсенал/6%20Химия/2%20Наркотики#coffee-"),
                         ("iv арсенал/6 химия/2 наркотики", "coffee-"))


class ValuesTest(unittest.TestCase):
    def test_damage(self):
        r = Report()
        self.assertEqual(arsenal.parse_damage("1d10–3+S.b R", "a:1", r), ("1d10–3+S.b", "R"))
        self.assertEqual(arsenal.parse_damage("2d10+1 I(Cr)", "a:1", r), ("2d10+1", "I(Cr)"))
        self.assertEqual(r.items, {})
        self.assertEqual(arsenal.parse_damage("1d5–1R R", "a:2", r), ("1d5–1R", "R"))
        self.assertEqual(arsenal.parse_damage("1d10 Q", "a:3", r), ("1d10", "Q"))
        self.assertEqual(len(messages(r, "profile")), 2)

    def test_rof(self):
        r = Report()
        self.assertEqual(arsenal.parse_rof("S\\–\\–", "a:1", r), ["S", "–", "–"])
        self.assertEqual(arsenal.parse_rof("S/2/–", "a:1", r), ["S", "2", "–"])
        self.assertEqual(arsenal.parse_rof("–/3/10", "a:1", r), ["–", "3", "10"])
        self.assertEqual(r.items, {})
        arsenal.parse_rof("S/2", "a:2", r)
        self.assertEqual(len(messages(r, "profile")), 1)

    def test_ap(self):
        r = Report()
        self.assertEqual(arsenal.parse_ap("–/4/4/4", "a:1", r), {"head": "–", "torso": "4", "arms": "4", "legs": "4"})
        self.assertEqual(arsenal.parse_ap("-/3/2/2", "a:1", r)["head"], "–")
        self.assertEqual(r.items, {})
        arsenal.parse_ap("4/4/4", "a:2", r)
        self.assertEqual(len(messages(r, "profile")), 1)

    def test_weight(self):
        self.assertEqual(arsenal.parse_weight("+1.5 кг"), 1.5)
        self.assertEqual(arsenal.parse_weight("2кг"), 2.0)
        self.assertEqual(arsenal.parse_weight("0,5"), 0.5)
        for s in ("—", "-", "по варианту", "+20%", "×2"):
            self.assertIsNone(arsenal.parse_weight(s), s)


WEAPONS = """
    # Базовое оружие
    {{datatable
    |paging=false
    | Название | Группа | Хват | Тип | Rng | Dmg | Pen | Свойства | Bl | Wt | R | Цена |
    | --- | --- | --- | --- | :---: | :---: | :---: | --- | :---: | :---: | :---: | :---: |
    | Warhammer | Primary | 1р [2р, Бл] | Молот<br>Крюк | 3<br>3 | 1d10+2 I(Cr)<br>1d10+1 R | 0<br>0 | Imprecise, Primitive<br>Felling (2), Primitive | -1 | 0.8 | -2 | 12 gp |
    | [Pit Net](#pit-net) | Exotic | 1р | — | 3 | 1d5+1 R | 0 | Flexible, Snare (2) | -1 | 2 | 1 | 20 gp |
    | Bayonet (Rifle) | Primary | 2р [Бл] | Штык<br>Посох<br>Нож | 3-4<br>2-3 | 1d10 R | 0 | Primitive | -1 | – | -3 | 5 gp |
    }}
    #### Pit Net
    Гладиаторская сеть.
"""

SHIELDS = """
    # Щиты
    | Название | Группа | Хват | Подтип | Rng | Dmg | Pen | AP | Защита | Свойства | Wt | R | Цена |
    | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
    | [Kite Shield](#kite-shield) | Primary (Shield) | 1р+П | Каплевидный | 0-2 | 1d5 I(Cr) | 0 | 2 | T+A1+(H)/(L1+L2) | Defensive, Primitive | 4 | -2 | 20 gp |
    | [Buckler](#buckler) | Primary (Shield) | 1р | Баклер | 0-2 | 1d5+1 I(Cr) | 0 | 0 | — | Defensive | 1 | -3 | 9 gp |
    #### Kite Shield
    Пехотный щит.
    #### Buckler
    Маленький щит.
"""

RANGED = """
    # Базовое
    | Название | Тип | Rng | RoF | Dmg | Pen | Clip | Rld | Свойства | Wt | R | Цена |
    | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
    | [Longbow](#longbow) | Bow<br>special | S.b×15м | S\\–\\– | 1d10–1+S.b R | 1 | 1 | ½ | Draw (4-5), Primitive | 3 | -2 | 75 gp |
    | Кремневый Пистолет | Exotic(SP)<br>Pistol | 15м | S/–/– | 1d10+4 I | 6 | 1 | 2 | Inaccurate | 1.5кг | 2 | 500 gp |
    ## Описание оружия
    Общий текст про луки.
    #### Longbow
    Тяжелый боевой лук.
"""


class WeaponsTest(unittest.TestCase):
    def test_melee_profiles(self):
        r = Report()
        idx, [page] = index(doc(WEAPONS))
        hammer, net, bayonet = [arsenal.melee_weapon(row, r) for row in arsenal.rows(page, idx, r, link_required=False)]
        self.assertEqual(hammer["tabs"], [
            {"profile": "hammer", "range": "3", "damage": "1d10+2", "pen": "0", "damageType": "I(Cr)", "special": "Imprecise, Primitive"},
            {"profile": "hook", "range": "3", "damage": "1d10+1", "pen": "0", "damageType": "R", "special": "Felling (2), Primitive"},
        ])
        self.assertEqual((hammer["group"], hammer["grip"], hammer["balance"], hammer["shield"]), ("Primary", "1р [2р, Бл]", "-1", {}))
        self.assertEqual((net["tabs"][0]["profile"], net["description"]), ("no", "Гладиаторская сеть."))
        # 3 типа профиля, 2 дальности, 1 урон: недостающие берут последнее значение, разнобой — в отчёт.
        self.assertEqual([t["profile"] for t in bayonet["tabs"]], ["bayonet", "staff", "knife"])
        self.assertEqual([t["range"] for t in bayonet["tabs"]], ["3-4", "2-3", "2-3"])
        self.assertEqual(messages(r, "profile"), ["Bayonet (Rifle): в «Rng» 2 профилей через <br>, в других 3"])
        self.assertEqual(r.items.get("link"), None)

    def test_shield(self):
        r = Report()
        idx, [page] = index(doc(SHIELDS))
        kite, buckler = [arsenal.melee_weapon(row, r, shield=True) for row in arsenal.rows(page, idx, r)]
        self.assertEqual(kite["shield"], {"subtype": "teardrop", "ap": 2, "defenseSectors": "T+A1+(H)/(L1+L2)"})
        self.assertEqual((kite["tabs"][0]["profile"], kite["description"]), ("", "Пехотный щит."))
        self.assertEqual(buckler["shield"], {"subtype": "buckler", "ap": 0, "defenseSectors": ""})
        self.assertEqual(r.items, {})

    def test_ranged(self):
        r = Report()
        idx, [page] = index(doc(RANGED))
        bow, pistol = [arsenal.ranged_weapon(row, r) for row in arsenal.rows(page, idx, r, link_required=False)]
        self.assertEqual(bow, {
            "name": "Longbow", "class": "special", "range": "S.b×15м", "damage": "1d10–1+S.b", "pen": "1",
            "damageType": "R", "rofSingle": "S", "rofShort": "–", "rofLong": "–", "clipCur": "1", "clipMax": "1",
            "reload": "½", "special": "Draw (4-5), Primitive", "upgrades": "", "description": "Тяжелый боевой лук.",
        })
        self.assertEqual((pistol["name"], pistol["class"], pistol["rofSingle"]), ("Кремневый Пистолет", "pistol", "S"))
        self.assertEqual(len(messages(r, "name")), 1)


GEAR = """
    # Освещение
    {{datatable
    |paging=false
    | Название | R | Wt | Цена |
    | --- | :---: | :---: | :---: |
    | [Hooded Lantern / Фонарь с Заслонкой](#lantern-) | -2 | 1 | 7 gp |
    | [Bullseye Lantern / Направленный Фонарь](#lantern-) | -2 | 1.5 | 12 gp |
    | [Coffee / Кофе (чашка)](/Iv%20Арсенал/Test/2%20Химия#coffee-) | -1 | - | 5 cp |
    | [Glow-Globe / Светосфера](#nowhere) | 1 | 0.5 | 110 gp |
    }}

    ## Масло

    #### Lantern / Фонарь
    **Редкость:** -2 | **Вес:** по варианту | **Цена:** по варианту
    Масляный фонарь.
    **Poor.Q:** тусклый.
    **Best.Q:** яркий.

    **Варианты:**
    - **С заслонкой.** **Вес:** 1.

    #### Oil / Масло
    **Редкость:** -4 | **Вес:** 0.5 | **Цена:** 1 sp
    **Мощность:** 3
    Лампадное масло.
"""

CHEMISTRY = """
    # Наркотики
    #### Coffee / Кофе
    **Редкость:** -1 | **Цена:** 5 cp
    Напиток из кофейных зёрен.
    **Приём:** Жидкость
    **Эффект:** Штраф –10 к тестам W, кроме тестов магии.
"""


class GearTest(unittest.TestCase):
    def setUp(self):
        self.r = Report()
        self.idx, (self.page, self.chem) = index(doc(GEAR), doc(CHEMISTRY, "iv арсенал/test/2 химия.md"))
        arsenal.check_entries(self.page, self.r, need_ru=True)
        self.items = arsenal.page_items(self.page, self.idx, self.r, "gear", self.page.heading())

    def test_shared_entry_gives_each_row_its_description(self):
        hooded, bullseye = self.items[0].record, self.items[1].record
        self.assertEqual((hooded["name"], hooded["name_ru"], hooded["weight"]), ("Hooded Lantern", "Фонарь с Заслонкой", 1.0))
        self.assertEqual((bullseye["name"], bullseye["weight"]), ("Bullseye Lantern", 1.5))
        self.assertEqual(hooded["description"], bullseye["description"])
        self.assertEqual(hooded["description"],
                         "Масляный фонарь.\n\nPoor.Q: тусклый.\nBest.Q: яркий.\n\nВарианты:\n- С заслонкой. Вес: 1.")
        self.assertEqual((hooded["entryType"], hooded["gearType"], hooded["armour"], hooded["conditions"]),
                         ("Освещение", "gear", {}, []))

    def test_row_of_another_page_item_is_left_to_it(self):
        self.assertNotIn("Coffee", [it.name for it in self.items])

    def test_broken_link_and_entry_without_row(self):
        names = [it.name for it in self.items]
        self.assertEqual(names, ["Hooded Lantern", "Bullseye Lantern", "Glow-Globe", "Oil"])
        oil = self.items[-1].record
        self.assertEqual((oil["weight"], oil["description"]), (0.5, "Мощность: 3\nЛампадное масло."))
        link = messages(self.r, "link")
        self.assertEqual(len(link), 2)
        self.assertIn("нет такого заголовка", link[0])
        self.assertIn("Oil: запись без строки", link[1])
        self.assertEqual(messages(self.r, "label"), ["Oil: неизвестная метка «Мощность»"])

    def test_chemistry_description_like_bc(self):
        items = arsenal.page_items(self.chem, self.idx, self.r, "consumable", self.chem.heading())
        self.assertEqual(items[0].record["description"],
                         "Напиток из кофейных зёрен.\n\nПриём: Жидкость\nЭффект: Штраф –10 к тестам W, кроме тестов магии.")


MODS = """
    # Модификации
    | Модификация | Категория | Требование | Кратко | Вес | R | Цена |
    | --- | --- | --- | --- | --- | --- | --- |
    | [Chain](#chain-) | Разное | Любое | Цепь | — | 0 | 15 gp |
    | [Weighted](#weighted-) | Разное | Баланс | +3 Dmg | +20% | -1 | 10 gp |
    ## Разное
    #### Chain / Цепь
    **Редкость:** 0 | **Цена:** 15 gp
    **Требование:** Любое.
    Оружие висит на цепи.
    #### Weighted / Утяжелённое
    **Редкость:** -1 | **Вес:** +20% | **Цена:** 10 gp ×М
    **Требование:** Баланс −1 или выше.
    Тяжелее.
    #### Spikes / Шипы
    **Редкость:** -1 | **Вес:** +1.5 кг | **Цена:** 50 gp
    Шипы.
"""


class ModsTest(unittest.TestCase):
    def test_mods(self):
        r = Report()
        idx, [page] = index(doc(MODS))
        chain, weighted, spikes = [it.record for it in arsenal.mods(page, idx, r, lambda e: e.groups.get(2, ""))]
        self.assertEqual(chain, {"name": "Chain", "name_ru": "Цепь", "weight": 0.0,
                                 "description": "Требование: Любое.\nОружие висит на цепи.", "entryType": "Разное"})
        self.assertEqual((weighted["weight"], weighted["description"]),
                         (0.0, "Вес: +20%\nТребование: Баланс −1 или выше.\nТяжелее."))
        self.assertEqual(spikes["weight"], 1.5)
        self.assertEqual(messages(r, "link"), ["Spikes: запись без строки в таблице раздела — выгружена отдельным предметом"])

    def test_same_name_in_two_sections(self):
        r = Report()
        items = [arsenal.Item({"name": "Chain", "name_ru": "Цепь", "entryType": "Рукопашное: Разное"}, "a.md:1"),
                 arsenal.Item({"name": "Chain", "entryType": "Дальнобойное: Прочие"}, "b.md:1"),
                 arsenal.Item({"name": "Scope", "entryType": "Дальнобойное: Прицелы"}, "b.md:2")]
        arsenal.disambiguate(items, r)
        self.assertEqual([(it.name, it.record.get("name_ru")) for it in items],
                         [("Chain (Рукопашное)", "Цепь (рукопашное)"), ("Chain (Дальнобойное)", None), ("Scope", None)])
        self.assertEqual(len(messages(r, "duplicate")), 2)


BC_GEAR = [
    {"name": "Recaf", "description": "Напитки.\n\nПрием: Жидкость\nЭффект: Штраф –10 к тестам W, кроме психотестов.",
     "gearType": "consumable", "conditions": []},
    {"name": "Commorrite Combat Drugs – Hypex", "description": "Боевые наркотики.", "gearType": "consumable", "conditions": []},
    {"name": "Mjod", "description": "Хмель.", "gearType": "consumable", "conditions": []},
]
BC_CONDITIONS = [
    {"name": "Characteristic Damage (WS)", "name_ru": "Урон Характеристики (WS)", "x": "урон",
     "conditions": [{"type": "CharacteristicBonus", "name": "WS", "value": "-X"}]},
    {"name": "Recaf", "name_ru": "Рекаф", "x": None,
     "conditions": [{"type": "RollBonus", "name": "W", "value": "-10", "except": ["psychic"]}]},
    {"name": "Recaf (Withdrawal)", "name_ru": "Рекаф (Ломка)", "x": None,
     "conditions": [{"type": "RollBonus", "name": "F", "value": "-15"}]},
    {"name": "Recafine", "name_ru": "Не то", "x": None, "conditions": []},
    {"name": "Commorrite Combat Drugs – Hypex", "name_ru": "Комморритские Боевые Наркотики – Гипекс", "x": None,
     "conditions": [{"type": "MovementBonus", "value": "5"}]},
    {"name": "Prone", "name_ru": "Сбит с Ног", "x": None,
     "conditions": [{"type": "RollBonus", "name": "WS", "value": "-20"}]},
    {"name": "Hex of Decrepitude (1)", "name_ru": "Порча Дряхлости (1)", "x": None,
     "conditions": [{"type": "CharacteristicBonus", "name": "T", "value": "-10"}]},
]
NAMES = {"gear": {"Coffee": "Recaf", "Drow Combat Drugs": "Commorrite Combat Drugs", "Gone": "Nothing"},
         "status_names": {"Сбитие с Ног": "Prone"}}

STATUSES = """
    # Статусы
    ## Сбитие с Ног
    Лежачий персонаж получает штраф −20 на WS.
    ## Ступор
    Не может действовать.
"""


class BCTest(unittest.TestCase):
    def setUp(self):
        self.bc = bcmod.BC(BC_GEAR, BC_CONDITIONS, NAMES)
        self.r = Report()

    def item(self, name, ru, description, where="c.md:1"):
        return arsenal.Item({"name": name, "name_ru": ru, "description": description, "conditions": []}, where)

    def test_chemistry_pairs(self):
        coffee = self.item("Coffee", "Кофе", "Напиток.\n\nПриём: Жидкость\nЭффект: Штраф –10 к тестам W, кроме тестов магии.")
        drow = self.item("Drow Combat Drugs", "Боевые Наркотики Дроу", "Совсем другой текст про эльфов и их яды.")
        new = self.item("Spice", "Пряность", "Новое.")
        pairs = bcmod.chemistry([coffee, drow, new], self.bc, self.r)
        self.assertEqual([(it.name, b) for it, b in pairs], [("Coffee", "Recaf"), ("Drow Combat Drugs", "Commorrite Combat Drugs")])
        bc_msgs = messages(self.r, "bc")
        self.assertTrue(any("«Gone» → «Nothing»" in m for m in bc_msgs))
        self.assertTrue(any(m.startswith("Drow Combat Drugs ↔ Commorrite Combat Drugs – Hypex") for m in bc_msgs))
        self.assertIn("Spice: нет пары в BC — механики нет", bc_msgs)
        self.assertNotIn("Coffee", " ".join(bc_msgs))
        self.assertEqual(self.r.notes, ["химия BC без пары в PF (1): Mjod"])

    def test_conditions(self):
        coffee = self.item("Coffee", "Кофе", "Эффект: штраф –10 к тестам W.")
        drow = self.item("Drow Combat Drugs", "Боевые Наркотики Дроу", "Гипекс: +5 к SPD.")
        powers = [("Hex of Decrepitude", "Порча Дряхлости", "Цель получает −10 к T.", "s.md:5")]
        out = conditions.build(self.bc, [(coffee, "Recaf"), (drow, "Commorrite Combat Drugs")], powers, self.r,
                               status_doc=doc(STATUSES, "ii механика/статусы.md"))
        by = {c["name"]: c for c in out}
        self.assertEqual(list(by), ["Prone", "Ступор", "Characteristic Damage (WS)", "Coffee", "Coffee (Withdrawal)",
                                    "Drow Combat Drugs – Hypex", "Hex of Decrepitude (1)"])
        self.assertEqual(by["Prone"], {"name": "Prone", "name_ru": "Сбитие с Ног", "x": None,
                                       "conditions": [{"type": "RollBonus", "name": "WS", "value": "-20"}]})
        self.assertEqual(by["Ступор"]["conditions"], [])
        self.assertEqual(by["Coffee"]["conditions"], BC_CONDITIONS[1]["conditions"])
        self.assertEqual(by["Coffee (Withdrawal)"]["name_ru"], "Кофе (Ломка)")
        self.assertEqual(by["Drow Combat Drugs – Hypex"]["name_ru"], "Боевые Наркотики Дроу – Гипекс")
        self.assertEqual(by["Hex of Decrepitude (1)"]["name_ru"], "Порча Дряхлости (1)")
        self.assertEqual(by["Characteristic Damage (WS)"]["name_ru"], "Урон Характеристики (WS)")
        # Числа механики, которых нет в тексте PF: ломка −15 у кофе.
        self.assertEqual(messages(self.r, "bc_check"), ["Coffee (Withdrawal) ← Recaf (Withdrawal): в тексте PF нет RollBonus F -15"])
        names = messages(self.r, "name")
        self.assertEqual(len(names), 2)
        self.assertIn("взято «Prone» из bc_names.json", names[0])
        self.assertIn("нет английского имени и его нет в bc_names.json", names[1])


if __name__ == "__main__":
    unittest.main()
