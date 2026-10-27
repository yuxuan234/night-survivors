"""Night Survivors: the game rules, run with a fixed time step (1/60 s).

This file never imports pygame. Every number comes from data/game.json.
"""

import json
import math
import os
import random

STEP = 1.0 / 60.0
DATA_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "game.json")


def load_data(path=DATA_PATH):
    with open(path, encoding="utf-8") as handle:
        return json.load(handle)


def distance(ax, ay, bx, by):
    return math.hypot(bx - ax, by - ay)


class Enemy:
    def __init__(self, kind, x, y, stats):
        self.kind = kind
        self.x = x
        self.y = y
        self.hp = stats["max_hp"]
        self.speed = stats["speed"]
        self.damage = stats["damage"]
        self.radius = stats["hit_radius"]
        self.xp = stats["xp"]
        self.boss = bool(stats.get("boss", False))
        self.hero_hit_timer = 0.0
        self.dead = False


class Spark:
    def __init__(self, x, y, vx, vy, damage, radius, reach):
        self.x = x
        self.y = y
        self.vx = vx
        self.vy = vy
        self.damage = damage
        self.radius = radius
        self.reach = reach
        self.flown = 0.0


class Gem:
    def __init__(self, x, y, xp, radius):
        self.x = x
        self.y = y
        self.xp = xp
        self.radius = radius


class Popup:
    """A damage number that floats up and fades away."""

    def __init__(self, x, y, amount, life):
        self.x = x
        self.y = y
        self.amount = amount
        self.life = life
        self.total = life


class Flash:
    """The white burst left where an enemy died."""

    def __init__(self, x, y, life):
        self.x = x
        self.y = y
        self.life = life
        self.total = life


