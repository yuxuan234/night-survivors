"""Run this on your own computer:  python make_sounds.py

It writes short .wav sounds into sounds/ using only the standard library.
main.py never imports this file (it would not work in a web browser): it only
loads the finished files from sounds/.
"""

import array
import math
import os
import random
import wave

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "sounds")
RATE = 22050          # samples per second
VOLUME = 0.5          # how loud the files are written (0.0 - 1.0)

SINE = math.sin


def triangle(phase):
    return 2.0 / math.pi * math.asin(math.sin(phase))


TRIANGLE = triangle


def tone(seconds, start_hz, end_hz=None, shape=SINE, volume=1.0):
    """One note, optionally sliding from start_hz to end_hz."""
    total = max(1, int(RATE * seconds))
    samples = []
    phase = 0.0
    for index in range(total):
        ratio = index / total
        hz = start_hz if end_hz is None else start_hz + (end_hz - start_hz) * ratio
        phase += math.tau * hz / RATE
        samples.append(shape(phase) * volume)
    return samples


def noise(seconds, volume=1.0):
    """Static, for the thump when the hero is hurt."""
    rng = random.Random(7)
    return [rng.uniform(-1.0, 1.0) * volume for _ in range(int(RATE * seconds))]


def decay(samples, strength=4.0):
    """Loud at the start, quiet at the end."""
    total = len(samples)
    return [s * math.exp(-strength * index / total) for index, s in enumerate(samples)]


def fade(samples, seconds=0.004):
    """A tiny fade in and out at the edges, so the sound does not click."""
    out = list(samples)
    edge = max(1, min(int(RATE * seconds), len(out) // 2))
    for index in range(edge):
        out[index] *= index / edge
        out[-1 - index] *= index / edge
    return out


def add(track, start_seconds, samples):
    """Mix samples into track at start_seconds (makes the track longer if needed)."""
    start = int(RATE * start_seconds)
    if start + len(samples) > len(track):
        track.extend([0.0] * (start + len(samples) - len(track)))
    for index, value in enumerate(samples):
        track[start + index] += value
    return track


def write(name, samples):
    """Normalise to VOLUME and save one 16-bit mono .wav file."""
    peak = max((abs(s) for s in samples), default=0.0)
    scale = VOLUME / peak if peak else 0.0
    frames = array.array("h", [int(max(-1.0, min(1.0, s * scale)) * 32767)
                               for s in samples])
    with wave.open(os.path.join(OUT, name + ".wav"), "wb") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(RATE)
        handle.writeframes(frames.tobytes())
    return name, len(samples) / RATE


def hit():
    """A small tick: a spark or blade landing on an enemy."""
    track = decay(noise(0.03, 0.5), 6.0)
    add(track, 0.0, decay(tone(0.05, 900.0, 300.0), 6.0))
    return fade(track)


def gem():
    """A bright two-note ping for picking up a crystal."""
    track = tone(0.06, 880.0, shape=TRIANGLE)
    add(track, 0.05, decay(tone(0.09, 1320.0, shape=TRIANGLE), 3.0))
    return fade(track)


def level_up():
    """Four rising notes: a card choice is coming."""
    track = []
    for index, hz in enumerate((523.0, 659.0, 784.0, 1047.0)):
        add(track, index * 0.075, tone(0.12, hz, shape=TRIANGLE, volume=0.8))
    return fade(decay(track, 1.2))


def hurt():
    """A low thump with a little static: the hero took damage."""
    track = decay(noise(0.06, 0.7), 5.0)
    add(track, 0.0, decay(tone(0.16, 220.0, 90.0, volume=0.9), 3.0))
    return fade(track)


def end():
    """Three slow notes going down: the run is over."""
    track = []
    for index, hz in enumerate((392.0, 311.0, 233.0)):
        add(track, index * 0.2, decay(tone(0.24, hz, shape=TRIANGLE), 2.5))
    return fade(decay(track, 1.0))


SOUNDS = {"hit": hit, "gem": gem, "level_up": level_up, "hurt": hurt, "end": end}


def main():
    if not os.path.isdir(OUT):
        os.makedirs(OUT)
    print("wrote %d files to sounds/ (%d Hz, 16-bit mono):" % (len(SOUNDS), RATE))
    for name, make in SOUNDS.items():
        name, seconds = write(name, make())
        print("   %-9s %5.2f s" % (name + ".wav", seconds))


if __name__ == "__main__":
    main()
