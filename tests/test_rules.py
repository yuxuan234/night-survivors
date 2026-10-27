"""Tests for rules.py only. The numbers come from data/game.json."""

import copy
import math
import os
import random
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import rules

BASE = rules.load_data()


def new_state(changes=None, seed=1):
    data = copy.deepcopy(BASE)
    for key, value in (changes or {}).items():
        part = data
        pieces = key.split(".")
        for piece in pieces[:-1]:
            part = part[piece]
        part[pieces[-1]] = value
    state = rules.GameState(data, random.Random(seed))
    no_more_waves(state)
    return state


def no_more_waves(state):
    """Stop new bats appearing, so a test only sees what it put there."""
    state.data["spawn"]["waves"] = [
        {"from_time": 9999.0, "types": ["bat"], "min_alive": 0}]


def no_level_up(state):
    """Keep the hero from levelling, so tests see only what they put there."""
    state.data["xp"]["first_level"] = 10 ** 9


def wand_is_slow(state):
    """Keep the wand from shooting, so batches are not shot down."""
    state.data["weapons"]["spark_wand"]["base_interval"] = 9999.0


def stationary_bat(state, x, y, hp=None):
    stats = dict(state.data["enemies"]["bat"])
    if hp is not None:
        stats["max_hp"] = hp
    bat = rules.Enemy("bat", x, y, stats)
    bat.speed = 0.0
    return bat


def run(state, seconds):
    for _ in range(int(round(seconds / rules.STEP))):
        state.update()


class Spawning(unittest.TestCase):
    def new_run(self, seed=1):
        """A real run, but the wand waits so batches are not shot down."""
        state = rules.GameState(copy.deepcopy(BASE), random.Random(seed))
        wand_is_slow(state)
        no_level_up(state)
        return state

    def test_one_second_adds_at_most_the_per_second_cap(self):
        state = self.new_run()
        run(state, 1.05)
        cap = BASE["spawn"]["max_per_second"]
        minimum = BASE["spawn"]["waves"][0]["min_alive"]
        self.assertEqual(len(state.enemies), min(cap, minimum))

    def test_grows_to_the_wave_minimum(self):
        state = self.new_run()
        minimum = BASE["spawn"]["waves"][0]["min_alive"]
        run(state, 2.0 + minimum / BASE["spawn"]["max_per_second"])
        self.assertEqual(len(state.enemies), minimum)

    def test_appears_on_the_circle_around_the_hero(self):
        state = self.new_run()
        state.hero_x, state.hero_y = 500.0, -300.0
        run(state, 1.05)
        radius = BASE["spawn"]["circle_radius"]
        self.assertTrue(state.enemies)
        for enemy in state.enemies:
            gap = math.hypot(enemy.x - state.hero_x, enemy.y - state.hero_y)
            # Spawned on the circle, then it walked in for a fraction of a
            # second (the batch happens at 1 s, we ran until 1.05 s).
            self.assertLessEqual(gap, radius)
            self.assertGreaterEqual(gap, radius - 0.1 * enemy.speed)

    def test_never_more_than_the_max_alive(self):
        state = new_state({"hero.max_hp": 10 ** 9})
        wand_is_slow(state)
        no_level_up(state)
        state.data["spawn"]["waves"] = [
            {"from_time": 0, "types": ["bat"], "min_alive": 500}]
        run(state, 20.0)
        self.assertEqual(len(state.enemies), BASE["spawn"]["max_alive"])

    def test_far_enemies_are_removed(self):
        state = new_state()
        bat = stationary_bat(state, BASE["spawn"]["despawn_radius"] + 50.0, 0.0)
        state.enemies.append(bat)
        run(state, 0.05)
        self.assertNotIn(bat, state.enemies)

    def test_bats_walk_to_the_hero(self):
        state = new_state()
        bat = rules.Enemy("bat", 200.0, 0.0, state.data["enemies"]["bat"])
        state.enemies.append(bat)
        run(state, 0.5)
        self.assertLess(bat.x, 200.0)


