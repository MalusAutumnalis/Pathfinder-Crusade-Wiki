"""Тесты разбора вики: `cd .scripts/gamedata && python -m unittest`."""

import textwrap
import unittest

import character
import pf
import spells
import wiki
from report import Report


def doc(text, path="test.md"):
    return wiki.parse_document(textwrap.dedent(text).lstrip("\n"), path)


class TitleTest(unittest.TestCase):
    def test_pair_and_tags(self):
        t = wiki.parse_title("Bite (X) / Укус #New")
        self.assertEqual((t.en, t.ru, t.tags, t.problems), ("Bite (X)", "Укус", ["New"], []))

    def test_several_tags(self):
        t = wiki.parse_title("Hatred / Ненависть #Changed #Review")
        self.assertEqual(t.tags, ["Changed", "Review"])
        self.assertEqual(t.text, "Hatred / Ненависть")

    def test_unknown_tag_counts_as_review(self):
        t = wiki.parse_title("Trait / Трейт # TO DO")
        self.assertEqual((t.en, t.ru, t.tags), ("Trait", "Трейт", ["Review"]))
        self.assertEqual(len(t.problems), 1)

    def test_slash_inside_names(self):
        t = wiki.parse_title("Open/Lock / Открыть/Запереть")
        self.assertEqual((t.en, t.ru, t.problems), ("Open/Lock", "Открыть/Запереть", []))

    def test_separator_without_spaces(self):
        t = wiki.parse_title("Dance of the Fallen Leaf/ Пляска опавшего листа")
        self.assertEqual((t.en, t.ru), ("Dance of the Fallen Leaf", "Пляска опавшего листа"))
        self.assertEqual(len(t.problems), 1)

    def test_single_names(self):
        t = wiki.parse_title("Spikes (X, Y) #New")
        self.assertEqual((t.en, t.ru, t.tags), ("Spikes (X, Y)", "", ["New"]))
        t = wiki.parse_title("Нежить #New")
        self.assertEqual((t.en, t.ru), ("", "Нежить"))

    def test_placeholder_in_english_name(self):
        t = wiki.parse_title("Battle Cant (<Организация>) / Боевой Кант (<Организация>) (I)")
        self.assertEqual(t.problems, [])

    def test_link_in_title(self):
        t = wiki.parse_title("[Lantern / Фонарь](#lantern-)")
        self.assertEqual((t.en, t.ru), ("Lantern", "Фонарь"))


class FieldsTest(unittest.TestCase):
    def test_several_labels_in_a_line(self):
        fs = wiki.line_fields("**Уровень:** 1, **Скл.:** I, FC  ", 3)
        self.assertEqual([(f.label, f.value, f.line) for f in fs], [("Уровень", "1", 3), ("Скл.", "I, FC", 3)])

    def test_pipe_separated(self):
        fs = wiki.line_fields("**Редкость:** 1 | **Вес:** 0.5 | **Цена:** 1 000 gp")
        self.assertEqual([(f.label, f.value) for f in fs], [("Редкость", "1"), ("Вес", "0.5"), ("Цена", "1 000 gp")])

    def test_god_leftover_stays_in_value(self):
        fs = wiki.line_fields("**Уровень:** 3, Бог: Тзинч | **Скл.:** W, Def")
        self.assertEqual(fs[0].value, "3, Бог: Тзинч")

    def test_not_a_field_line(self):
        self.assertEqual(wiki.line_fields("Текст **Метка:** внутри"), [])

    def test_split_fields_stops_at_open_label(self):
        lines = [(1, "**Стоимость:** 100 XP  "), (2, ""), (3, "**Эффект:** Начало."), (4, "**Раны:** 10"), (5, "Хвост")]
        fields, rest = wiki.split_fields(lines, open_labels=("Эффект",))
        self.assertEqual([f.label for f in fields], ["Стоимость", "Эффект"])
        self.assertEqual(rest, [(4, "**Раны:** 10"), (5, "Хвост")])

    def test_split_fields_stops_at_text(self):
        fields, rest = wiki.split_fields([(1, "**Скл.:** A, Gen"), (2, "Текст."), (3, "**Действие:** Полное")])
        self.assertEqual([f.label for f in fields], ["Скл."])
        self.assertEqual([n for n, _ in rest], [2, 3])


