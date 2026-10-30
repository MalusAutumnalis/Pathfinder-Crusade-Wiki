"""Тесты материалов, зачарований и естественного оружия: `cd .scripts/gamedata && python -m unittest`."""

import textwrap
import unittest

import arsenal
import materials
import wiki
from report import Report


def doc(text, path="iv арсенал/test/1 тест.md"):
    return wiki.parse_document(textwrap.dedent(text).lstrip("\n"), path)


def messages(r, kind):
    return [m for _, m, _ in r.items.get(kind, [])]


MATERIALS = """
    # Материалы

    | Материал | Тип | Применение | R | Цена | Банк | Вес | Прочность | Ёмкость | AP | Pen | Особое |
    | --- | --- | --- | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | --- |
    | [Мифрил](#mithral-) | Металл | Универсальный | 3 | ×15 | ×1.5 | ×0.5 | 2 | ×1 | +1 | +1 | +20 Max.A |
    | [Кожа](#leather-) | Кожа | Броня | −3 | ×0.3 | ×0.5 | ×1 | −1 | ×1 | 0 | — | — |

    #### Mithral / Мифрил
    **Редкость:** 3 | **Цена:** ×15 | **Банк:** ×1.5 | **Вес:** ×0.5 | **Прочность:** 2 | **Ёмкость:** ×1 | **AP:** +1 | **Pen:** +1
    **Применение:** Универсальный
    **Особое:**
    - Броня получает +20 Max.A.
    - Клинки острее.

    **Описание:** Лёгкий металл.

    #### Leather / Кожа
    **Редкость:** −3 | **Цена:** ×0.3 | **Банк:** ×0.5 | **Вес:** ×1 | **Прочность:** −2 | **Ёмкость:** ×1 | **AP:** 0 | **Pen:** —
    **Применение:** Броня
    **Описание:** Выделанная кожа.

    #### Tin / Олово
    **Редкость:** 0

    ## Инкрустация
    | Камень | Редкость | Цена | Ёмкость |
    | --- | :---: | :---: | :---: |
    | Кварц | 0 | 1500 | +1 |
    | Янтарь | 1 | 2000 | +2 |
"""


class MaterialsTest(unittest.TestCase):
    def setUp(self):
        self.r = Report()
        self.out = materials.materials(self.r, doc(MATERIALS))
        self.by_name = {m["name"]: m for m in self.out}

    def test_numbers_and_texts(self):
        m = self.by_name["Mithral"]
        self.assertEqual(m["name_ru"], "Мифрил")
        self.assertEqual(m["entryType"], "Металл")
        self.assertEqual((m["rarity"], m["priceFactor"], m["bankFactor"], m["weightFactor"]), (3, 15, 1.5, 0.5))
        self.assertEqual((m["durability"], m["capacityFactor"], m["ap"], m["pen"]), (2, 1, 1, 1))
        self.assertEqual(m["short"], "+20 Max.A")
        self.assertEqual(m["special"], "- Броня получает +20 Max.A.\n- Клинки острее.")
        self.assertEqual(m["description"], "Лёгкий металл.")

    def test_dash_is_none(self):
        leather = self.by_name["Leather"]
        self.assertEqual((leather["rarity"], leather["pen"], leather["short"]), (-3, None, ""))

    def test_mithral_cap_bonus(self):
        self.assertEqual(self.by_name["Mithral"]["conditions"],
                         [{"type": "CharacteristicCapBonus", "name": "A", "value": "20"}])
        self.assertEqual(self.by_name["Leather"]["conditions"], [])

    def test_table_and_entry_disagree(self):
        self.assertTrue(any("Прочность: в записи −2, в таблице −1" in m for m in messages(self.r, "value")))
        self.assertEqual(self.by_name["Leather"]["durability"], -2)

    def test_entry_without_row_is_reported(self):
        self.assertNotIn("Tin", self.by_name)
        self.assertTrue(any("Tin" in m for m in messages(self.r, "link")))

    def test_gems(self):
        gems = [m for m in self.out if m["entryType"] == materials.INLAY_TYPE]
        self.assertEqual(gems[0], {"name": "Quartz", "name_ru": "Кварц", "entryType": "Инкрустация",
                                   "rarity": 0, "price": 1500, "capacityBonus": 1})
        self.assertEqual(gems[1]["name"], "Янтарь")
        self.assertTrue(any("Янтарь" in m for m in messages(self.r, "name")))