class Hero(unittest.TestCase):
    def test_walks_toward_the_pointer_at_the_data_speed(self):
        state = new_state()
        state.set_walk_direction(0.0, -100.0)
        run(state, 1.0)
        self.assertAlmostEqual(state.hero_y, -BASE["hero"]["speed"], places=2)

    def test_a_pointer_inside_the_dead_zone_does_not_move_the_hero(self):
        state = new_state()
        zone = BASE["walk"]["pointer_dead_zone"]
        state.set_walk_direction(zone * 0.5, 0.0)
        run(state, 1.0)
        self.assertEqual((state.hero_x, state.hero_y), (0.0, 0.0))

    def test_the_map_has_no_edges(self):
        state = new_state()
        state.set_walk_direction(100.0, 100.0)
        run(state, 5.0)
        expected = BASE["hero"]["speed"] * 5.0 / math.sqrt(2.0)
        self.assertAlmostEqual(state.hero_x, expected, places=1)
        self.assertAlmostEqual(state.hero_y, expected, places=1)


class Damage(unittest.TestCase):
    def test_touching_hurts_once_per_interval(self):
        state = new_state()
        no_level_up(state)
        wand_is_slow(state)
        state.enemies = [stationary_bat(state, 20.0, 0.0)]
        run(state, 1.0)
        hits = 1.0 / BASE["contact"]["hero_hit_interval"]
        expected = BASE["enemies"]["bat"]["damage"] * hits
        self.assertAlmostEqual(state.hp, BASE["hero"]["max_hp"] - expected, places=4)

    def test_the_json_number_decides_the_damage(self):
        damage = BASE["enemies"]["bat"]["damage"] + 7
        state = new_state({"enemies.bat.damage": damage})
        no_level_up(state)
        wand_is_slow(state)
        state.enemies = [stationary_bat(state, 20.0, 0.0)]
        run(state, 0.4)
        self.assertAlmostEqual(state.hp, BASE["hero"]["max_hp"] - damage, places=4)

    def test_a_hit_needs_touching(self):
        state = new_state()
        no_level_up(state)
        state.enemies = [stationary_bat(state, 40.0, 0.0)]
        run(state, 1.0)
        self.assertEqual(state.hp, BASE["hero"]["max_hp"])

    def test_zero_hp_ends_the_game_and_a_restart_clears_it(self):
        state = new_state()
        no_level_up(state)
        wand_is_slow(state)
        for row in range(4):
            for column in range(5):
                state.enemies.append(
                    stationary_bat(state, float(column) - 2.0, float(row) - 2.0))
        run(state, 5.0)
        self.assertEqual(state.status, "game_over")
        self.assertEqual(state.hp, 0.0)
        state.reset()
        self.assertEqual((state.status, state.hp), ("playing", state.max_hp))
        self.assertEqual((state.enemies, state.gems, state.sparks), ([], [], []))
        self.assertEqual(state.time, 0.0)
        self.assertEqual(state.level, 1)
        self.assertEqual(state.weapons, {"spark_wand": 1})
        self.assertEqual(state.passives, {})


class SparkWand(unittest.TestCase):
    def test_shoots_the_nearest_enemy_and_kills_it(self):
        state = new_state()
        no_level_up(state)
        near = stationary_bat(state, 60.0, 0.0)
        far = stationary_bat(state, 90.0, 0.0)
        state.enemies = [far, near]
        interval = state.data["weapons"]["spark_wand"]["base_interval"]
        run(state, interval + 0.05)
        self.assertEqual(len(state.sparks), 1)
        run(state, 0.3)
        self.assertEqual(state.kills, 1)
        self.assertTrue(near.dead)
        self.assertIn(far, state.enemies)

    def test_fires_once_per_interval_and_each_spark_hits(self):
        state = new_state()
        no_level_up(state)
        bat = stationary_bat(state, 100.0, 0.0, hp=10000)
        state.enemies = [bat]
        cfg = state.data["weapons"]["spark_wand"]
        shots = 3
        # A spark needs 100 / 400 = 0.25 s to reach the bat, so all three land.
        run(state, cfg["base_interval"] * shots + 0.4)
        self.assertEqual(bat.hp, 10000 - shots * cfg["base_damage"])

    def test_higher_levels_use_the_numbers_from_the_json(self):
        state = new_state()
        cfg = state.data["weapons"]["spark_wand"]
        state.weapons["spark_wand"] = 5
        damage, interval, shots = state._spark_settings()
        self.assertEqual(damage, cfg["base_damage"] + cfg["damage_per_level"] * 4)
        self.assertAlmostEqual(interval,
                               cfg["base_interval"] - cfg["interval_per_level"] * 4)
        self.assertEqual(shots, cfg["base_sparks"] + len(cfg["extra_spark_at_levels"]))

    def test_no_sparks_without_an_enemy(self):
        state = new_state()
        run(state, 3.0)
        self.assertEqual(state.sparks, [])

    def test_a_spark_that_hits_hurts_only_once(self):
        state = new_state()
        no_level_up(state)
        bat = stationary_bat(state, 100.0, 0.0, hp=BASE["enemies"]["bat"]["max_hp"])
        state.enemies = [bat]
        interval = state.data["weapons"]["spark_wand"]["base_interval"]
        run(state, interval + 0.4)
        self.assertEqual(state.kills, 1)
        self.assertEqual(state.sparks, [])


