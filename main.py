"""Night Survivors: window, drawing, sound and input.

This file only loads finished pictures from assets/ (see make_assets.py) and
finished sounds from sounds/ (see make_sounds.py).
The loop is async with one `await asyncio.sleep(0)` per frame so pygbag can
run the game in a web browser.
"""

import asyncio
import math
import os
import sys

import pygame

import rules

STEP = rules.STEP
END_STATES = ("game_over", "victory")
SPARK_COLOUR = (255, 225, 120)
HP_BACK = (60, 20, 26)
HP_FILL = (220, 70, 70)
XP_BACK = (18, 30, 60)
XP_FILL = (90, 150, 255)
BAR_EDGE = (20, 60, 90)
RING_COLOUR = (255, 235, 150)
RING_DIM = (170, 160, 110)
TEXT = (205, 210, 235)
SHADOW = (12, 10, 18)
OVER_TEXT = (250, 250, 250)
CARD_BACK = (34, 30, 48)
CARD_EDGE = (120, 110, 170)
CARD_LEVEL = (255, 220, 130)
POPUP_TEXT = (255, 240, 190)
FLASH = (255, 255, 255)


class Input:
    """Turns mouse and finger events into a walk direction and a click."""

    def __init__(self, width, height):
        self.width = width
        self.height = height
        self.pointer_x = width / 2.0
        self.pointer_y = height / 2.0
        self.seen_pointer = False
        self.uses_touch = False
        self.touching = False
        self.click_at = None

    def handle(self, event):
        if event.type == pygame.MOUSEMOTION or event.type == pygame.MOUSEBUTTONDOWN:
            self.pointer_x, self.pointer_y = event.pos
            self.uses_touch = False
            self.seen_pointer = True
            if event.type == pygame.MOUSEBUTTONDOWN:
                self.click_at = event.pos
        elif event.type in (pygame.FINGERDOWN, pygame.FINGERMOTION):
            self.pointer_x = event.x * self.width
            self.pointer_y = event.y * self.height
            self.uses_touch = True
            self.touching = True
            self.seen_pointer = True
        elif event.type == pygame.FINGERUP:
            self.touching = False
            self.click_at = (self.pointer_x, self.pointer_y)

    def take_click(self):
        """The click or tap of this frame, or None."""
        click, self.click_at = self.click_at, None
        return click

    def walk_offset(self):
        """Offset of the pointer from the hero, who is always at screen centre.

        The mouse pointer stays where it was left, so the hero keeps walking
        even when the mouse does not move. When a finger is lifted the hero
        stops, so a touch gives a direction only while it is down.
        """
        if not self.seen_pointer or (self.uses_touch and not self.touching):
            return 0.0, 0.0
        return (self.pointer_x - self.width / 2.0,
                self.pointer_y - self.height / 2.0)


def load_images(data):
    """Load the finished pictures from assets/ (made by make_assets.py)."""
    folder = os.path.join(os.path.dirname(os.path.abspath(__file__)), "assets")
    names = ["hero", "floor", "sword", "gem_blue", "gem_pink"]
    names.extend(data["enemies"])
    images = {}
    for name in names:
        path = os.path.join(folder, name + ".png")
        if not os.path.exists(path):
            raise SystemExit("Missing %s - run  python make_assets.py  first." % path)
        images[name] = pygame.image.load(path).convert_alpha()
    return images


def enemy_pictures(images, data):
    """One picture per enemy, drawn twice as big when the design says so."""
    pictures = {}
    for kind, stats in data["enemies"].items():
        image = images[kind]
        scale = stats.get("draw_scale", 1)
        if scale != 1:
            size = (image.get_width() * scale, image.get_height() * scale)
            image = pygame.transform.scale(image, size)
        pictures[kind] = image
    return pictures