INDEX = """
    # Зачарования
    | Зачарование | Категория | Ёмкость | Кратко |
    | --- | --- | :---: | --- |
    | [Feather](/Iv%20Арсенал/7%20Зачарования/1%20Тест#feather) | Универсальное | 2 / 4 / 11 | Вес |
    | [Flaming](/Iv%20Арсенал/7%20Зачарования/1%20Тест#flaming) | Оружие | 1 / 3 | Flame |
    | [Greater Accuracy](/Iv%20Арсенал/7%20Зачарования/1%20Тест#greater-accuracy) | Дальнее оружие | 5 | Даёт Accurate |
    | [Tempo](/Iv%20Арсенал/7%20Зачарования/1%20Тест#tempo) | Поножи | 8 / 12 | Стойки |
    | [Grasping](/Iv%20Арсенал/7%20Зачарования/9%20Наручи#grasping) | Наручи | 3 | Остановить падение |
"""

ENCHANTMENTS = """
    # Тест

    #### Feather
    **Ёмкость 2:** Вес до ½.
    **Ёмкость 4:** Вес до ¼.
    **Ёмкость 11:** Вес до 0.

    #### Flaming
    **Ёмкость 1:** Оружие получает свойство Flame (d5).
    **Ёмкость 3:** Оружие получает свойство Flame (d10), тест A–20.
    **Ёмкость 7:** Оружие получает свойство Flame (2d10).

    #### Greater Accuracy
    **Ёмкость:** 5
    **Требования:** оружие без свойства Inaccurate
    **Эффект:** Оружие получает свойство Accurate.

    #### Tempo
    Дуэльные стойки.

    **Ёмкость 8:**
    - **Агрессивная Стойка:** урон.

    **Ёмкость 12:** Как выше, но:
    - **Агрессивная Стойка:** больше урона.

    ####
    **Ёмкость 3:** Без имени.

    #### Orphan
    **Ёмкость:** 1
    **Эффект:** Нет в таблице.
"""


class EnchantmentsTest(unittest.TestCase):
    def setUp(self):
        self.r = Report()
        d = doc(ENCHANTMENTS, "iv арсенал/7 зачарования/1 тест.md")
        self.out = materials.enchantments(self.r, doc(INDEX, "iv арсенал/7 зачарования.md"), [d])
        self.by_name = {e["name"]: e for e in self.out}

    def test_levels_and_weight_factor(self):
        feather = self.by_name["Feather"]
        self.assertEqual((feather["entryType"], feather["short"]), ("Универсальное", "Вес"))
        self.assertEqual([(lv["capacity"], lv["weightFactor"]) for lv in feather["levels"]], [(2, 0.5), (4, 0.25), (11, 0)])
        self.assertEqual(feather["levels"][0]["text"], "Вес до ½.")

    def test_special_from_granted_property(self):
        flaming = self.by_name["Flaming"]
        self.assertEqual([lv["special"] for lv in flaming["levels"]], ["Flame (d5)", "Flame (d10)", "Flame (2d10)"])
        self.assertTrue(any("Flaming" in m and "[1, 3, 7]" in m for m in messages(self.r, "value")))

    def test_single_level_with_requirement(self):
        ga = self.by_name["Greater Accuracy"]
        self.assertEqual(ga["requirement"], "оружие без свойства Inaccurate")
        self.assertEqual(ga["levels"], [{"capacity": 5, "text": "Оружие получает свойство Accurate.", "special": "Accurate"}])

    def test_multiline_level_and_description(self):
        tempo = self.by_name["Tempo"]
        self.assertEqual(tempo["description"], "Дуэльные стойки.")
        self.assertEqual(tempo["levels"][0]["text"], "- Агрессивная Стойка: урон.")
        self.assertEqual(tempo["levels"][1]["text"], "Как выше, но:\n- Агрессивная Стойка: больше урона.")

    def test_bare_heading_ends_the_entry(self):
        self.assertEqual([lv["capacity"] for lv in self.by_name["Tempo"]["levels"]], [8, 12])
        self.assertTrue(any("без имени" in m for m in messages(self.r, "name")))

    def test_row_without_entry_falls_back_to_index(self):
        self.assertEqual(self.by_name["Grasping"]["levels"], [{"capacity": 3, "text": "Остановить падение", "special": ""}])
        self.assertTrue(any("Grasping" in m for m in messages(self.r, "link")))

    def test_entry_without_row_is_reported(self):
        self.assertNotIn("Orphan", self.by_name)
        self.assertTrue(any("Orphan" in m for m in messages(self.r, "link")))

    def test_rule_without_level_is_reported(self):
        self.assertTrue(any("Distance" in m for m in messages(self.r, "value")))