class Gems(unittest.TestCase):
    def test_a_dead_enemy_drops_a_gem_worth_its_xp(self):
        state = new_state()
        no_level_up(state)
        # Far enough that the gem is not collected during the test.
        bat = stationary_bat(state, 300.0, 0.0)
        state.enemies = [bat]
        run(state, BASE["weapons"]["spark_wand"]["base_interval"] + 0.9)
        self.assertEqual(state.kills, 1)
        self.assertEqual(len(state.gems), 1)
        self.assertEqual(state.gems[0].xp, BASE["enemies"]["bat"]["xp"])
        self.assertAlmostEqual(state.gems[0].x, 300.0, places=1)

    def test_a_gem_outside_the_magnet_radius_stays_where_it_is(self):
        state = new_state()
        magnet = BASE["gems"]["magnet_radius"]
        gem = rules.Gem(magnet + 40.0, 0.0, 1, BASE["gems"]["radius"])
        state.gems = [gem]
        run(state, 1.0)
        self.assertAlmostEqual(gem.x, magnet + 40.0, places=6)
        self.assertEqual(state.xp, 0)

    def test_a_gem_inside_the_magnet_radius_flies_in_and_is_taken(self):
        state = new_state()
        magnet = BASE["gems"]["magnet_radius"]
        gem = rules.Gem(magnet - 10.0, 0.0, BASE["enemies"]["bat"]["xp"],
                        BASE["gems"]["radius"])
        state.gems = [gem]
        run(state, 0.5)
        self.assertEqual(state.gems, [])
        self.assertEqual(state.xp, BASE["enemies"]["bat"]["xp"])

    def test_the_magnet_item_widens_the_radius_and_moves_faster(self):
        state = new_state()
        magnet = BASE["gems"]["magnet_radius"]
        extra = BASE["passives"]["magnet"]["radius"]
        state.passives["magnet"] = 1
        self.assertEqual(state.magnet_radius(), magnet + extra)
        gem = rules.Gem(magnet + extra - 5.0, 0.0, 1, BASE["gems"]["radius"])
        state.gems = [gem]
        run(state, 0.5)
        self.assertEqual(state.gems, [])

    def test_the_magnet_item_also_helps_the_hero_walk_faster_with_boots(self):
        state = new_state()
        percent = BASE["passives"]["swift_boots"]["speed_percent"]
        state.passives["swift_boots"] = 2
        expected = BASE["hero"]["speed"] * (1.0 + 2 * percent / 100.0)
        self.assertAlmostEqual(state.walk_speed(), expected, places=6)


