"""Scratch smoke test (not part of the game): run main.py headless while
posting fake mouse moves, clicks and finger touches, and save real frames so
the pictures can be looked at. Fast-forwards the clock so the boss and the
2:00 win are reached in a few seconds instead of two minutes."""

import asyncio
import os

os.environ["SDL_VIDEODRIVER"] = "dummy"
os.environ["SDL_AUDIODRIVER"] = "dummy"

import pygame

import main
import rules

holder = {"state": None, "frame": 0, "log": [], "seen": {}}
real_update = rules.GameState.update
real_load_sounds = main.load_sounds
played = []


def patched_update(self, dt=rules.STEP):
    if holder["state"] is None:
        holder["state"] = self
    for enemy in self.enemies:
        holder["seen"].setdefault("kinds", set()).add(enemy.kind)
    real_update(self, dt)
    seen = holder["seen"]
    seen["popups_max"] = max(seen.get("popups_max", 0), len(self.popups))
    seen["flashes_max"] = max(seen.get("flashes_max", 0), len(self.flashes))
    if self.shake > 0.0:
        seen["shake_seen"] = True
        offset = main.camera_shake(self, self.data["feel"])
        seen["shake_peak"] = max(seen.get("shake_peak", 0), *(abs(c) for c in offset))


class Spy:
    """Wraps a loaded sound so this script can count which ones main.py plays."""

    def __init__(self, sound, name):
        self.sound = sound
        self.name = name

    def play(self, *args, **kwargs):
        played.append(self.name)
        return self.sound.play(*args, **kwargs)

    def __getattr__(self, item):
        return getattr(self.sound, item)


def patched_load_sounds(data):
    sounds = real_load_sounds(data)
    holder["seen"]["sounds_loaded"] = sorted(sounds)
    return {name: Spy(sound, name) for name, sound in sounds.items()}


main.load_sounds = patched_load_sounds
rules.GameState.update = patched_update


def mouse(pos):
    return pygame.event.Event(pygame.MOUSEMOTION, pos=pos, rel=(1, 1))


def key(code):
    return pygame.event.Event(pygame.KEYDOWN, key=code, mod=0)


def click(pos):
    return pygame.event.Event(pygame.MOUSEBUTTONDOWN, pos=pos, button=1, rel=(0, 0),
                              num_clicks=1, button_is_down=True)


def finger(kind, x, y, pressure):
    return pygame.event.Event(kind, finger_id=0, x=x, y=y, dx=0.0, dy=0.0,
                              pressure=pressure)


def shoot(name):
    pygame.image.save(pygame.display.get_surface(), "/tmp/%s.png" % name)


def near(state, kind, dx, dy):
    """Put one enemy of a kind close to the hero, for the picture."""
    stats = state.data["enemies"][kind]
    bat = rules.Enemy(kind, state.hero_x + dx, state.hero_y + dy, stats)
    bat.speed = 0.0
    state.enemies.append(bat)
    return bat


def fast_forward(state):
    """Jump to 1:29 so the boss row of the wave table is next, and let the
    hero live long enough to reach the win."""
    state.time = 89.0
    state.spawn_timer = 0.9
    state.data["hero"]["max_hp"] = 10 ** 6
    state.max_hp = 10 ** 6
    state.hp = 10 ** 6


def restore_normal_numbers(state):
    """Undo this script's tweaks so the restart check uses the real numbers."""
    original = rules.load_data()
    state.max_hp = state.data["hero"]["max_hp"] = original["hero"]["max_hp"]
    state.data["goal"] = original["goal"]