class DocumentTest(unittest.TestCase):
    SRC = """
        # Телепатия
        ## Месмеризм
        #### Delude / Заблуждение
        Текст.
        ##### Sub / Под
        Ещё.
        ### Глубже
        #### Passion / Страсть #New
        ```
        # не заголовок
        ```
        ## Иллюзионизм
        #### Noise / Шум
    """

    def test_entries_and_groups(self):
        es = wiki.entries(doc(self.SRC))
        self.assertEqual([e.name for e in es], ["Delude", "Passion", "Noise"])
        self.assertEqual(es[0].groups, {1: "Телепатия", 2: "Месмеризм"})
        self.assertEqual(es[1].groups, {1: "Телепатия", 2: "Месмеризм", 3: "Глубже"})
        self.assertEqual(es[2].groups, {1: "Телепатия", 2: "Иллюзионизм"})
        self.assertEqual(es[1].title.tags, ["New"])

    def test_body_and_children(self):
        d = doc(self.SRC)
        e = wiki.entries(d)[0]
        self.assertEqual([t for _, t in e.body()], ["Текст.", "##### Sub / Под", "Ещё."])
        self.assertEqual([t for _, t in e.own_body()], ["Текст."])
        self.assertEqual([c.name for c in e.children()], ["Sub"])
        self.assertEqual(e.where, "test.md:3")

    def test_within(self):
        es = wiki.entries(doc(self.SRC), within=lambda g: g.get(2) == "Иллюзионизм")
        self.assertEqual([e.name for e in es], ["Noise"])


class TextTest(unittest.TestCase):
    def test_plain_inline(self):
        s = wiki.plain_inline("**Жирный** [Ссылка](/a#b) и [[Вики|текст]] S\\–\\– <span>x</span><br>y")
        self.assertEqual(s, "Жирный Ссылка и текст S–– x\ny")

    def test_keeps_placeholders(self):
        self.assertEqual(wiki.plain_inline("Cant (<Организация>)"), "Cant (<Организация>)")

    def test_plain_text(self):
        s = wiki.plain_text([(1, "Первая  "), (2, "##### Подзаголовок"), (3, ""), (4, ""), (5, ""), (6, "Вторая")])
        self.assertEqual(s, "Первая\nПодзаголовок\n\nВторая")


class TablesTest(unittest.TestCase):
    def test_markdown_table(self):
        d = doc("""
            Текст
            | Rng | RoF | Dmg |
            |-----|-----|-----|
            | 30м | S\\–\\– | 1d10 E |
            После
        """)
        [t] = wiki.tables(d.numbered(1, 99))
        self.assertEqual(t.header, ["Rng", "RoF", "Dmg"])
        self.assertEqual(t.rows, [["30м", "S\\–\\–", "1d10 E"]])
        self.assertEqual((t.line, t.end), (2, 5))
        self.assertEqual(t.column("dmg"), 2)

    def test_datatable(self):
        d = doc("""
            {{datatable
            |paging=false
            |sortable=true
            | Название | Цена |
            | --- | :---: |
            | [Recoil Glove / Откатная Перчатка](#recoil-glove-) | 50 gp |
            | Warhammer | 1<br>2 |
            }}
            #### Recoil Glove / Откатная Перчатка
        """)
        [t] = wiki.tables(d.numbered(1, 99))
        self.assertEqual(t.options, {"paging": "false", "sortable": "true"})
        self.assertEqual(t.dicts()[0]["Цена"], "50 gp")
        self.assertEqual(wiki.cell_link(t.rows[0][0]), ("Recoil Glove / Откатная Перчатка", "#recoil-glove-"))
        self.assertEqual(wiki.split_br(t.rows[1][1]), ["1", "2"])
        self.assertEqual(t.end, 9)

    def test_escaped_pipe(self):
        self.assertEqual(wiki.split_row("| a\\|b | c |"), ["a\\|b", "c"])