def load_sounds(data):
    """Load the finished sounds from sounds/, made by make_sounds.py.

    main.py does not build sounds itself: in a web browser only the files work.
    Without an audio device, or without the files, the game plays silently.
    """
    try:
        pygame.mixer.init()
    except pygame.error:
        print("No audio device here - playing silently.")
        return {}
    folder = os.path.join(os.path.dirname(os.path.abspath(__file__)), "sounds")
    volume = data["sound"]["volume"]
    sounds = {}
    for name in sorted(set(data["sound"]["files"].values())):
        for suffix in (".ogg", ".wav"):
            path = os.path.join(folder, name + suffix)
            if os.path.exists(path):
                sound = pygame.mixer.Sound(path)
                sound.set_volume(volume)
                sounds[name] = sound
                break
        else:
            print("Missing sounds/%s - run  python make_sounds.py  for sound." % name)
    return sounds


def play_events(state, sounds, cfg, cooldown):
    """Play the sounds the rules asked for this frame, never too fast.

    A weapon can hit a dozen enemies in one second, so each sound has a
    smallest gap between two plays (data/game.json, sound/min_gap).
    """
    now = pygame.time.get_ticks() / 1000.0
    for event in state.take_events():
        sound = sounds.get(cfg["files"].get(event, ""))
        if sound is None or now < cooldown.get(event, 0.0):
            continue
        sound.play()
        cooldown[event] = now + cfg["min_gap"].get(event, 0.0)


def camera_shake(state, feel):
    """How far to nudge the picture while the hero is hurt, in pixels."""
    total = feel["shake_seconds"]
    if state.shake <= 0.0 or total <= 0.0:
        return 0, 0
    left = state.shake / total
    angle = (total - state.shake) / total * feel["shake_wiggles"] * math.tau
    return (int(round(feel["shake_pixels"] * left * math.sin(angle))),
            int(round(feel["shake_pixels"] * left * math.cos(angle * 1.7))))