TRAITS = """
    # Трейты

    #### Natural Weapons (X) / Естественное Оружие
    Когти.

    | Оружие | Тип | Rng | Dmg | Pen | Свойства | Bl |
    |---|---|---|---|---|---|---|
    | Кулаки | Кулак.Б | 0-1 | 1d10+X I(Cr) | 0 | Primitive | -1 |
    | Рога | – | 0 | 2d10+X R | 0 | Primitive | -2 |
    | Хвост | Кнут | 2-5 | 1d10+X R | 0 | Primitive | -2 |

    Рога — только в Натиск.

    #### Deadly Natural Weapons (X) / Смертельное Естественное Оружие
    | Оружие | Тип | Rng | Dmg | Pen | Свойства | Bl |
    |---|---|---|---|---|---|---|
    | Копыта | Нет | 0 | 1d10+X I(Cr) | X | Imprecise, Reinforced | -2 |
"""


class NaturalWeaponsTest(unittest.TestCase):
    def setUp(self):
        self.r = Report()
        self.out = arsenal.natural_weapons(self.r, doc(TRAITS, "iii продвижение/трейты.md"))
        self.by_name = {w["name"]: w for w in self.out}

    def test_records(self):
        fists = self.by_name["Fists (Natural Weapons)"]
        self.assertEqual(fists["name_ru"], "Кулаки (Естественное Оружие)")
        self.assertEqual((fists["entryType"], fists["trait"], fists["balance"]), ("Трейт", "Natural Weapons (X)", "-1"))
        self.assertEqual(fists["tabs"], [{"profile": "fist.a", "range": "0-1", "damage": "1d10", "pen": "0",
                                          "damageType": "I(Cr)", "special": "Primitive"}])
        self.assertEqual(fists["description"], "Рога — только в Натиск.")

    def test_dash_and_no_profiles(self):
        self.assertEqual(self.by_name["Horns (Natural Weapons)"]["tabs"][0]["profile"], "no")
        self.assertEqual(self.by_name["Horns (Natural Weapons)"]["tabs"][0]["damage"], "2d10")
        hooves = self.by_name["Hooves (Deadly Natural Weapons)"]
        self.assertEqual((hooves["tabs"][0]["profile"], hooves["tabs"][0]["pen"]), ("no", "0"))
        self.assertEqual(hooves["trait"], "Deadly Natural Weapons (X)")

    def test_unknown_weapon_is_reported(self):
        self.assertEqual(len(self.out), 3)
        self.assertTrue(any("Хвост" in m for m in messages(self.r, "name")))


if __name__ == "__main__":
    unittest.main()