class TestBaseTest(unittest.TestCase):
    SKILLS = {"Deceive", "Trade", "Intimidate", "Sleight of Hand", "Spellcraft"}

    def test_bases(self):
        cases = {
            "Cs+20/10/0 (vss S+0)": ("cs", "Cs"),
            "Cs–10 vs W+0": ("cs", "Cs"),
            "W–20 vs W+0": ("characteristic", "W"),
            "S+0": ("characteristic", "S"),
            "Deceive(F) +0 vs W +0": ("skill", "Deceive"),
            "Trade(Bardic)(Стат Навыка) +0 или Intimidate(F или W) +0": ("skill", "Trade"),
            "Sleight of Hand(F) +0": ("skill", "Sleight of Hand"),
            "Spellcraft(P)+10": ("skill", "Spellcraft"),
            "Psyniscience(P)+30": (None, "Psyniscience"),
            "Cast+10": (None, "Cast"),
            "Cor+0": (None, "Cor"),
        }
        for test, want in cases.items():
            self.assertEqual(pf.test_base(test, self.SKILLS), want, test)

    def test_aptitudes(self):
        self.assertEqual(pf.parse_aptitudes("I, FC"), (["I", "FC"], []))
        self.assertEqual(pf.parse_aptitudes("Bs, Fin"), (["Bs", "Fin"], ["Bs"]))


SPELLS = """
    # Телекинез
    ## Базовая Сила
    #### Mind Over Matter / Разум Превыше Материи
    **Стоимость:** 100 XP
    **Требования:** PR 1+
    **Действие:** Полудействие
    **Поддержание:** Свободное действие
    **Тест магии:** Cs+20/10/0 (vss S+0)
    **Дальность:** PR×10м
    **Тип:** Атака
    **Эффект:** Начало [ссылка](#x).
    1) Режим.

    | Rng | RoF | Dmg | Pen | Свойства |
    |-----|-----|-----|-----|----------|
    | PR×10м | S\\–\\– | 2d10+2×PR E(Fl) | 0 | Primitive |

    После таблицы.
    ## Разное
    #### Jump / Прыжок
    **Стоимость:** 1 000 xp
    **Требования:** Нет
    **Тест магии:** Cor+0
    **Цвет:** синий
    **Эффект:** Прыг.
"""


