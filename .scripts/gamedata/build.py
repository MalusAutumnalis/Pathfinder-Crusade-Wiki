"""Выгрузка вики Pathfinder Crusade в ассеты автодополнения листа.

    python .scripts/gamedata/build.py [--out DIR] [--report FILE]

По умолчанию пишет в `../CharacterSheet/internal/gamedata/assets/pathfinder_crusade/`
(рядом с вики), отчёт — в `.scripts/gamedata/report.txt` и кратко в stdout.
Формы записей — как у ассетов Black Crusade (`internal/gamedata/*.go` чарника).
"""

import argparse
import json
import sys
from pathlib import Path

import arsenal
import bc as bcmod
import character
import conditions
import spells
import wiki
from report import Report

HERE = Path(__file__).resolve().parent
DEFAULT_OUT = wiki.ROOT.parent / "CharacterSheet" / "internal" / "gamedata" / "assets" / "pathfinder_crusade"
DEFAULT_REPORT = HERE / "report.txt"


def unique(items, key, where, report, what, group=None):
    """Первые записи с каждым английским именем; повторы — в отчёт (group — свернуть по файлу)."""
    seen, out = {}, []
    for item in items:
        k = key(item).lower()
        if k in seen:
            if group:
                report.add("duplicate", where(item), f"{key(item)}: {what} уже есть ({seen[k]})", group=group)
            else:
                report.add("duplicate", where(item), f"{what} «{key(item)}» уже есть: {seen[k]}")
            continue
        seen[k] = where(item)
        out.append(item)
    return out


def build(report, bc_assets=bcmod.DEFAULT_ASSETS):
    """Все выгружаемые файлы: {имя файла: список записей}."""
    skill_list = character.skills(report)
    skill_names = character.skill_groups(skill_list)

    talent_list = character.talents(report)
    trait_list = character.traits(report)
    spell_list = spells.spells(report, skill_names)
    elites = spells.elite_archetypes(report, skill_names)
    for el in elites:
        talent_list += el.talents
        spell_list += el.spells
        trait_list += el.traits
    art_list = spells.arts(report, spell_list, skill_names)

    talent_list = unique(talent_list, lambda t: t.entry.name, lambda t: t.entry.where, report, "талант")
    trait_list = unique(trait_list, lambda t: t[1].name, lambda t: t[1].where, report, "трейт")
    spell_list = unique(spell_list, lambda s: s.entry.name, lambda s: s.entry.where, report, "заклинание")
    art_list = unique(art_list, lambda a: a.name, lambda a: a.entry.where, report, "Искусство")
    skill_list = unique(skill_list, lambda s: s.en, lambda s: s.entry.where, report, "навык")

    advancements = character.characteristics(report)
    for s in skill_list:
        advancements += s.advancements()
    for t in talent_list:
        advancements += t.advancements()
    advancements += [a.advancement() for a in art_list]
    advancements += [s.advancement() for s in spell_list]
    advancements += [el.advancement() for el in elites if el.entry is not None]

    files = {
        "talents.json": [t.record() for t in talent_list] + [a.talent() for a in art_list],
        "traits.json": [t[0] for t in trait_list],
        "advancements.json": advancements,
        "psychic_powers.json": [s.power for s in spell_list] + [a.power() for a in art_list],
    }

    powers = [(s.power["name"], s.power.get("name_ru", ""), s.power.get("effect", ""), s.entry.where) for s in spell_list]
    powers += [(a.name, a.power().get("name_ru", ""), a.power().get("effect", ""), a.entry.where) for a in art_list]
    powers += [(r["name"], r.get("name_ru", ""), r["description"], t.entry.where)
               for t in talent_list for r in [t.record()]]
    powers += [(r["name"], r.get("name_ru", ""), r["description"], e.where) for r, e in trait_list]
    files.update(build_arsenal(report, bcmod.BC.load(bc_assets), powers))
    return files


def build_arsenal(report, bc, powers):
    """Арсенал и условия: melee, ranged, gear, cybernetics, модификации, conditions."""
    index = arsenal.Index()
    name = lambda x: x.name
    where = lambda x: x.where

    melee, ranged, shields = arsenal.weapons(index, report)
    melee = unique(melee + shields, name, where, report, "рукопашное оружие")
    ranged = unique(ranged, name, where, report, "дальнобойное оружие")
    armour = arsenal.armour(index, report)
    gear = arsenal.gear(index, report)
    chemistry = [it for it in gear if it.record["gearType"] == "consumable" and "6 химия/" in it.where]
    pairs = bcmod.chemistry(chemistry, bc, report)
    weapons = [arsenal.Item(w.gear(), w.where) for w in melee + ranged]
    gear = unique(weapons + armour + gear, name, where, report, "предмет",
                  group="английское имя повторяет строку выше — выгружена первая (нужно уточнение в английском имени)")
    cybernetics = unique(arsenal.cybernetics(index, report), name, where, report, "протез")
    armour_mods = unique(arsenal.armour_mods(index, report), name, where, report, "модификация брони")
    weapon_mods = unique(arsenal.weapon_mods(index, report), name, where, report, "модификация оружия")

    return {
        "melee.json": [w.record for w in melee],
        "ranged.json": [w.record for w in ranged],
        "gear.json": [it.record for it in gear],
        "cybernetics.json": [it.record for it in cybernetics],
        "armour_mods.json": [it.record for it in armour_mods],
        "weapon_mods.json": [it.record for it in weapon_mods],
        "conditions.json": conditions.build(bc, pairs, powers, report),
    }


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--out", type=Path, default=DEFAULT_OUT, help="папка ассетов PF (по умолчанию %(default)s)")
    ap.add_argument("--report", type=Path, default=DEFAULT_REPORT, help="файл отчёта (по умолчанию %(default)s)")
    ap.add_argument("--bc", type=Path, default=bcmod.DEFAULT_ASSETS,
                    help="ассеты Black Crusade — механика химии и статусов (по умолчанию %(default)s)")
    args = ap.parse_args(argv)

    report = Report()
    files = build(report, args.bc)

    args.out.mkdir(parents=True, exist_ok=True)
    for name, records in files.items():
        report.counts[name] = len(records)
        with open(args.out / name, "w", encoding="utf-8", newline="\n") as f:
            json.dump(records, f, ensure_ascii=False, indent=2)
            f.write("\n")

    text = report.render()
    args.report.write_text(text, encoding="utf-8", newline="\n")

    summary = text.split("\n\n## ")[0]
    out = sys.stdout
    if hasattr(out, "reconfigure"):
        out.reconfigure(encoding="utf-8")
    print(summary)
    print(f"Ассеты: {args.out}")
    print(f"Отчёт: {args.report}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