class LevelUp(unittest.TestCase):
    def test_xp_for_the_next_level_follows_the_json(self):
        state = new_state()
        first = BASE["xp"]["first_level"]
        step = BASE["xp"]["extra_per_level"]
        for level, needed in ((1, first), (2, first + step), (5, first + 4 * step)):
            state.level = level
            self.assertEqual(state.xp_needed(), needed)

    def test_enough_xp_pauses_the_game_with_three_cards(self):
        state = new_state()
        state.gems = [rules.Gem(10.0, 0.0, 1, BASE["gems"]["radius"])
                      for _ in range(BASE["xp"]["first_level"])]
        run(state, 0.5)
        self.assertEqual(state.status, "level_up")
        self.assertEqual(len(state.cards), BASE["level_up"]["cards"])
        frozen = (state.time, list(state.enemies))
        run(state, 1.0)
        self.assertEqual((state.time, state.enemies), frozen)

    def test_a_card_shows_a_name_a_new_level_and_one_line(self):
        state = new_state()
        for card in state._make_cards():
            self.assertTrue(card["name"])
            self.assertTrue(card["text"])
            self.assertIn(card["kind"], ("weapon", "passive", "heal"))
            if card["kind"] != "heal":
                self.assertIsInstance(card["level"], int)

    def test_choosing_a_weapon_adds_it_and_play_resumes(self):
        state = new_state()
        state.status = "level_up"
        state.cards = [{"kind": "weapon", "id": "spin_blades", "level": 1,
                        "name": "Spin Blades", "text": "2 blades, 8 damage"}]
        state.choose_card(0)
        self.assertEqual(state.weapons["spin_blades"], 1)
        self.assertEqual(state.status, "playing")
        self.assertEqual(state.cards, [])

    def test_a_fourth_weapon_is_never_offered(self):
        state = new_state()
        state.weapons = {name: 1 for name in BASE["weapons"]}
        self.assertEqual(len(state.weapons), BASE["weapon_limit"]["max_weapons"])
        for card in state._card_pool():
            self.assertFalse(card["kind"] == "weapon" and card["level"] == 1)

    def test_nothing_is_off_that_is_already_at_the_top_level(self):
        state = new_state()
        limit = BASE["weapon_limit"]["max_level"]
        for name in BASE["weapons"]:
            state.weapons[name] = limit
        for name in BASE["passives"]:
            state.passives[name] = limit
        self.assertEqual(state._card_pool(), [])
        cards = state._make_cards()
        self.assertEqual(len(cards), BASE["level_up"]["cards"])
        self.assertTrue(all(card["kind"] == "heal" for card in cards))

    def test_a_heal_card_gives_hp_but_never_more_than_the_max(self):
        state = new_state()
        state.hp = 10.0
        state.status = "level_up"
        state.cards = [{"kind": "heal", "id": "heal", "level": None,
                        "name": "Heal", "text": "Heal 30 HP"}]
        state.choose_card(0)
        self.assertEqual(state.hp, 10.0 + BASE["level_up"]["heal_hp"])
        state.hp = 99.0
        state.status = "level_up"
        state.cards = [{"kind": "heal", "id": "heal", "level": None,
                        "name": "Heal", "text": "Heal 30 HP"}]
        state.choose_card(0)
        self.assertEqual(state.hp, state.max_hp)

    def test_two_level_ups_in_a_row_are_offered_one_after_the_other(self):
        state = new_state()
        first = BASE["xp"]["first_level"]
        step = BASE["xp"]["extra_per_level"]
        # Enough for level 2 (5) and level 3 (8) with one left over.
        state.xp = first + (first + step) + 1
        state.status = "level_up"
        state.cards = [{"kind": "passive", "id": "magnet", "level": 1,
                        "name": "Magnet", "text": "+30 px"}]
        state.choose_card(0)
        self.assertEqual(state.level, 2)
        self.assertEqual(state.status, "level_up")
        state.choose_card(0)
        self.assertEqual(state.level, 3)
        self.assertEqual(state.status, "level_up")
        state.choose_card(0)
        self.assertEqual(state.xp, 1)
        self.assertEqual(state.status, "playing")

    def test_big_heart_adds_max_hp_and_heals(self):
        state = new_state()
        cfg = BASE["passives"]["big_heart"]
        state.hp = 50.0
        state.status = "level_up"
        state.cards = [{"kind": "passive", "id": "big_heart", "level": 1,
                        "name": "Big Heart", "text": cfg["line"]}]
        state.choose_card(0)
        self.assertEqual(state.max_hp, BASE["hero"]["max_hp"] + cfg["max_hp"])
        self.assertEqual(state.hp, 50.0 + cfg["heal"])

    def test_the_bottom_line_shows_what_you_have(self):
        state = new_state()
        state.weapons = {"spark_wand": 2, "holy_ring": 1}
        state.passives = {"swift_boots": 1}
        self.assertEqual(state.owned_line(), "Spark 2  Ring 1  Boots 1")