def fake_event_get():
    holder["frame"] += 1
    frame = holder["frame"]
    state = holder["state"]

    if frame % 120 == 0 and state is not None:
        holder["log"].append(
            "frame %3d  t=%5.1fs  Lv %d  hp=%8.1f  alive=%3d kinds=%-22s kills=%3d "
            "status=%-9s numbers=%2d flashes=%2d shake=%4.2f %s"
            % (frame, state.time, state.level, state.hp, len(state.enemies),
               ",".join(sorted({e.kind for e in state.enemies})), state.kills,
               state.status, len(state.popups), len(state.flashes), state.shake,
               state.owned_line()))

    # --- ordinary input, as in the earlier steps ---
    if frame == 5:
        return [mouse((300, 150))]
    if frame == 20:
        return [key(pygame.K_p)]
    if frame == 25:
        return [key(pygame.K_p)]
    if frame == 30:
        return [finger(pygame.FINGERDOWN, 0.2, 0.9, 1.0)]
    if frame == 35:
        return [finger(pygame.FINGERMOTION, 0.9, 0.4, 1.0)]
    if frame == 45:
        return [finger(pygame.FINGERUP, 0.9, 0.4, 0.0)]
    if frame == 50:
        return [mouse((120, 600))]

    # --- level-up cards ---
    if frame == 60 and state is not None:
        state.xp = state.xp_needed() - 1
        state.gems.append(rules.Gem(20.0, 0.0, 1, state.data["gems"]["radius"]))
    if frame == 66 and state is not None:
        holder["seen"]["cards"] = (state.status, len(state.cards))
        return []
    if frame == 70:
        return [click((100, 200))]
    if frame == 72 and state is not None:
        holder["seen"]["after_card"] = (state.status, state.level)

    # --- the wave table, the boss and every picture on screen ---
    if frame == 80 and state is not None:
        fast_forward(state)
        near(state, "slime", -120.0, 60.0)
        near(state, "ghost", 120.0, -60.0)
        return []
    if frame in (100, 110, 120, 130, 140) and state is not None:
        # A bat that cannot die, touching the hero: the hurt sound, the shake
        # and the damage numbers we want in the picture.
        near(state, "bat", 18.0, 0.0).hp = 10 ** 6
        return []
    if 130 <= frame <= 200 and state is not None and state.popups \
            and not holder["seen"].get("feel_shot"):
        holder["seen"]["feel_shot"] = True
        holder["seen"]["feel_numbers"] = len(state.popups)
        shoot("ns_feel")
        return []
    if 155 <= frame <= 300 and state is not None and state.flashes \
            and not holder["seen"].get("flash_shot"):
        holder["seen"]["flash_shot"] = True
        shoot("ns_flash")
        return []
    if frame == 150 and state is not None:
        holder["seen"]["boss_alive"] = any(e.boss for e in state.enemies)
        shoot("ns_waves")
        return []
    if frame == 160 and state is not None:
        state.data["goal"]["survive_seconds"] = state.time + 2.0
        return []
    if frame == 300 and state is not None:
        holder["seen"]["victory"] = state.status
        shoot("ns_victory")
        return []
    if frame == 305 and state is not None:
        restore_normal_numbers(state)
        return []
    if frame == 310:
        return [click((200, 400))]
    if frame == 313 and state is not None:
        holder["seen"]["restart"] = (state.status, state.time < 1.0, state.level,
                                     state.boss_spawned, state.hp,
                                     dict(state.weapons))

    # --- keep playing with more input so nothing crashes ---
    if frame == 330:
        return [mouse((60, 640))]
    if frame == 400:
        return [finger(pygame.FINGERDOWN, 0.8, 0.2, 1.0)]
    if frame == 405:
        return [finger(pygame.FINGERMOTION, 0.3, 0.7, 1.0)]
    if frame == 410:
        return [finger(pygame.FINGERUP, 0.3, 0.7, 0.0)]
    if frame == 420:
        return [mouse((330, 90))]
    if frame == 520:
        return [pygame.event.Event(pygame.QUIT)]
    return []


pygame.event.get = fake_event_get
asyncio.run(main.main())

state = holder["state"]
print("\n".join(holder["log"]))
print("\nframes run:", holder["frame"])
for label, value in holder["seen"].items():
    print("%-14s %s" % (label + ":", sorted(value) if isinstance(value, set) else value))
print("final: t=%.1f Lv %d alive=%d kills=%d status=%s %s" % (
    state.time, state.level, len(state.enemies), state.kills, state.status,
    state.owned_line()))
print("sounds played:", {n: played.count(n) for n in sorted(set(played))})

seen = holder["seen"]
problems = []
if seen.get("sounds_loaded") != ["end", "gem", "hit", "hurt", "level_up"]:
    problems.append("sounds/ did not load: %s" % seen.get("sounds_loaded"))
if not {"hit", "gem", "level_up", "hurt", "end"} <= set(played):
    problems.append("not every sound was played: %s" % sorted(set(played)))
if not seen.get("popups_max"):
    problems.append("no damage numbers were ever on screen")
if not seen.get("flashes_max"):
    problems.append("no death flash was ever on screen")
if not seen.get("shake_seen") or not seen.get("shake_peak"):
    problems.append("the screen never shook when the hero was hurt")
if holder["frame"] < 520:
    problems.append("loop stopped early")
if seen.get("cards") != ("level_up", 3):
    problems.append("the level-up screen with 3 cards never appeared")
if seen.get("after_card") != ("playing", 2):
    problems.append("clicking a card did not resume play at Lv 2")
if not seen.get("boss_alive"):
    problems.append("the boss never came on screen")
if seen.get("kinds") != {"bat", "slime", "ghost", "demon"}:
    problems.append("not every enemy kind appeared: %s" % seen.get("kinds"))
if seen.get("victory") != "victory":
    problems.append("no VICTORY at the goal time (saw %r)" % seen.get("victory"))
if seen.get("restart") != ("playing", True, 1, False, 100.0, {"spark_wand": 1}):
    problems.append("clicking the end screen did not start a clean new run")
print("\nRESULT:", "PROBLEMS: " + "; ".join(problems) if problems else "all checks passed")