def clock_text(seconds, total=None):
    label = "%d:%02d" % (int(seconds // 60), int(seconds % 60))
    if total is None:
        return label
    return "%s / %d:%02d" % (label, int(total // 60), int(total % 60))


def to_screen(value, hero_value, centre):
    return int(value - hero_value + centre)


def draw_sprite(surface, image, x, y):
    surface.blit(image, image.get_rect(center=(int(x), int(y))))


def draw_floor(surface, state, images, centre):
    tile = images["floor"].get_width()
    centre_x, centre_y = centre
    left = state.hero_x - centre_x
    top = state.hero_y - centre_y
    first_col = int(math.floor(left / tile))
    first_row = int(math.floor(top / tile))
    cols = int(surface.get_width() / tile) + 2
    rows = int(surface.get_height() / tile) + 2
    for row in range(rows):
        for col in range(cols):
            x = int((col + first_col) * tile - left)
            y = int((row + first_row) * tile - top)
            surface.blit(images["floor"], (x, y))


def draw_gems(surface, state, images, centre):
    for gem in state.gems:
        image = images["gem_blue"] if gem.xp <= 1 else images["gem_pink"]
        draw_sprite(surface, image,
                    to_screen(gem.x, state.hero_x, centre[0]),
                    to_screen(gem.y, state.hero_y, centre[1]))


def draw_blades(surface, state, images, centre):
    if "spin_blades" not in state.weapons:
        return
    for x, y in state.blade_positions():
        screen_x = to_screen(x, state.hero_x, centre[0])
        screen_y = to_screen(y, state.hero_y, centre[1])
        angle = math.degrees(math.atan2(screen_y - centre[1], screen_x - centre[0]))
        draw_sprite(surface, pygame.transform.rotate(images["sword"], -angle - 90),
                    screen_x, screen_y)


def draw_ring(surface, state, centre):
    if "holy_ring" not in state.weapons:
        return
    bright = state.ring_flash > 0.05
    pygame.draw.circle(surface, RING_COLOUR if bright else RING_DIM,
                       (int(centre[0]), int(centre[1])), int(state.holy_radius()),
                       2 + (3 if bright else 0))


def draw_flashes(surface, state, feel, centre):
    """A white ring that grows and fades where an enemy died."""
    for flash in state.flashes:
        gone = 1.0 - flash.life / flash.total
        radius = int(feel["flash_radius"] + feel["flash_grow"] * gone)
        alpha = int(220 * flash.life / flash.total)
        size = radius * 2 + 4
        glow = pygame.Surface((size, size), pygame.SRCALPHA)
        pygame.draw.circle(glow, FLASH + (alpha,), (size // 2, size // 2), radius, 3)
        surface.blit(glow, (to_screen(flash.x, state.hero_x, centre[0]) - size // 2,
                            to_screen(flash.y, state.hero_y, centre[1]) - size // 2))


def draw_popups(surface, state, fonts, centre):
    """The damage numbers, floating up from the enemy they hit."""
    _, small = fonts
    for popup in state.popups:
        alpha = max(0, min(255, int(255 * popup.life / popup.total)))
        amount = str(popup.amount)
        x = to_screen(popup.x, state.hero_x, centre[0])
        y = to_screen(popup.y, state.hero_y, centre[1])
        shadow = small.render(amount, True, SHADOW)
        shadow.set_alpha(alpha)
        surface.blit(shadow, (x - shadow.get_width() // 2 + 1, y + 1))
        label = small.render(amount, True, POPUP_TEXT)
        label.set_alpha(alpha)
        surface.blit(label, (x - label.get_width() // 2, y))


def text(surface, font, string, colour, pos):
    """Text with a dark offset copy, so it stays readable on the light floor."""
    surface.blit(font.render(string, True, SHADOW), (pos[0] + 1, pos[1] + 1))
    label = font.render(string, True, colour)
    surface.blit(label, pos)
    return label


def bar(surface, fonts, x, y, ratio, back, fill, label):
    width, height = 150, 14
    pygame.draw.rect(surface, back, (x, y, width, height))
    if ratio > 0:
        pygame.draw.rect(surface, fill, (x, y, int(width * min(1.0, ratio)), height))
    pygame.draw.rect(surface, BAR_EDGE, (x, y, width, height), 2)
    text(surface, fonts[1], label, TEXT, (x + 156, y - 2))


def draw_hud(surface, state, fonts):
    big, small = fonts
    bar(surface, fonts, 10, 10, state.hp / state.max_hp, HP_BACK, HP_FILL,
        "%d / %d" % (round(state.hp), state.max_hp))
    bar(surface, fonts, 10, 30, state.xp / state.xp_needed(), XP_BACK, XP_FILL,
        "Lv %d" % state.level)

    total = state.data["goal"]["survive_seconds"]
    label = clock_text(state.time, total)
    text(surface, big, label, TEXT,
         (surface.get_width() - big.size(label)[0] - 10, 10))

    owned = state.owned_line()
    text(surface, small, owned, TEXT,
         (10, surface.get_height() - small.size(owned)[1] - 8))


def wrap(text, font, max_width):
    words = text.split()
    lines = []
    while words:
        used = words.pop(0)
        while words and font.size(used + " " + words[0])[0] <= max_width:
            used += " " + words.pop(0)
        lines.append(used)
    return lines


def card_rects(surface, count):
    margin, gap, height = 18, 12, 128
    top = int(surface.get_height() * 0.22)
    return [pygame.Rect(margin, top + index * (height + gap),
                        surface.get_width() - 2 * margin, height)
            for index in range(count)]


def draw_shade(surface, alpha=210):
    shade = pygame.Surface(surface.get_size(), pygame.SRCALPHA)
    shade.fill((10, 8, 18, alpha))
    surface.blit(shade, (0, 0))


def draw_cards(surface, state, fonts):
    big, small = fonts
    draw_shade(surface, 235)
    title = big.render("LEVEL UP - choose one", True, OVER_TEXT)
    surface.blit(title, (surface.get_width() // 2 - title.get_width() // 2, 70))
    for rect, card in zip(card_rects(surface, len(state.cards)), state.cards):
        pygame.draw.rect(surface, CARD_BACK, rect, border_radius=10)
        pygame.draw.rect(surface, CARD_EDGE, rect, 2, border_radius=10)
        surface.blit(big.render(card["name"], True, OVER_TEXT), (rect.x + 14, rect.y + 12))
        if card["level"] is not None:
            surface.blit(small.render("Lv %d" % card["level"], True, CARD_LEVEL),
                         (rect.right - 46, rect.y + 18))
        y = rect.y + 54
        for line in wrap(card["text"], small, rect.width - 28):
            surface.blit(small.render(line, True, TEXT), (rect.x + 14, y))
            y += 22


def draw_end(surface, state, fonts):
    big, small = fonts
    won = state.status == "victory"
    draw_shade(surface)
    title = big.render("VICTORY" if won else "GAME OVER",
                       True, (120, 235, 140) if won else (235, 90, 90))
    surface.blit(title, (surface.get_width() // 2 - title.get_width() // 2, 240))

    total = state.data["goal"]["survive_seconds"]
    lines = ["Survived " + clock_text(state.time, total),
             "Kills %d" % state.kills,
             "Level %d" % state.level,
             "",
             "Click or tap to play again"]
    y = 300
    for line in lines:
        if not line:
            y += 10
        else:
            label = small.render(line, True, OVER_TEXT)
            surface.blit(label, (surface.get_width() // 2 - label.get_width() // 2, y))
            y += 26


async def main():
    pygame.init()
    data = rules.load_data()
    width = data["screen"]["width"]
    height = data["screen"]["height"]
    surface = pygame.display.set_mode((width, height))
    pygame.display.set_caption("Night Survivors")
    clock = pygame.time.Clock()
    fonts = (pygame.font.Font(None, 34), pygame.font.Font(None, 22))
    images = load_images(data)
    enemy_images = enemy_pictures(images, data)
    sounds = load_sounds(data)
    feel = data["feel"]

    state = rules.GameState(data)
    pad = Input(width, height)
    fps = data["fps"]
    accumulator = 0.0
    paused = False
    running = True
    cooldown = {}
    home = (width / 2.0, height / 2.0)

    while running:
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                running = False
            elif event.type == pygame.KEYDOWN and event.key == pygame.K_p:
                paused = not paused
            else:
                pad.handle(event)

        click = pad.take_click()
        if click is not None:
            if state.status == "level_up":
                for index, rect in enumerate(card_rects(surface, len(state.cards))):
                    if rect.collidepoint(click):
                        state.choose_card(index)
                        break
            elif state.status in END_STATES:
                state.reset()
                paused = False

        if not paused and state.status == "playing":
            state.set_walk_direction(*pad.walk_offset())
            accumulator += clock.tick(fps) / 1000.0
            accumulator = min(accumulator, 0.2)
            while accumulator >= STEP:
                state.update(STEP)
                accumulator -= STEP
        else:
            clock.tick(fps)

        play_events(state, sounds, data["sound"], cooldown)
        shake_x, shake_y = camera_shake(state, feel)
        centre = (home[0] + shake_x, home[1] + shake_y)

        draw_floor(surface, state, images, centre)
        draw_gems(surface, state, images, centre)
        for enemy in state.enemies:
            draw_sprite(surface, enemy_images[enemy.kind],
                        to_screen(enemy.x, state.hero_x, centre[0]),
                        to_screen(enemy.y, state.hero_y, centre[1]))
        draw_flashes(surface, state, feel, centre)
        for spark in state.sparks:
            pygame.draw.circle(surface, SPARK_COLOUR,
                               (to_screen(spark.x, state.hero_x, centre[0]),
                                to_screen(spark.y, state.hero_y, centre[1])),
                               int(spark.radius))
        draw_ring(surface, state, centre)
        draw_sprite(surface, images["hero"], centre[0], centre[1])
        draw_blades(surface, state, images, centre)
        draw_popups(surface, state, fonts, centre)

        draw_hud(surface, state, fonts)
        if state.status == "level_up":
            draw_cards(surface, state, fonts)
        elif state.status in END_STATES:
            draw_end(surface, state, fonts)
        elif paused:
            label = fonts[0].render("PAUSED - press P", True, OVER_TEXT)
            surface.blit(label, (width // 2 - label.get_width() // 2, height // 2))

        pygame.display.flip()
        await asyncio.sleep(0)

    pygame.quit()


if __name__ == "__main__":
    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    asyncio.run(main())