class SpinBlades(unittest.TestCase):
    def test_blades_sit_on_the_orbit_and_turn(self):
        state = new_state()
        cfg = BASE["weapons"]["spin_blades"]
        state.weapons["spin_blades"] = 1
        places = state.blade_positions()
        self.assertEqual(len(places), cfg["base_blades"])
        for x, y in places:
            self.assertAlmostEqual(math.hypot(x, y), cfg["orbit_radius"], places=6)
        before = state.blade_positions()
        run(state, 0.5)
        self.assertNotEqual(before, state.blade_positions())

    def test_more_levels_give_more_blades(self):
        state = new_state()
        for level, blades in ((1, 2), (2, 3), (3, 3), (4, 4), (5, 4)):
            state.weapons["spin_blades"] = level
            self.assertEqual(state.blade_count(), blades)

    def test_a_blade_hurts_an_enemy_it_passes(self):
        state = new_state()
        no_level_up(state)
        wand_is_slow(state)
        cfg = BASE["weapons"]["spin_blades"]
        state.weapons["spin_blades"] = 1
        state.weapon_timers["spin_blades"] = 0.0
        bat = stationary_bat(state, cfg["orbit_radius"], 0.0, hp=10000)
        state.enemies = [bat]
        run(state, 2.0)
        lost = 10000 - bat.hp
        self.assertGreater(lost, 0)
        self.assertEqual(lost % cfg["base_damage"], 0)

    def test_a_blade_never_hurts_twice_inside_its_interval(self):
        state = new_state()
        no_level_up(state)
        wand_is_slow(state)
        cfg = BASE["weapons"]["spin_blades"]
        state.weapons["spin_blades"] = 1
        bat = stationary_bat(state, cfg["orbit_radius"], 0.0, hp=10 ** 6)
        state.enemies = [bat]
        run(state, cfg["turn_seconds"] * 4)
        hits = (10 ** 6 - bat.hp) / cfg["base_damage"]
        # 2 blades, 4 turns each: at most one hit per blade per hit interval.
        limit = 2 * cfg["turn_seconds"] * 4 / cfg["blade_hit_interval"]
        self.assertLessEqual(hits, limit)


class HolyRing(unittest.TestCase):
    def test_it_hurts_every_enemy_inside_and_nobody_outside(self):
        state = new_state()
        no_level_up(state)
        wand_is_slow(state)
        cfg = BASE["weapons"]["holy_ring"]
        state.weapons["holy_ring"] = 1
        state.weapon_timers["holy_ring"] = 0.0
        inside = [stationary_bat(state, 20.0, 0.0, hp=10000),
                  stationary_bat(state, 0.0, 30.0, hp=10000)]
        outside = stationary_bat(state, cfg["base_radius"] + 60.0, 0.0, hp=10000)
        state.enemies = inside + [outside]
        run(state, cfg["interval"] + 0.02)
        for bat in inside:
            self.assertEqual(bat.hp, 10000 - cfg["base_damage"])
        self.assertEqual(outside.hp, 10000)

    def test_a_higher_level_is_bigger_and_harder(self):
        state = new_state()
        cfg = BASE["weapons"]["holy_ring"]
        state.weapons["holy_ring"] = 3
        self.assertEqual(state.holy_radius(),
                         cfg["base_radius"] + 2 * cfg["radius_per_level"])