class SpellTest(unittest.TestCase):
    def test_spell(self):
        r = Report()
        mom, jump = [spells.Spell(e, r, {"Athletics"}) for e in wiki.entries(doc(SPELLS))]
        p = mom.power
        self.assertEqual((p["name"], p["name_ru"], p["type"]), ("Mind Over Matter", "Разум Превыше Материи", "Телекинез"))
        self.assertEqual((p["psychotest"], p["subtypes"], p["range"]), ("Cs+20/10/0 (vss S+0)", "Атака", "PR×10м"))
        self.assertEqual((p["damage"], p["damageType"], p["pen"], p["special"]), ("2d10+2×PR", "E(Fl)", "0", "Primitive"))
        self.assertEqual((p["rofSingle"], p["rofShort"], p["rofLong"], p["weaponRange"]), ("S", "–", "–", "PR×10м"))
        self.assertEqual(p["effect"], "Начало ссылка.\n1) Режим.\n\nПосле таблицы.")
        self.assertNotIn("roll", p)
        self.assertEqual(mom.advancement(), {
            "type": "psychicPower", "name": "Mind Over Matter", "name_ru": "Разум Превыше Материи",
            "discipline": "Телекинез", "subdiscipline": "Базовая Сила", "experienceCost": 100, "requirements": "PR 1+",
        })
        a = jump.advancement()
        self.assertEqual((a["experienceCost"], a["requirements"], a["subdiscipline"]), (1000, None, "Разное"))

        kinds = {k: [m for _, m, _ in v] for k, v in r.items.items()}
        self.assertEqual(kinds["label"], ["Jump: неизвестная метка «Цвет»"])
        self.assertEqual(kinds["test"], ["Jump: «Cor+0» начинается с «Cor»"])
        self.assertIn("Jump: нет «Действие»", kinds["required"])
        self.assertNotIn("format", kinds)

    def test_art_takes_base_profile(self):
        r = Report()
        [mom, _] = [spells.Spell(e, r, set()) for e in wiki.entries(doc(SPELLS))]
        arts_doc = doc("""
            # Искусства Барда
            ## Телекинез
            #### Mind Over Matter / Разум над Материей
            **Уровень:** 2, **Скл.:** Gen, Mag
            **Требования:** Trade(Bardic) +10
            **Тест магии:** Trade(Bardic)(Стат Навыка) +0
            Отличие от базового.
        """)
        [e] = wiki.entries(arts_doc)
        art = spells.Art(e, ("Bard", "Бард"), mom, r, {"Trade"})
        p = art.power()
        self.assertEqual((p["name"], p["name_ru"]), ("Mind Over Matter (Bard)", "Разум над Материей (Бард)"))
        self.assertEqual(p["subtypes"], "Атака, Arts (Bard)")
        self.assertEqual((p["level"], p["psychotest"], p["damage"]), (2, "Trade(Bardic)(Стат Навыка) +0", "2d10+2×PR"))
        self.assertTrue(p["effect"].startswith("Отличие от базового.\n\nНачало"))
        self.assertNotIn("roll", p)
        self.assertEqual(art.advancement(), {
            "type": "talent", "name": "Mind Over Matter (Bard)", "name_ru": "Разум над Материей (Бард)",
            "level": 2, "aptitudes": "Gen, Mag", "requirements": "Trade(Bardic) +10",
        })
        self.assertEqual(mom.power["subtypes"], "Атака", "the base spell stays as it was")
        self.assertEqual([m for _, m, _ in r.items["arts"]],
                         ["Mind Over Matter: русское имя «Разум над Материей», у базового заклинания — «Разум Превыше Материи»"])


class TalentTest(unittest.TestCase):
    def test_talent(self):
        r = Report()
        [t, bad] = [character.parse_talent(e, r) for e in wiki.entries(doc("""
            # Общие
            #### Combat Formation / Боевое Построение
            **Уровень:** 1, **Скл.:** I, FC
            **Требования:** I 40
            Текст [ссылка](#a).
            #### Pain Is an Illusion / Боль — Иллюзия
            **Уровень:** 3, Бог: Тзинч | **Скл.:** W, Psy
            **Специализации:** Нож, Меч
        """))]
        self.assertEqual(t.record(), {"name": "Combat Formation", "name_ru": "Боевое Построение", "description": "Текст ссылка."})
        self.assertEqual(t.advancement(), {
            "type": "talent", "name": "Combat Formation", "name_ru": "Боевое Построение",
            "level": 1, "aptitudes": "I, FC", "requirements": "I 40",
        })
        self.assertEqual((bad.level, bad.aptitudes, bad.requirements, bad.description), (3, "W", None, "Специализации: Нож, Меч"))
        self.assertEqual(sorted(m for _, m, _ in r.items["value"]), [
            "Pain Is an Illusion: лишнее в строке уровня: «Бог: Тзинч»",
            "Pain Is an Illusion: склонность не из списка: «W, Psy»",
        ])


class ReportTest(unittest.TestCase):
    def test_collapses_groups(self):
        r = Report()
        for n in range(5):
            r.add("test", f"a.md:{n + 1}", f"S{n}: «Cor+0»", group="тесты начинаются с «Cor»")
        r.add("test", "b.md:1", "X: «Cor+0»", group="тесты начинаются с «Cor»")
        text = r.render()
        self.assertIn("- a.md — тесты начинаются с «Cor» — 5 записей: S0, S1, S2, S3, S4", text)
        self.assertIn("- b.md:1 — X: «Cor+0»", text)


if __name__ == "__main__":
    unittest.main()