class GameState:
    """Holds everything that is true about one run of the game."""

    def __init__(self, data=None, rng=None):
        self.data = load_data() if data is None else data
        self.rng = random.Random() if rng is None else rng
        self.reset()

    def reset(self):
        hero = self.data["hero"]
        self.hero_x = 0.0
        self.hero_y = 0.0
        self.max_hp = hero["max_hp"]
        self.hp = float(hero["max_hp"])
        self.radius = hero["hit_radius"]

        self.enemies = []
        self.sparks = []
        self.gems = []
        self.popups = []
        self.flashes = []
        self.events = []
        self.shake = 0.0
        self.time = 0.0
        self.kills = 0
        self.status = "playing"

        self.level = 1
        self.xp = 0
        self.cards = []
        self.spawn_timer = 0.0
        self.boss_spawned = False
        self.weapons = {"spark_wand": 1}
        self.passives = {}
        self.weapon_timers = {name: 0.0 for name in self.weapons}
        self.blade_angle = 0.0
        self.blade_timers = []
        self.ring_flash = 0.0

        # Where the player wants to walk, as a screen offset from the hero.
        # main.py sets this every frame from the mouse pointer or a finger.
        self.walk_dx = 0.0
        self.walk_dy = 0.0

    def set_walk_direction(self, dx, dy):
        self.walk_dx = dx
        self.walk_dy = dy

    # --- feel: damage numbers, death flashes, shake, sounds ------------
    def take_events(self):
        """The sounds to play for this frame ("hit", "gem", "hurt", ...)."""
        events, self.events = self.events, []
        return events

    def _event(self, name):
        self.events.append(name)

    def _popup(self, x, y, amount):
        feel = self.data["feel"]
        self.popups.append(Popup(x, y - feel["popup_lift"], int(round(amount)),
                                 feel["popup_seconds"]))
        del self.popups[:max(0, len(self.popups) - feel["max_popups"])]

    def _flash(self, x, y):
        self.flashes.append(Flash(x, y, self.data["feel"]["flash_seconds"]))

    def _update_feel(self, dt):
        feel = self.data["feel"]
        self.shake = max(0.0, self.shake - dt)
        for popup in self.popups:
            popup.life -= dt
            popup.y -= feel["popup_rise"] * dt
        self.popups = [popup for popup in self.popups if popup.life > 0.0]
        for flash in self.flashes:
            flash.life -= dt
        self.flashes = [flash for flash in self.flashes if flash.life > 0.0]

    def update(self, dt=STEP):
        """Advance the game by one fixed step."""
        if self.status != "playing":
            return
        self.time += dt
        self._move_hero(dt)
        self._spawn(dt)
        self._move_enemies(dt)
        self._contact_damage(dt)
        self._update_weapons(dt)
        self._move_sparks(dt)
        self._move_gems(dt)
        self._remove_far_enemies()
        self._update_feel(dt)
        self.ring_flash = max(0.0, self.ring_flash - dt * 4.0)
        if self.hp <= 0:
            self.hp = 0.0
            self.status = "game_over"
            self._event("lose")
        elif self.time >= self.data["goal"]["survive_seconds"]:
            self.status = "victory"
            self._event("win")

    # --- what the hero has --------------------------------------------
    def passive_level(self, name):
        return self.passives.get(name, 0)

    def walk_speed(self):
        percent = self.data["passives"]["swift_boots"]["speed_percent"]
        bonus = 1.0 + percent / 100.0 * self.passive_level("swift_boots")
        return self.data["hero"]["speed"] * bonus

    def magnet_radius(self):
        gems = self.data["gems"]
        extra = self.data["passives"]["magnet"]["radius"]
        return gems["magnet_radius"] + extra * self.passive_level("magnet")

    def xp_needed(self):
        """XP for the next level: 5 at level 1, then 3 more each level."""
        xp = self.data["xp"]
        return xp["first_level"] + xp["extra_per_level"] * (self.level - 1)

    # --- hero ---------------------------------------------------------
    def _move_hero(self, dt):
        away = distance(0.0, 0.0, self.walk_dx, self.walk_dy)
        if away < self.data["walk"]["pointer_dead_zone"]:
            return
        step_length = self.walk_speed() * dt
        self.hero_x += self.walk_dx / away * step_length
        self.hero_y += self.walk_dy / away * step_length

    # --- enemies appearing --------------------------------------------
    def _current_wave(self):
        wave = self.data["spawn"]["waves"][0]
        for row in self.data["spawn"]["waves"]:
            if row["from_time"] <= self.time:
                wave = row
        return wave

    def _spawn(self, dt):
        rules = self.data["spawn"]
        self.spawn_timer += dt
        while self.spawn_timer >= rules["interval"]:
            self.spawn_timer -= rules["interval"]
            self._spawn_batch(self._current_wave())

    def _point_on_circle(self):
        rules = self.data["spawn"]
        angle = self.rng.uniform(0.0, math.tau)
        return (self.hero_x + math.cos(angle) * rules["circle_radius"],
                self.hero_y + math.sin(angle) * rules["circle_radius"])

    def _spawn_batch(self, wave):
        rules = self.data["spawn"]
        room = rules["max_alive"] - len(self.enemies)
        wanted = wave["min_alive"] - len(self.enemies)
        count = min(room, wanted, rules["max_per_second"])
        for _ in range(max(0, count)):
            x, y = self._point_on_circle()
            kind = self.rng.choice(wave["types"])
            self.enemies.append(Enemy(kind, x, y, self.data["enemies"][kind]))
        self._spawn_boss(wave)

    def _spawn_boss(self, wave):
        """The boss of a wave appears once, and only once, in the whole run."""
        kind = wave.get("boss")
        if kind is None or self.boss_spawned:
            return
        if len(self.enemies) >= self.data["spawn"]["max_alive"]:
            return
        x, y = self._point_on_circle()
        self.enemies.append(Enemy(kind, x, y, self.data["enemies"][kind]))
        self.boss_spawned = True

    def _move_enemies(self, dt):
        for enemy in self.enemies:
            gap = distance(self.hero_x, self.hero_y, enemy.x, enemy.y)
            touching = self.radius + enemy.radius
            if gap <= touching or gap == 0.0:
                continue
            step_length = enemy.speed * dt
            enemy.x += (self.hero_x - enemy.x) / gap * step_length
            enemy.y += (self.hero_y - enemy.y) / gap * step_length

    def _remove_far_enemies(self):
        """Normal enemies too far away are removed; the boss is pulled back."""
        rules = self.data["spawn"]
        keep = []
        for enemy in self.enemies:
            gap = distance(self.hero_x, self.hero_y, enemy.x, enemy.y)
            if enemy.boss:
                if gap > rules["boss_return_radius"]:
                    enemy.x, enemy.y = self._point_on_circle()
                keep.append(enemy)
            elif gap <= rules["despawn_radius"]:
                keep.append(enemy)
        self.enemies = keep

    # --- damage to the hero -------------------------------------------
    def _contact_damage(self, dt):
        """An enemy that touches the hero hurts him once every 0.5 s.

        hero_hit_timer counts down; an enemy is ready to hurt again at 0.
        """
        interval = self.data["contact"]["hero_hit_interval"]
        for enemy in self.enemies:
            touching = (distance(self.hero_x, self.hero_y, enemy.x, enemy.y)
                        <= self.radius + enemy.radius)
            if touching and enemy.hero_hit_timer <= 0.0:
                self.hp -= enemy.damage
                enemy.hero_hit_timer = interval
                self.shake = self.data["feel"]["shake_seconds"]
                self._event("hurt")
            else:
                enemy.hero_hit_timer -= dt

    # --- weapons -------------------------------------------------------
    def _update_weapons(self, dt):
        if "spark_wand" in self.weapons:
            self._update_spark_wand(dt)
        if "spin_blades" in self.weapons:
            self._update_spin_blades(dt)
        if "holy_ring" in self.weapons:
            self._update_holy_ring(dt)

    def _time_of(self, name, dt):
        """Return the time since this weapon last fired, and start a new count."""
        timer = self.weapon_timers.get(name, 0.0) + dt
        self.weapon_timers[name] = timer
        return timer

    def _spark_settings(self):
        cfg = self.data["weapons"]["spark_wand"]
        level = self.weapons["spark_wand"]
        extra = level - 1
        return (
            cfg["base_damage"] + cfg["damage_per_level"] * extra,
            max(cfg["min_interval"], cfg["base_interval"] - cfg["interval_per_level"] * extra),
            cfg["base_sparks"] + sum(1 for lv in cfg["extra_spark_at_levels"] if level >= lv),
        )

    def _update_spark_wand(self, dt):
        cfg = self.data["weapons"]["spark_wand"]
        damage, interval, shots = self._spark_settings()
        if self._time_of("spark_wand", dt) < interval or not self.enemies:
            return
        self.weapon_timers["spark_wand"] -= interval
        nearest = sorted(self.enemies,
                         key=lambda e: distance(self.hero_x, self.hero_y, e.x, e.y))
        for index in range(shots):
            enemy = nearest[index % len(nearest)]
            angle = math.atan2(enemy.y - self.hero_y, enemy.x - self.hero_x)
            if index >= len(nearest):
                angle += 0.25 * (index - len(nearest) + 1)
            speed = cfg["spark_speed"]
            self.sparks.append(Spark(
                self.hero_x, self.hero_y,
                math.cos(angle) * speed, math.sin(angle) * speed,
                damage, cfg["spark_radius"], cfg["spark_reach"]))

    def blade_count(self):
        cfg = self.data["weapons"]["spin_blades"]
        level = self.weapons.get("spin_blades", 0)
        return cfg["base_blades"] + sum(1 for lv in cfg["extra_blade_at_levels"]
                                        if level >= lv)

    def blade_positions(self):
        """Where the blades are, for the rules and for drawing."""
        if "spin_blades" not in self.weapons:
            return []
        cfg = self.data["weapons"]["spin_blades"]
        count = self.blade_count()
        places = []
        for index in range(count):
            angle = self.blade_angle + index * math.tau / count
            places.append((self.hero_x + math.cos(angle) * cfg["orbit_radius"],
                           self.hero_y + math.sin(angle) * cfg["orbit_radius"]))
        return places

    def _update_spin_blades(self, dt):
        cfg = self.data["weapons"]["spin_blades"]
        level = self.weapons["spin_blades"]
        damage = cfg["base_damage"] + cfg["damage_per_level"] * (level - 1)
        self.blade_angle = (self.blade_angle + dt * math.tau / cfg["turn_seconds"]) % math.tau
        count = self.blade_count()
        while len(self.blade_timers) < count:
            self.blade_timers.append(0.0)
        for index, (blade_x, blade_y) in enumerate(self.blade_positions()):
            self.blade_timers[index] -= dt
            if self.blade_timers[index] > 0.0:
                continue
            for enemy in self.enemies:
                if distance(blade_x, blade_y, enemy.x, enemy.y) <= cfg["blade_radius"] + enemy.radius:
                    self.blade_timers[index] = cfg["blade_hit_interval"]
                    self._hurt(enemy, damage)
                    break

    def holy_radius(self):
        cfg = self.data["weapons"]["holy_ring"]
        level = self.weapons.get("holy_ring", 0)
        return cfg["base_radius"] + cfg["radius_per_level"] * max(0, level - 1)

    def _update_holy_ring(self, dt):
        cfg = self.data["weapons"]["holy_ring"]
        level = self.weapons["holy_ring"]
        if self._time_of("holy_ring", dt) < cfg["interval"]:
            return
        self.weapon_timers["holy_ring"] -= cfg["interval"]
        damage = cfg["base_damage"] + cfg["damage_per_level"] * (level - 1)
        radius = self.holy_radius()
        self.ring_flash = 1.0
        for enemy in list(self.enemies):
            if distance(self.hero_x, self.hero_y, enemy.x, enemy.y) <= radius + enemy.radius:
                self._hurt(enemy, damage)

    def _move_sparks(self, dt):
        alive_sparks = []
        for spark in self.sparks:
            travel = math.hypot(spark.vx, spark.vy) * dt
            spark.x += spark.vx * dt
            spark.y += spark.vy * dt
            spark.flown += travel
            hit = None
            for enemy in self.enemies:
                if enemy.dead:
                    continue
                if distance(spark.x, spark.y, enemy.x, enemy.y) <= spark.radius + enemy.radius:
                    hit = enemy
                    break
            if hit is not None:
                self._hurt(hit, spark.damage)
            elif spark.flown < spark.reach:
                alive_sparks.append(spark)
        self.sparks = alive_sparks
        self.enemies = [e for e in self.enemies if not e.dead]

    def _hurt(self, enemy, damage):
        enemy.hp -= damage
        self._event("hit")
        self._popup(enemy.x, enemy.y, damage)
        if enemy.hp <= 0 and not enemy.dead:
            enemy.dead = True
            self.kills += 1
            self._flash(enemy.x, enemy.y)
            if enemy.xp > 0:
                self.gems.append(Gem(enemy.x, enemy.y, enemy.xp,
                                     self.data["gems"]["radius"]))

    # --- gems and levelling up ----------------------------------------
    def _move_gems(self, dt):
        cfg = self.data["gems"]
        magnet = self.magnet_radius()
        left = []
        for gem in self.gems:
            gap = distance(self.hero_x, self.hero_y, gem.x, gem.y)
            if gap <= self.radius + gem.radius:
                self._collect(gem)
                continue
            if gap <= magnet and gap > 0.0:
                step_length = cfg["fly_speed"] * dt
                gem.x += (self.hero_x - gem.x) / gap * step_length
                gem.y += (self.hero_y - gem.y) / gap * step_length
            left.append(gem)
        self.gems = left

    def _collect(self, gem):
        self.xp += gem.xp
        self._event("gem")
        self._check_level_up()

    def _check_level_up(self):
        if self.xp < self.xp_needed():
            return
        self.xp -= self.xp_needed()
        self.level += 1
        self.cards = self._make_cards()
        self.status = "level_up"
        self._event("level_up")

    def _card_pool(self):
        """Everything the hero may be offered right now."""
        limit = self.data["weapon_limit"]
        options = []
        for name, cfg in self.data["weapons"].items():
            owned = self.weapons.get(name)
            if owned is None:
                if len(self.weapons) < limit["max_weapons"]:
                    options.append({"kind": "weapon", "id": name, "level": 1,
                                    "name": cfg["name"], "text": cfg["line_new"]})
            elif owned < limit["max_level"]:
                options.append({"kind": "weapon", "id": name, "level": owned + 1,
                                "name": cfg["name"], "text": cfg["line"]})
        for name, cfg in self.data["passives"].items():
            owned = self.passive_level(name)
            if owned < limit["max_level"]:
                options.append({"kind": "passive", "id": name, "level": owned + 1,
                                "name": cfg["name"], "text": cfg["line"]})
        return options

    def _make_cards(self):
        wanted = self.data["level_up"]["cards"]
        pool = self._card_pool()
        cards = self.rng.sample(pool, min(wanted, len(pool)))
        heal = self.data["level_up"]["heal_hp"]
        while len(cards) < wanted:
            cards.append({"kind": "heal", "id": "heal", "level": None,
                          "name": "Heal", "text": "Heal %d HP" % heal})
        return cards

    def choose_card(self, index):
        """Called by main.py when a card is clicked or tapped."""
        if self.status != "level_up" or not 0 <= index < len(self.cards):
            return
        card = self.cards[index]
        if card["kind"] == "weapon":
            self.weapons[card["id"]] = card["level"]
            self.weapon_timers[card["id"]] = 0.0
            if card["id"] == "spin_blades":
                self.blade_timers = []
        elif card["kind"] == "passive":
            self.passives[card["id"]] = card["level"]
            if card["id"] == "big_heart":
                cfg = self.data["passives"]["big_heart"]
                self.max_hp += cfg["max_hp"]
                self.hp = min(self.hp + cfg["heal"], self.max_hp)
        else:
            self.hp = min(self.hp + self.data["level_up"]["heal_hp"], self.max_hp)
        self.cards = []
        self.status = "playing"
        self._check_level_up()

    def owned_line(self):
        """What the hero has, for the bottom of the screen."""
        parts = []
        for name, level in self.weapons.items():
            parts.append("%s %d" % (self.data["weapons"][name]["short"], level))
        for name, level in self.passives.items():
            parts.append("%s %d" % (self.data["passives"][name]["short"], level))
        return "  ".join(parts)