class Waves(unittest.TestCase):
    """The wave table from GAME.md, checked against the numbers in the JSON."""

    # From | Enemy types             | Minimum alive
    TABLE = {
        0: (["bat"], 12), 15: (["bat"], 20), 30: (["bat", "slime"], 28),
        45: (["slime", "ghost"], 36), 60: (["bat", "ghost"], 45),
        75: (["bat", "slime", "ghost"], 55), 90: (["bat", "slime"], 55),
        105: (["bat"], 75), 119: (["bat"], 75),
    }

    def running(self, seed=5):
        """A real run with the whole wave table, where the hero cannot die."""
        state = rules.GameState(copy.deepcopy(BASE), random.Random(seed))
        no_level_up(state)
        wand_is_slow(state)
        state.data["hero"]["max_hp"] = 10 ** 6
        state.max_hp = 10 ** 6
        state.hp = 10 ** 6
        return state

    def test_the_right_row_is_used_at_every_time(self):
        state = rules.GameState(copy.deepcopy(BASE), random.Random(1))
        for moment, (types, minimum) in self.TABLE.items():
            state.time = moment
            wave = state._current_wave()
            self.assertEqual(wave["types"], types, "types at %d s" % moment)
            self.assertEqual(wave["min_alive"], minimum, "minimum at %d s" % moment)

    def test_only_the_ninety_second_row_has_a_boss(self):
        data = rules.load_data()
        rows = [row for row in data["spawn"]["waves"] if "boss" in row]
        self.assertEqual([row["from_time"] for row in rows], [90])
        self.assertEqual(rows[0]["boss"], "demon")

    def test_only_bats_at_first_and_every_kind_later(self):
        state = self.running()
        run(state, 20.0)
        self.assertEqual({enemy.kind for enemy in state.enemies}, {"bat"})
        run(state, 40.0)
        self.assertEqual({enemy.kind for enemy in state.enemies},
                         {"bat", "slime", "ghost"})

    def test_the_alive_count_follows_the_minimum_for_the_time(self):
        state = self.running()
        for moment, (_, minimum) in ((15, self.TABLE[15]), (45, self.TABLE[45]),
                                     (105, self.TABLE[105])):
            state.time = moment - 0.5
            # Six seconds is enough for the eight-per-second top-up to catch up.
            run(state, 6.0)
            self.assertGreaterEqual(len(state.enemies), minimum,
                                    "minimum alive at %d s" % moment)
            self.assertLessEqual(len(state.enemies), minimum + 8,
                                 "no flood past the minimum at %d s" % moment)

    def test_the_boss_appears_once(self):
        state = self.running()
        state.time = 89.5
        run(state, 3.0)
        demons = [e for e in state.enemies if e.kind == "demon"]
        self.assertEqual(len(demons), 1)
        self.assertTrue(demons[0].boss)
        state.enemies = [e for e in state.enemies if e is not demons[0]]
        run(state, 5.0)
        self.assertEqual([e for e in state.enemies if e.kind == "demon"], [])
        self.assertTrue(state.boss_spawned)

    def test_the_boss_is_never_removed_but_is_pulled_back(self):
        state = new_state()
        demon = rules.Enemy("demon", 900.0, 0.0, state.data["enemies"]["demon"])
        demon.speed = 0.0
        state.enemies = [demon]
        run(state, 0.05)
        self.assertIn(demon, state.enemies)
        gap = math.hypot(demon.x - state.hero_x, demon.y - state.hero_y)
        self.assertAlmostEqual(gap, BASE["spawn"]["circle_radius"], places=6)

    def test_the_boss_numbers_come_from_the_json(self):
        state = new_state()
        stats = BASE["enemies"]["demon"]
        demon = rules.Enemy("demon", 100.0, 0.0, stats)
        self.assertEqual((demon.hp, demon.speed, demon.damage),
                         (stats["max_hp"], stats["speed"], stats["damage"]))
        self.assertEqual(stats["xp"], 0)
        self.assertGreater(BASE["enemies"]["ghost"]["speed"], BASE["hero"]["speed"])

    def test_a_dead_boss_drops_no_gem(self):
        state = new_state()
        no_level_up(state)
        demon = rules.Enemy("demon", 100.0, 0.0, state.data["enemies"]["demon"])
        demon.speed = 0.0
        state.enemies = [demon]
        state._hurt(demon, 10 ** 6)
        state.enemies = [e for e in state.enemies if not e.dead]
        self.assertEqual(state.kills, 1)
        self.assertEqual(state.gems, [])

    def test_a_full_two_minute_run_is_survivable_and_ends_in_victory(self):
        state = rules.GameState(copy.deepcopy(BASE), random.Random(7))
        no_level_up(state)
        state.data["hero"]["max_hp"] = 10 ** 6
        state.max_hp = 10 ** 6
        state.hp = 10 ** 6
        state.set_walk_direction(0.0, -100.0)
        run(state, BASE["goal"]["survive_seconds"] + 0.1)
        self.assertEqual(state.status, "victory")
        self.assertLessEqual(len(state.enemies), BASE["spawn"]["max_alive"])
        self.assertGreater(state.kills, 0)
        self.assertEqual(round(state.time), BASE["goal"]["survive_seconds"])


class Victory(unittest.TestCase):
    def test_the_goal_time_in_the_json_ends_the_run(self):
        state = new_state({"goal.survive_seconds": 2})
        run(state, 2.05)
        self.assertEqual(state.status, "victory")

    def test_dying_first_still_gives_game_over(self):
        state = new_state({"goal.survive_seconds": 5})
        no_level_up(state)
        for row in range(4):
            for column in range(5):
                state.enemies.append(
                    stationary_bat(state, float(column) - 2.0, float(row) - 2.0))
        run(state, 5.0)
        self.assertEqual(state.status, "game_over")

    def test_the_game_freezes_at_the_end(self):
        state = new_state({"goal.survive_seconds": 2})
        run(state, 2.05)
        frozen = (state.time, state.enemies, state.sparks)
        run(state, 3.0)
        self.assertEqual((state.time, state.enemies, state.sparks), frozen)

    def test_a_restart_clears_the_boss_and_the_clock(self):
        state = rules.GameState(copy.deepcopy(BASE), random.Random(5))
        state.boss_spawned = True
        state.time = 95.0
        state.reset()
        self.assertFalse(state.boss_spawned)
        self.assertEqual(state.time, 0.0)
        self.assertEqual(state.enemies, [])


class Feel(unittest.TestCase):
    """Damage numbers, death flashes, the shake and the sound requests."""

    def target(self, hp=10 ** 6, x=100.0):
        """A run with one bat that cannot die and cannot walk away.

        The spark needs about a third of a second to cross the 100 px, so the
        first hit lands at 1.1 s.
        """
        state = new_state()
        no_level_up(state)
        state.enemies.append(stationary_bat(state, x, 0.0, hp=hp))
        return state

    def test_a_hit_shows_a_number_and_asks_for_the_hit_sound(self):
        state = self.target()
        run(state, 1.1)
        self.assertIn("hit", state.take_events())
        damage = state.data["weapons"]["spark_wand"]["base_damage"]
        self.assertEqual([p.amount for p in state.popups], [damage])

    def test_the_numbers_float_up_and_then_disappear(self):
        state = self.target()
        run(state, 1.1)
        number = state.popups[0]
        start = number.y
        run(state, 0.2)
        self.assertLess(number.y, start)
        run(state, state.data["feel"]["popup_seconds"])
        self.assertNotIn(number, state.popups)

    def test_a_dead_enemy_leaves_a_flash_that_fades(self):
        state = self.target(hp=1)
        run(state, 1.1)
        self.assertEqual(len(state.flashes), 1)
        run(state, state.data["feel"]["flash_seconds"])
        self.assertEqual(state.flashes, [])

    def test_touching_the_hero_shakes_and_asks_for_the_hurt_sound(self):
        state = self.target(x=1.0)
        run(state, 0.1)
        self.assertGreater(state.shake, 0.0)
        self.assertIn("hurt", state.take_events())
        run(state, state.data["feel"]["shake_seconds"])
        self.assertEqual(state.shake, 0.0)

    def test_a_gem_a_level_up_and_the_end_each_ask_for_a_sound(self):
        state = self.target(hp=10 ** 6)
        radius = state.data["gems"]["radius"]
        state.gems.append(rules.Gem(0.0, 0.0, 1, radius))
        run(state, rules.STEP)
        self.assertIn("gem", state.take_events())

        state = new_state()
        state.xp = state.xp_needed() - 1
        state.gems.append(rules.Gem(0.0, 0.0, 1, radius))
        run(state, rules.STEP)
        self.assertIn("level_up", state.take_events())

        state = new_state({"goal.survive_seconds": 1})
        run(state, 1.05)
        self.assertIn("win", state.take_events())

    def test_the_end_sound_is_only_asked_for_once(self):
        state = new_state({"goal.survive_seconds": 1})
        run(state, 1.05)
        state.take_events()
        run(state, 2.0)
        self.assertEqual(state.take_events(), [])

    def test_take_events_clears_the_list(self):
        state = self.target()
        run(state, 1.1)
        self.assertNotEqual(state.events, [])
        state.take_events()
        self.assertEqual(state.events, [])

    def test_there_are_never_more_numbers_than_the_limit_allows(self):
        state = new_state()
        no_level_up(state)
        # A spark every frame: far more numbers than the limit allows.
        cfg = state.data["weapons"]["spark_wand"]
        cfg["base_interval"] = cfg["min_interval"] = 0.01
        for row in range(10):
            for column in range(6):
                state.enemies.append(stationary_bat(
                    state, float(column) * 20.0 - 60.0, float(row) * 20.0 - 90.0,
                    hp=10 ** 6))
        run(state, 2.0)
        self.assertEqual(len(state.enemies), 60)
        self.assertEqual(len(state.popups), state.data["feel"]["max_popups"])

    def test_a_restart_clears_the_numbers_the_flashes_and_the_shake(self):
        state = self.target()
        run(state, 1.1)
        state.reset()
        self.assertEqual((state.popups, state.flashes, state.events), ([], [], []))
        self.assertEqual(state.shake, 0.0)


if __name__ == "__main__":
    unittest.main()
