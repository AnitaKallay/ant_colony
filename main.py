import pygame
import random
import math
import time
import struct
import array
from enum import Enum
from dataclasses import dataclass, field
from typing import List, Optional, Tuple

pygame.init()
pygame.font.init()
pygame.mixer.init(frequency=44100, size=-16, channels=1, buffer=512)

# ── Chiptune Sound Engine ──────────────────────────────────────────────────────
SAMPLE_RATE = 44100

def _make_sound(samples) -> pygame.mixer.Sound:
    """Convert a list of float samples [-1,1] into a pygame Sound."""
    buf = array.array('h', (int(max(-32767, min(32767, s * 32767))) for s in samples))
    return pygame.mixer.Sound(buffer=buf)

def _square(t, freq, duty=0.5):
    return 1.0 if (t * freq % 1.0) < duty else -1.0

def _sine(t, freq):
    return math.sin(2 * math.pi * freq * t)

def _noise():
    return random.uniform(-1, 1)

def _envelope(i, total, attack=0.01, decay=0.1, sustain=0.7, release=0.2):
    t = i / total
    if t < attack:
        return t / attack
    elif t < attack + decay:
        return 1.0 - (1.0 - sustain) * ((t - attack) / decay)
    elif t < 1.0 - release:
        return sustain
    else:
        return sustain * (1.0 - (t - (1.0 - release)) / release)

def _gen(duration, fn, vol=0.5):
    n = int(SAMPLE_RATE * duration)
    return [fn(i / SAMPLE_RATE, i, n) * vol for i in range(n)]

class SoundEngine:
    def __init__(self):
        self.sounds = {}
        self.music_channel = None
        self.music_playing = False
        self.music_sound = None  # built lazily on first start_music() call
        self._build_sounds()

    def _build_sounds(self):
        # Egg hatch — rising arpeggio blip
        def hatch(t, i, n):
            freq = 440 * (1 + i / n * 2)
            return _square(t, freq, 0.4) * _envelope(i, n, 0.01, 0.05, 0.3, 0.5)
        self.sounds['hatch'] = _make_sound(_gen(0.35, hatch, 0.4))

        # Food deposited — satisfying coin-like chime
        def coin(t, i, n):
            f1 = _sine(t, 880) * _envelope(i, n, 0.005, 0.05, 0.0, 0.9)
            f2 = _sine(t, 1320) * _envelope(i, n, 0.005, 0.1, 0.0, 0.8) * 0.5
            return f1 + f2
        self.sounds['food'] = _make_sound(_gen(0.3, coin, 0.5))

        # Worker dispatched — quick chip blip
        def dispatch(t, i, n):
            freq = 330 + 220 * (i / n)
            return _square(t, freq, 0.5) * _envelope(i, n, 0.005, 0.02, 0.4, 0.4)
        self.sounds['dispatch'] = _make_sound(_gen(0.15, dispatch, 0.3))

        # Room built — triumphant 3-note chord blip
        def build(t, i, n):
            progress = i / n
            if progress < 0.33:
                freq = 523.25  # C5
            elif progress < 0.66:
                freq = 659.25  # E5
            else:
                freq = 783.99  # G5
            return _square(t, freq, 0.45) * _envelope(i, n, 0.01, 0.05, 0.5, 0.3)
        self.sounds['build'] = _make_sound(_gen(0.45, build, 0.4))

        # Leaf piece picked up — soft pop
        def pickup(t, i, n):
            freq = 600 - 200 * (i / n)
            return _square(t, freq, 0.3) * _envelope(i, n, 0.005, 0.02, 0.0, 0.8)
        self.sounds['pickup'] = _make_sound(_gen(0.1, pickup, 0.25))

        # Leaf piece deposited in food room — bubbly pop
        def deposit(t, i, n):
            freq = 400 + 400 * (i / n)
            return (_square(t, freq, 0.5) * 0.6 + _sine(t, freq * 1.5) * 0.4) * \
                   _envelope(i, n, 0.005, 0.05, 0.0, 0.7)
        self.sounds['deposit'] = _make_sound(_gen(0.18, deposit, 0.3))

        # Warning / can't do — low buzz
        def warn(t, i, n):
            return _square(t, 120, 0.7) * _envelope(i, n, 0.01, 0.05, 0.5, 0.3)
        self.sounds['warn'] = _make_sound(_gen(0.2, warn, 0.25))

        # Colony selected — fanfare jingle
        def fanfare(t, i, n):
            notes = [261.63, 329.63, 392.0, 523.25]  # C E G C
            seg = n // len(notes)
            idx = min(i // seg, len(notes) - 1)
            freq = notes[idx]
            local_i = i % seg
            return _square(t, freq, 0.5) * _envelope(local_i, seg, 0.01, 0.05, 0.6, 0.3)
        self.sounds['fanfare'] = _make_sound(_gen(0.6, fanfare, 0.4))

        # Ant step — tiny tick (used sparingly)
        def step(t, i, n):
            return _noise() * _envelope(i, n, 0.001, 0.01, 0.0, 0.8)
        self.sounds['step'] = _make_sound(_gen(0.04, step, 0.08))

    def _build_music(self):
        """Looping chiptune track — 16 bars across two 8-bar sections."""
        bpm = 118
        beat = 60 / bpm
        total = beat * 4 * 16  # 16 bars

        # ── Section A (bars 1-8): bright, wandering melody ──
        A = 0
        melody_A = [
            (A+0*beat,523.25,beat*.8),(A+1*beat,587.33,beat*.4),(A+1.5*beat,659.25,beat*.4),
            (A+2*beat,783.99,beat*.8),(A+3*beat,659.25,beat*.4),(A+3.5*beat,587.33,beat*.4),
            (A+4*beat,523.25,beat*1.),(A+5*beat,392.00,beat*.8),
            (A+6*beat,440.00,beat*.4),(A+6.5*beat,493.88,beat*.4),(A+7*beat,523.25,beat*.8),
            (A+8*beat,659.25,beat*.8),(A+9*beat,587.33,beat*.4),(A+9.5*beat,523.25,beat*.4),
            (A+10*beat,493.88,beat*.8),(A+11*beat,440.00,beat*.4),(A+11.5*beat,392.00,beat*.4),
            (A+12*beat,440.00,beat*.8),(A+13*beat,493.88,beat*.4),(A+13.5*beat,523.25,beat*.4),
            (A+14*beat,587.33,beat*.8),(A+15*beat,523.25,beat*.8),
            (A+16*beat,659.25,beat*.6),(A+17*beat,587.33,beat*.4),(A+17.5*beat,523.25,beat*.4),
            (A+18*beat,493.88,beat*.8),(A+19*beat,440.00,beat*.4),(A+19.5*beat,392.00,beat*.4),
            (A+20*beat,349.23,beat*1.),(A+21*beat,392.00,beat*.8),
            (A+22*beat,440.00,beat*.4),(A+22.5*beat,493.88,beat*.4),(A+23*beat,523.25,beat*.8),
            (A+24*beat,587.33,beat*.8),(A+25*beat,523.25,beat*.4),(A+25.5*beat,493.88,beat*.4),
            (A+26*beat,440.00,beat*.8),(A+27*beat,392.00,beat*.4),(A+27.5*beat,349.23,beat*.4),
            (A+28*beat,392.00,beat*.8),(A+29*beat,440.00,beat*.8),
            (A+30*beat,493.88,beat*.8),(A+31*beat,523.25,beat*1.2),
        ]

        # ── Section B (bars 9-16): lower, more brooding ──
        B = beat * 32
        melody_B = [
            (B+0*beat,392.00,beat*.8),(B+1*beat,349.23,beat*.4),(B+1.5*beat,392.00,beat*.4),
            (B+2*beat,440.00,beat*.8),(B+3*beat,493.88,beat*.4),(B+3.5*beat,440.00,beat*.4),
            (B+4*beat,392.00,beat*1.),(B+5*beat,349.23,beat*.8),
            (B+6*beat,329.63,beat*.4),(B+6.5*beat,349.23,beat*.4),(B+7*beat,392.00,beat*.8),
            (B+8*beat,440.00,beat*.8),(B+9*beat,493.88,beat*.4),(B+9.5*beat,523.25,beat*.4),
            (B+10*beat,587.33,beat*.8),(B+11*beat,523.25,beat*.4),(B+11.5*beat,493.88,beat*.4),
            (B+12*beat,440.00,beat*.8),(B+13*beat,493.88,beat*.4),(B+13.5*beat,523.25,beat*.4),
            (B+14*beat,587.33,beat*.8),(B+15*beat,659.25,beat*.8),
            (B+16*beat,523.25,beat*.6),(B+17*beat,493.88,beat*.4),(B+17.5*beat,440.00,beat*.4),
            (B+18*beat,392.00,beat*.8),(B+19*beat,349.23,beat*.4),(B+19.5*beat,329.63,beat*.4),
            (B+20*beat,349.23,beat*1.),(B+21*beat,392.00,beat*.8),
            (B+22*beat,440.00,beat*.4),(B+22.5*beat,493.88,beat*.4),(B+23*beat,523.25,beat*.8),
            (B+24*beat,587.33,beat*.6),(B+25*beat,523.25,beat*.4),(B+25.5*beat,493.88,beat*.4),
            (B+26*beat,440.00,beat*.8),(B+27*beat,392.00,beat*.4),(B+27.5*beat,349.23,beat*.4),
            (B+28*beat,392.00,beat*.8),(B+29*beat,440.00,beat*.6),
            (B+30*beat,493.88,beat*.8),(B+31*beat,523.25,beat*1.2),
        ]

        # Bass pattern repeats every 8 beats
        def bass_for(offset):
            return [
                (offset+0*beat,130.81,beat*.9),(offset+2*beat,130.81,beat*.9),
                (offset+4*beat,98.00, beat*.9),(offset+6*beat,110.00,beat*.9),
                (offset+8*beat,130.81,beat*.9),(offset+10*beat,98.00,beat*.9),
                (offset+12*beat,87.31,beat*.9),(offset+14*beat,98.00,beat*.9),
                (offset+16*beat,130.81,beat*.9),(offset+18*beat,146.83,beat*.9),
                (offset+20*beat,110.00,beat*.9),(offset+22*beat,98.00,beat*.9),
                (offset+24*beat,87.31,beat*.9),(offset+26*beat,98.00,beat*.9),
                (offset+28*beat,110.00,beat*.9),(offset+30*beat,130.81,beat*.9),
            ]

        bass_notes = bass_for(A) + bass_for(B)
        all_melody = melody_A + melody_B

        n = int(SAMPLE_RATE * total)
        buf = [0.0] * n

        for start, freq, dur in all_melody:
            si = int(start * SAMPLE_RATE)
            ei = min(n, si + int(dur * SAMPLE_RATE))
            length = max(1, ei - si)
            for k in range(length):
                t = (si + k) / SAMPLE_RATE
                env = _envelope(k, length, 0.01, 0.05, 0.6, 0.2)
                buf[si + k] += _square(t, freq, 0.45) * env * 0.22

        for start, freq, dur in bass_notes:
            si = int(start * SAMPLE_RATE)
            ei = min(n, si + int(dur * SAMPLE_RATE))
            length = max(1, ei - si)
            for k in range(length):
                t = (si + k) / SAMPLE_RATE
                env = _envelope(k, length, 0.01, 0.1, 0.5, 0.3)
                buf[si + k] += _sine(t, freq) * env * 0.18

        # Hi-hat every 8th note
        hat_iv = int(beat / 2 * SAMPLE_RATE)
        hat_len = int(0.035 * SAMPLE_RATE)
        for hi in range(0, n, hat_iv):
            for k in range(min(hat_len, n - hi)):
                buf[hi + k] += _noise() * (1 - k / hat_len) * 0.055

        # Kick on every beat
        kick_len = int(0.09 * SAMPLE_RATE)
        for bi in range(int(total / beat)):
            ki = int(bi * beat * SAMPLE_RATE)
            for k in range(min(kick_len, n - ki)):
                t = k / SAMPLE_RATE
                f = 75 * math.exp(-t * 35)
                e = math.exp(-t * 22)
                buf[ki + k] += _sine(t, f) * e * 0.28

        # Snare on beats 2 and 4
        snare_len = int(0.06 * SAMPLE_RATE)
        for bi in range(int(total / beat)):
            if bi % 4 in (1, 3):
                si2 = int(bi * beat * SAMPLE_RATE)
                for k in range(min(snare_len, n - si2)):
                    t = k / SAMPLE_RATE
                    e = math.exp(-t * 40)
                    buf[si2 + k] += (_noise() * 0.6 + _sine(t, 200) * 0.4) * e * 0.18

        self.music_sound = _make_sound(buf)
        self.music_sound.set_volume(0.32)

    def play(self, name, volume=1.0):
        s = self.sounds.get(name)
        if s:
            s.set_volume(volume)
            s.play()

    def start_music(self):
        if not self.music_playing:
            if self.music_sound is None:
                self._build_music()
            self.music_channel = self.music_sound.play(loops=-1)
            self.music_playing = True

    def stop_music(self):
        if self.music_playing and self.music_channel:
            self.music_channel.stop()
            self.music_playing = False

    def toggle_music(self):
        """Only allows turning music off, not back on."""
        if self.music_playing:
            self.stop_music()


# Global sound engine (initialized after pygame.mixer.init)
SFX: Optional["SoundEngine"] = None

# ── Constants ──────────────────────────────────────────────────────────────────
W, H = 1280, 720
FPS = 60
TILE = 40

# Colors
C = {
    "bg_out":    (34, 85, 34),
    "bg_nest":   (80, 50, 20),
    "soil":      (110, 70, 30),
    "soil2":     (90, 55, 22),
    "tunnel":    (60, 38, 14),
    "ui_bg":     (20, 12, 5),
    "ui_panel":  (35, 22, 8),
    "ui_border": (160, 100, 40),
    "gold":      (220, 170, 50),
    "white":     (240, 235, 220),
    "red_ant":   (200, 50, 30),
    "red_dark":  (140, 25, 15),
    "black_ant": (30, 30, 35),
    "black_dark":(10, 10, 15),
    "queen_c":   (180, 120, 200),
    "egg_c":     (240, 230, 200),
    "leaf":      (60, 160, 40),
    "leaf2":     (45, 130, 30),
    "mushroom":  (210, 160, 100),
    "food_glow": (255, 200, 80),
    "grass":     (45, 100, 45),
    "sky":       (135, 195, 120),
    "dirt":      (120, 80, 35),
    "room_queen":(80, 50, 100),
    "room_store":(70, 50, 30),
    "room_leaf": (40, 80, 40),
    "room_food": (100, 70, 20),
    "green_btn": (50, 140, 50),
    "red_btn":   (160, 50, 40),
    "hover_btn": (80, 180, 80),
    "disabled":  (60, 60, 60),
    "pheromone": (180, 255, 180, 80),
}

# Fonts
try:
    FONT_LG    = pygame.font.SysFont("Georgia", 28, bold=True)
    FONT_MD    = pygame.font.SysFont("Georgia", 18)
    FONT_SM    = pygame.font.SysFont("Georgia", 13)
    FONT_TITLE = pygame.font.SysFont("Georgia", 52, bold=True)
    FONT_XL    = pygame.font.SysFont("Georgia", 72, bold=True)
except:
    FONT_LG    = pygame.font.Font(None, 32)
    FONT_MD    = pygame.font.Font(None, 22)
    FONT_SM    = pygame.font.Font(None, 16)
    FONT_TITLE = pygame.font.Font(None, 60)
    FONT_XL    = pygame.font.Font(None, 80)


# ── Enums & Data ───────────────────────────────────────────────────────────────
class GameState(Enum):
    SPLASH   = "splash"
    LOADING  = "loading"
    MENU     = "menu"
    SELECT   = "select"
    NEST     = "nest"
    OUTSIDE  = "outside"
    SHOP     = "shop"
    UPGRADES = "upgrades"
    BATTLE   = "battle"

class AntRole(Enum):
    WORKER = "worker"
    SOLDIER = "soldier"
    QUEEN = "queen"

class AntState(Enum):
    IDLE         = "idle"
    WANDER       = "wander"
    FETCH_LEAF   = "fetch_leaf"
    CARRY_LEAF   = "carry_leaf"
    DEPOSIT      = "deposit"
    PROCESS_LEAF = "process_leaf"  # walking to leaf room to grab a piece
    PROCESS_CARRY= "process_carry" # carrying piece to food room

class RoomType(Enum):
    QUEEN    = "Queen Chamber"
    STORAGE  = "Storage"
    LEAF     = "Leaf Room"
    FOOD     = "Food Lab"
    NURSERY  = "Nursery"
    BARRACKS = "Barracks"
    HOSPITAL = "Hospital"
    FARM     = "Underground Farm"
    TUNNELS  = "Tunnel Network"

ROOM_COLORS = {
    RoomType.QUEEN:    C["room_queen"],
    RoomType.STORAGE:  C["room_store"],
    RoomType.LEAF:     C["room_leaf"],
    RoomType.FOOD:     C["room_food"],
    RoomType.NURSERY:  (60, 60, 90),
    RoomType.BARRACKS: (70, 40, 40),
    RoomType.HOSPITAL: (40, 80, 80),
    RoomType.FARM:     (45, 75, 30),
    RoomType.TUNNELS:  (55, 42, 18),
}

ROOM_COSTS = {
    RoomType.LEAF:     {"food": 3,  "leaves": 0},
    RoomType.FOOD:     {"food": 0,  "leaves": 6},
    RoomType.NURSERY:  {"food": 12, "leaves": 0},
    RoomType.BARRACKS: {"food": 15, "leaves": 0},
    RoomType.HOSPITAL: {"food": 18, "leaves": 0},
    RoomType.FARM:     {"food": 0,  "leaves": 10},
    RoomType.TUNNELS:  {"food": 14, "leaves": 0},
}

ROOM_DESCRIPTIONS = {
    RoomType.LEAF:     "Required to store\nleaf pieces brought\nby workers.",
    RoomType.FOOD:     "Drag leaf pieces\nhere to instantly\ngrow queen's food.",
    RoomType.NURSERY:  "Speed up egg\nhatching by 2x.\nMore ants, faster!",
    RoomType.BARRACKS: "Train soldiers to\ndefend your colony.\nClick to train (3🍄).",
    RoomType.HOSPITAL: "Soldiers regenerate\nbetween battles.\nReduces losses.",
    RoomType.FARM:     "Passively generates\n1 food every 20s.\nNeeds leaf pieces.",
    RoomType.TUNNELS:  "All ants move 25%\nfaster. Speed stacks\nwith Faster Legs.",
}


# ── Particle System ────────────────────────────────────────────────────────────
@dataclass
class Particle:
    x: float
    y: float
    vx: float
    vy: float
    life: float
    max_life: float
    color: tuple
    size: float

    def update(self, dt):
        self.x += self.vx * dt
        self.y += self.vy * dt
        self.life -= dt
        self.vy += 20 * dt  # gravity

    def draw(self, surf):
        alpha = self.life / self.max_life
        r = max(1, int(self.size * alpha))
        col = tuple(max(0, min(255, int(c * alpha))) for c in self.color[:3])
        pygame.draw.circle(surf, col, (int(self.x), int(self.y)), r)


# ── Pheromone Trail ────────────────────────────────────────────────────────────
class PheromoneTrail:
    def __init__(self):
        self.trails = []  # list of (x, y, strength)

    def add(self, x, y, strength=1.0):
        self.trails.append([x, y, strength])
        if len(self.trails) > 300:
            self.trails.pop(0)

    def update(self, dt):
        self.trails = [[x, y, s - dt * 0.3] for x, y, s in self.trails if s > 0]

    def draw(self, surf):
        for x, y, s in self.trails:
            alpha = int(s * 60)
            r = max(1, int(s * 4))
            if alpha > 5:
                c = (100, 220, 100)
                pygame.draw.circle(surf, c, (int(x), int(y)), r)


# ── Leaf Piece (what ants actually carry) ─────────────────────────────────────
class LeafPiece:
    """A small chunk cut from a Leaf. One ant carries one piece."""
    def __init__(self, x, y, shape_pts, color_var=0):
        self.x = float(x)
        self.y = float(y)
        self.angle = random.uniform(0, 360)
        self.wobble = random.uniform(0, math.pi * 2)
        self.being_carried = False
        self.carrier = None
        self.deposited = False
        self.being_dragged = False
        self.drag_offset = (0, 0)
        self.shape_pts = shape_pts
        self.size = 9
        gr = random.randint(-15, 15)
        self.col = (max(0, min(255, C["leaf"][0] + color_var)),
                    max(0, min(255, C["leaf"][1] + gr)),
                    max(0, min(255, C["leaf"][2] + color_var)))
        self.col2 = (max(0, min(255, C["leaf2"][0])),
                     max(0, min(255, C["leaf2"][1] + gr // 2)),
                     max(0, min(255, C["leaf2"][2])))

    def draw(self, surf):
        self.wobble += 0.025
        a = math.radians(self.angle + (math.sin(self.wobble) * 4 if not self.being_carried else 0))
        cos_a, sin_a = math.cos(a), math.sin(a)
        pts = []
        for px, py in self.shape_pts:
            rx = px * cos_a - py * sin_a + self.x
            ry = px * sin_a + py * cos_a + self.y
            pts.append((rx, ry))
        if len(pts) >= 3:
            pygame.draw.polygon(surf, self.col, pts)
            pygame.draw.polygon(surf, self.col2, pts, 1)
        if len(pts) >= 2:
            mid = len(pts) // 2
            pygame.draw.line(surf, self.col2,
                             (int(pts[0][0]), int(pts[0][1])),
                             (int(pts[mid][0]), int(pts[mid][1])), 1)

    def get_rect(self):
        return pygame.Rect(self.x - self.size, self.y - self.size,
                           self.size * 2, self.size * 2)


def make_piece_shapes(count, base_size):
    shapes = []
    for _ in range(count):
        pts = []
        n_verts = random.randint(5, 7)
        for i in range(n_verts):
            ang = 2 * math.pi * i / n_verts + random.uniform(-0.3, 0.3)
            r = base_size * random.uniform(0.5, 1.0)
            pts.append((math.cos(ang) * r, math.sin(ang) * r))
        shapes.append(pts)
    return shapes


# ── Full Leaf (sits on ground, breaks into pieces when ants arrive) ───────────
class Leaf:
    PIECES_PER_LEAF = 4

    def __init__(self, x, y, pieces_override=None):
        self.x = float(x)
        self.y = float(y)
        self.angle = random.uniform(0, 360)
        self.size = random.randint(22, 32)
        self.wobble = random.uniform(0, math.pi * 2)
        n = pieces_override if pieces_override else self.PIECES_PER_LEAF
        self.pieces: List["LeafPiece"] = self._make_pieces(n)
        self.selected = False
        self.fully_harvested = False

    def _make_pieces(self, count):
        pieces = []
        shapes = make_piece_shapes(count, 10)
        offsets = [(-8, -8), (8, -6), (-6, 8), (7, 7), (-9, 2), (9, 2)]
        for i in range(count):
            ox, oy = offsets[i] if i < len(offsets) else (random.randint(-10, 10), random.randint(-10, 10))
            p = LeafPiece(self.x + ox, self.y + oy, shapes[i], color_var=random.randint(-10, 10))
            pieces.append(p)
        return pieces

    def available_pieces(self):
        return [p for p in self.pieces if not p.deposited and p.carrier is None]

    def draw(self, surf):
        self.wobble += 0.015
        a = math.radians(self.angle + math.sin(self.wobble) * 3)
        pts = []
        for i in range(10):
            ang = 2 * math.pi * i / 10 + a
            r = self.size * (1.0 if i % 2 == 0 else 0.55)
            pts.append((self.x + math.cos(ang) * r, self.y + math.sin(ang) * r))
        if len(pts) >= 3:
            avail = len(self.available_pieces())
            alpha_factor = max(0.0, avail / self.PIECES_PER_LEAF * 0.6)
            base_col = (max(0, min(255, int(C["leaf"][0] * alpha_factor))),
                        max(0, min(255, int(C["leaf"][1] * alpha_factor))),
                        max(0, min(255, int(C["leaf"][2] * alpha_factor))))
            if any(c > 0 for c in base_col):
                pygame.draw.polygon(surf, base_col, pts)
        for p in self.pieces:
            if not p.deposited:
                p.draw(surf)
        if self.selected:
            pulse = abs(math.sin(time.time() * 4))
            ring_col = (max(0, min(255, int(220 * pulse + 100))),
                        max(0, min(255, int(220 * pulse + 50))), 0)
            pygame.draw.circle(surf, ring_col, (int(self.x), int(self.y)), self.size + 6, 2)
            lbl = FONT_SM.render("HARVESTING", True, ring_col)
            surf.blit(lbl, (int(self.x) - lbl.get_width() // 2, int(self.y) - self.size - 18))

    def get_rect(self):
        return pygame.Rect(self.x - self.size, self.y - self.size,
                           self.size * 2, self.size * 2)

    def update(self):
        self.fully_harvested = all(p.deposited for p in self.pieces)


# ── Ant ──────────────────────────────────────────────────────────────────────
class Ant:
    def __init__(self, x, y, role: AntRole, colony_color):
        self.x = float(x)
        self.y = float(y)
        self.role = role
        self.colony_color = colony_color
        self.state = AntState.IDLE
        self.target_x = x
        self.target_y = y
        self.angle = random.uniform(0, 360)
        self.speed = 60 if role == AntRole.QUEEN else (45 if role == AntRole.WORKER else 38)
        self.idle_timer = random.uniform(0.5, 2.0)
        self.carrying_piece: Optional[LeafPiece] = None   # now carries a piece
        self.assigned_piece: Optional[LeafPiece] = None   # piece we're heading to
        self.assigned_leaf: Optional[Leaf] = None         # parent leaf (for position)
        self.leg_phase = random.uniform(0, math.pi * 2)
        self.size = 12 if role == AntRole.QUEEN else (7 if role == AntRole.WORKER else 9)
        self.trail = PheromoneTrail()
        self.trail_timer = 0
        self.wander_timer = 0
        self.deposit_target = None
        self.selected = False
        self.path_noise = random.uniform(0, 100)
        self._deposit_pos_override = None
        self._deposit_at_entrance = False
        self._process_food_room = None
        self._keep_processing = False

    def body_color(self):
        if self.colony_color == "red":
            return C["red_ant"] if self.role != AntRole.QUEEN else C["queen_c"]
        return C["black_ant"] if self.role != AntRole.QUEEN else C["queen_c"]

    def dark_color(self):
        return C["red_dark"] if self.colony_color == "red" else C["black_dark"]

    def update(self, dt, bounds, rooms, storage_pos):
        self.leg_phase += dt * 8
        self.trail_timer -= dt
        if self.trail_timer <= 0:
            self.trail_timer = 0.1
            if self.state in (AntState.FETCH_LEAF, AntState.CARRY_LEAF):
                self.trail.add(self.x, self.y)
        self.trail.update(dt)

        dx = self.target_x - self.x
        dy = self.target_y - self.y
        dist = math.hypot(dx, dy)

        # Use a wider arrive threshold when fetching a piece — piece positions have offsets
        arrive_dist = 18 if self.state == AntState.FETCH_LEAF else 3
        if dist > arrive_dist:
            spd = self.speed * dt
            noise_angle = math.sin(self.path_noise + time.time() * 0.5) * 0.3
            self.path_noise += dt * 0.2
            move_angle = math.atan2(dy, dx) + noise_angle
            self.x += math.cos(move_angle) * spd
            self.y += math.sin(move_angle) * spd
            self.angle = math.degrees(math.atan2(dy, dx))
        else:
            self._on_arrive(rooms, storage_pos, bounds)

        self.x = max(bounds[0] + 5, min(bounds[2] - 5, self.x))
        self.y = max(bounds[1] + 5, min(bounds[3] - 5, self.y))

        # Keep carried piece on top of ant head
        if self.carrying_piece:
            self.carrying_piece.x = self.x
            self.carrying_piece.y = self.y - self.size - 5

    def _on_arrive(self, rooms, storage_pos, bounds):
        if self.state == AntState.IDLE:
            self.idle_timer -= 0.016
            if self.idle_timer <= 0:
                self._set_wander(bounds)

        elif self.state == AntState.WANDER:
            self._set_wander(bounds)

        elif self.state == AntState.FETCH_LEAF:
            piece = self.assigned_piece
            # Piece is pre-reserved with being_carried=True, carrier=self
            if piece and not piece.deposited and piece.carrier is self:
                self.carrying_piece = piece
                self.state = AntState.CARRY_LEAF
                override = getattr(self, '_deposit_pos_override', None)
                if override:
                    self.target_x = override[0] + random.randint(-15, 15)
                    self.target_y = override[1] + random.randint(-10, 10)
                    self.deposit_target = None
                    self._deposit_at_entrance = True
                else:
                    leaf_room = next((r for r in rooms if r.rtype == RoomType.LEAF), None)
                    store_room = next((r for r in rooms if r.rtype == RoomType.STORAGE), None)
                    target = leaf_room or store_room
                    if target:
                        self.target_x = target.cx() + random.randint(-20, 20)
                        self.target_y = target.cy() + random.randint(-10, 10)
                        self.deposit_target = target
                        self._deposit_at_entrance = False
                    else:
                        piece.being_carried = False
                        piece.carrier = None
                        self.carrying_piece = None
                        self.state = AntState.IDLE
            else:
                # Piece deposited or stolen — release and go idle
                if piece and piece.carrier is self:
                    piece.being_carried = False
                    piece.carrier = None
                self.assigned_piece = None
                self.assigned_leaf = None
                self.state = AntState.IDLE

        elif self.state == AntState.CARRY_LEAF:
            piece = self.carrying_piece
            if piece:
                at_entrance = getattr(self, '_deposit_at_entrance', False)
                if at_entrance:
                    # Outside: arrived at entrance — find leaf room in rooms list and deposit
                    leaf_room = next((r for r in rooms if r.rtype == RoomType.LEAF), None)
                    store_room = next((r for r in rooms if r.rtype == RoomType.STORAGE), None)
                    target = leaf_room or store_room
                    if target:
                        piece.being_carried = False
                        piece.carrier = None
                        piece.deposited = True
                        piece.x = target.rect.x + random.randint(15, max(16, target.rect.w - 15))
                        piece.y = target.rect.y + random.randint(25, max(26, target.rect.h - 15))
                        target.leaves.append(piece)
                    self._deposit_at_entrance = False
                elif self.deposit_target:
                    piece.being_carried = False
                    piece.carrier = None
                    piece.deposited = True
                    piece.x = self.deposit_target.rect.x + random.randint(15, max(16, self.deposit_target.rect.w - 15))
                    piece.y = self.deposit_target.rect.y + random.randint(25, max(26, self.deposit_target.rect.h - 15))
                    self.deposit_target.leaves.append(piece)
            self.carrying_piece = None
            self.deposit_target = None
            self.assigned_piece = None
            self.assigned_leaf = None
            self._deposit_pos_override = None
            self.state = AntState.IDLE
            self._set_wander(bounds)

        elif self.state == AntState.DEPOSIT:
            self.state = AntState.IDLE

        elif self.state == AntState.PROCESS_LEAF:
            piece = self.assigned_piece
            if piece and not piece.deposited and piece.carrier is self:
                self.carrying_piece = piece
                self.state = AntState.PROCESS_CARRY
                food_room = getattr(self, '_process_food_room', None)
                if food_room:
                    self.target_x = food_room.cx() + random.randint(-20, 20)
                    self.target_y = food_room.cy() + random.randint(-10, 10)
                else:
                    piece.being_carried = False
                    piece.carrier = None
                    self.carrying_piece = None
                    self.state = AntState.IDLE
            else:
                if piece and piece.carrier is self:
                    piece.being_carried = False
                    piece.carrier = None
                self.assigned_piece = None
                self.state = AntState.IDLE

        elif self.state == AntState.PROCESS_CARRY:
            piece = self.carrying_piece
            food_room = getattr(self, '_process_food_room', None)
            if piece and food_room:
                for r in rooms:
                    if piece in r.leaves:
                        r.leaves.remove(piece)
                        break
                piece.being_carried = False
                piece.carrier = None
                piece.deposited = True
                food_room.mushrooms.append({
                    "x": food_room.rect.x + random.randint(20, max(21, food_room.rect.w - 20)),
                    "y": food_room.rect.y + random.randint(30, max(31, food_room.rect.h - 30)),
                    "grow": 0.0
                })
                food_room._pending_food = getattr(food_room, '_pending_food', 0) + 1
            self.carrying_piece = None
            self.assigned_piece = None

            # If keep_processing, grab the next available piece immediately
            if getattr(self, '_keep_processing', False) and food_room:
                next_piece = None
                for r in rooms:
                    if r.rtype in (RoomType.LEAF, RoomType.STORAGE):
                        for p in r.leaves:
                            if p.carrier is None:
                                next_piece = p
                                break
                    if next_piece:
                        break
                if next_piece:
                    next_piece.deposited = False
                    next_piece.being_carried = True
                    next_piece.carrier = self
                    self.assigned_piece = next_piece
                    self._process_food_room = food_room
                    self.state = AntState.PROCESS_LEAF
                    self.target_x = next_piece.x
                    self.target_y = next_piece.y
                    return  # don't fall through to idle
                else:
                    # No more pieces — stop looping
                    self._keep_processing = False
                    self._process_food_room = None

            self.state = AntState.IDLE
            self._set_wander(bounds)

    def _set_wander(self, bounds):
        self.state = AntState.WANDER
        margin = 20
        self.target_x = random.uniform(bounds[0] + margin, bounds[2] - margin)
        self.target_y = random.uniform(bounds[1] + margin, bounds[3] - margin)
        self.wander_timer = random.uniform(1.0, 3.0)

    def command_process(self, piece: "LeafPiece", food_room):
        self.assigned_piece = piece
        self._process_food_room = food_room
        self._keep_processing = True
        piece.deposited = False
        piece.being_carried = True
        piece.carrier = self
        self.state = AntState.PROCESS_LEAF
        self.target_x = piece.x
        self.target_y = piece.y

    def command_fetch_piece(self, piece: "LeafPiece", leaf: "Leaf", rooms, deposit_pos=None):
        self.assigned_piece = piece
        self.assigned_leaf = leaf
        self._deposit_pos_override = deposit_pos
        self.state = AntState.FETCH_LEAF
        piece.being_carried = True
        piece.carrier = self
        self.target_x = piece.x
        self.target_y = piece.y
        self.assigned_piece = piece
        self.assigned_leaf = leaf
        self._deposit_pos_override = deposit_pos
        self.state = AntState.FETCH_LEAF
        # Reserve immediately — marks it as taken so no other ant targets it
        piece.being_carried = True
        piece.carrier = self
        # Target the piece exactly (wider arrive threshold handles the gap)
        self.target_x = piece.x
        self.target_y = piece.y

    def draw(self, surf, show_trail=True):
        if show_trail:
            self.trail.draw(surf)
        a = math.radians(self.angle)
        s = self.size
        bc = self.body_color()
        dc = self.dark_color()

        if self.selected:
            pygame.draw.circle(surf, C["gold"], (int(self.x), int(self.y)), s + 5, 2)

        for i in range(3):
            offset = (i - 1) * s * 0.6
            leg_swing = math.sin(self.leg_phase + i * 1.2) * s * 0.9
            lx = self.x + math.cos(a + math.pi / 2) * offset - math.sin(a) * leg_swing
            ly = self.y + math.sin(a + math.pi / 2) * offset - math.cos(a) * leg_swing * 0.5
            attach_l = (int(self.x + math.cos(a + math.pi / 2) * s * 0.4 + math.cos(a) * offset * 0.3),
                        int(self.y + math.sin(a + math.pi / 2) * s * 0.4 + math.sin(a) * offset * 0.3))
            pygame.draw.line(surf, dc, attach_l, (int(lx), int(ly)), 1)
            rx = self.x - math.cos(a + math.pi / 2) * offset - math.sin(a) * (-leg_swing)
            ry = self.y - math.sin(a + math.pi / 2) * offset - math.cos(a) * (-leg_swing) * 0.5
            attach_r = (int(self.x - math.cos(a + math.pi / 2) * s * 0.4 + math.cos(a) * offset * 0.3),
                        int(self.y - math.sin(a + math.pi / 2) * s * 0.4 + math.sin(a) * offset * 0.3))
            pygame.draw.line(surf, dc, attach_r, (int(rx), int(ry)), 1)

        ab_x = self.x - math.cos(a) * s * 0.9
        ab_y = self.y - math.sin(a) * s * 0.9
        ab_r = int(s * 0.85) if self.role == AntRole.QUEEN else int(s * 0.7)
        pygame.draw.circle(surf, bc, (int(ab_x), int(ab_y)), ab_r)
        pygame.draw.circle(surf, dc, (int(ab_x), int(ab_y)), ab_r, 1)

        th_r = int(s * 0.55)
        pygame.draw.circle(surf, bc, (int(self.x), int(self.y)), th_r)

        hd_x = self.x + math.cos(a) * s * 0.85
        hd_y = self.y + math.sin(a) * s * 0.85
        hd_r = int(s * 0.5) if self.role == AntRole.QUEEN else int(s * 0.45)
        pygame.draw.circle(surf, bc, (int(hd_x), int(hd_y)), hd_r)
        pygame.draw.circle(surf, dc, (int(hd_x), int(hd_y)), hd_r, 1)

        for side in [-1, 1]:
            ant_base_x = hd_x + math.cos(a) * hd_r * 0.8
            ant_base_y = hd_y + math.sin(a) * hd_r * 0.8
            ant_tip_x = ant_base_x + math.cos(a + side * 0.6) * s * 0.9
            ant_tip_y = ant_base_y + math.sin(a + side * 0.6) * s * 0.9
            pygame.draw.line(surf, dc, (int(ant_base_x), int(ant_base_y)),
                             (int(ant_tip_x), int(ant_tip_y)), 1)
            pygame.draw.circle(surf, dc, (int(ant_tip_x), int(ant_tip_y)), 2)

        if self.role == AntRole.QUEEN:
            crown_x, crown_y = int(hd_x), int(hd_y - hd_r - 2)
            for i in range(3):
                px = crown_x + (i - 1) * 4
                pygame.draw.line(surf, C["gold"], (px, crown_y), (px, crown_y - 5 - i * 2), 2)
            pygame.draw.circle(surf, C["gold"], (crown_x, crown_y - 3), 2)

        # Draw carried piece above ant
        if self.carrying_piece:
            self.carrying_piece.draw(surf)


# ── Egg ──────────────────────────────────────────────────────────────────────
class Egg:
    def __init__(self, x, y):
        self.x = x
        self.y = y
        self.hatch_time = 15.0  # seconds
        self.max_time = 15.0
        self.wobble = random.uniform(0, math.pi * 2)
        self.ready = False

    def update(self, dt, nursery_bonus=1.0):
        self.wobble += dt * 1.5
        self.hatch_time -= dt * nursery_bonus
        if self.hatch_time <= 0:
            self.ready = True

    def draw(self, surf):
        progress = 1.0 - (self.hatch_time / self.max_time)
        wobble_r = math.sin(self.wobble) * 1.5 * progress
        # Egg shape
        egg_rect = pygame.Rect(self.x - 7, self.y - 10, 14, 18)
        col = (*C["egg_c"][:3],)
        if progress > 0.8:
            # Cracking effect
            col = (220, 200, 150)
            pygame.draw.line(surf, (150, 130, 100),
                             (self.x + int(wobble_r), self.y - 3),
                             (self.x + 2 + int(wobble_r), self.y + 4), 1)

        pygame.draw.ellipse(surf, col, egg_rect)
        pygame.draw.ellipse(surf, (180, 170, 140), egg_rect, 1)

        # Progress ring
        if progress > 0:
            arc_rect = pygame.Rect(self.x - 11, self.y - 11, 22, 22)
            end_angle = -math.pi / 2 + progress * 2 * math.pi
            try:
                pygame.draw.arc(surf, C["gold"], arc_rect, -math.pi / 2, end_angle, 2)
            except:
                pass


# ── Room ──────────────────────────────────────────────────────────────────────
class Room:
    def __init__(self, rtype: RoomType, rect: pygame.Rect):
        self.rtype = rtype
        self.rect = rect
        self.leaves: List[Leaf] = []
        self.food_count = 0
        self.mushrooms: List[dict] = []  # {x, y, grow}
        self.hover_alpha = 0
        self.particles: List[Particle] = []
        self.glow = 0.0

    def cx(self):
        return self.rect.centerx

    def cy(self):
        return self.rect.centery

    def update(self, dt):
        self.hover_alpha = max(0, self.hover_alpha - dt * 200)
        self.glow = (math.sin(time.time() * 2) + 1) * 0.5
        self.particles = [p for p in self.particles if p.life > 0]
        for p in self.particles:
            p.update(dt)
        for m in self.mushrooms:
            m["grow"] = min(1.0, m.get("grow", 0) + dt * 0.3)

    def draw(self, surf):
        col = ROOM_COLORS[self.rtype]
        pygame.draw.rect(surf, col, self.rect, border_radius=8)
        glow_col = tuple(min(255, int(c + self.glow * 40)) for c in col)
        pygame.draw.rect(surf, glow_col, self.rect, 2, border_radius=8)

        lbl = FONT_SM.render(self.rtype.value, True, C["white"])
        surf.blit(lbl, (self.rect.x + 4, self.rect.y + 4))

        # Draw leaf pieces stored here
        for piece in self.leaves[-12:]:
            piece.draw(surf)

        # Draw mushrooms
        for m in self.mushrooms:
            g = m.get("grow", 1.0)
            self._draw_mushroom(surf, m["x"], m["y"], g)

        # Leaf room: show piece count
        if self.rtype == RoomType.LEAF and self.leaves:
            cnt = FONT_SM.render(f"{len(self.leaves)} pieces stored", True, (180, 220, 180))
            surf.blit(cnt, (self.rect.x + 4, self.rect.bottom - 16))

        for p in self.particles:
            p.draw(surf)

    def _draw_mushroom(self, surf, x, y, grow):
        # Cap
        cap_h = int(14 * grow)
        cap_w = int(18 * grow)
        if cap_w > 0 and cap_h > 0:
            cap_rect = pygame.Rect(x - cap_w, y - cap_h - int(8 * grow), cap_w * 2, cap_h)
            pygame.draw.ellipse(surf, C["mushroom"], cap_rect)
            # Spots
            for sx, sy in [(-4, -5), (3, -8), (-1, -3)]:
                if grow > 0.5:
                    pygame.draw.circle(surf, (240, 220, 180),
                                       (x + int(sx * grow), y + int(sy * grow)), max(1, int(3 * grow)))
            # Stem
            stem_h = int(10 * grow)
            stem_w = int(5 * grow)
            if stem_h > 0 and stem_w > 0:
                stem_rect = pygame.Rect(x - stem_w // 2, y - stem_h, stem_w, stem_h)
                pygame.draw.rect(surf, (200, 180, 140), stem_rect, border_radius=2)

    def add_food_particle(self):
        for _ in range(8):
            p = Particle(
                x=self.cx(), y=self.cy(),
                vx=random.uniform(-40, 40),
                vy=random.uniform(-80, -20),
                life=1.5, max_life=1.5,
                color=C["food_glow"],
                size=5
            )
            self.particles.append(p)


# ── Queen ─────────────────────────────────────────────────────────────────────
class Queen:
    def __init__(self, x, y, colony_color):
        self.ant = Ant(x, y, AntRole.QUEEN, colony_color)
        self.egg_timer = 12.0
        self.egg_interval = 12.0
        self.eggs: List[Egg] = []
        self.max_eggs = 6
        self.food = 0  # colony food supply

    def update(self, dt, queen_room_rect, nursery_bonus=1.0, egg_discount=0):
        self.ant.x = queen_room_rect.centerx + math.sin(time.time() * 0.5) * 20
        self.ant.y = queen_room_rect.centery + math.cos(time.time() * 0.3) * 10
        self.ant.leg_phase += dt * 3

        self.egg_timer -= dt
        egg_cost = max(0, 1 - egg_discount)
        if self.egg_timer <= 0 and len(self.eggs) < self.max_eggs and self.food >= egg_cost:
            self.food -= egg_cost
            ex = queen_room_rect.x + random.randint(20, queen_room_rect.width - 20)
            ey = queen_room_rect.y + random.randint(30, queen_room_rect.height - 20)
            self.eggs.append(Egg(ex, ey))
            self.egg_timer = self.egg_interval

        hatched = []
        for egg in self.eggs:
            egg.update(dt, nursery_bonus)
            if egg.ready:
                hatched.append(egg)
        return hatched

    def draw(self, surf):
        self.ant.draw(surf)
        for egg in self.eggs:
            egg.draw(surf)


# ── Outside World ──────────────────────────────────────────────────────────────
class OutsideWorld:
    def __init__(self, colony_color):
        self.colony_color = colony_color
        self.leaves: set = set()
        self.spawn_timer = 0
        self.spawn_interval = 8.0
        self.cloud_x = [random.uniform(0, W) for _ in range(5)]
        self.cloud_speeds = [random.uniform(10, 25) for _ in range(5)]
        self.trees = [(random.randint(80, W - 80), H // 2 - random.randint(20, 60),
                       random.randint(25, 45)) for _ in range(8)]
        self.grass_tufts = [(random.randint(0, W), H // 2 + random.randint(5, 25))
                            for _ in range(40)]
        self.nest_entrance_rect = pygame.Rect(W // 2 - 50, H // 2 + 60, 100, 40)

    def update(self, dt, bigger_bite=False, scout_level=0):
        self.spawn_timer -= dt
        max_leaves = 12 + scout_level * 4
        if self.spawn_timer <= 0 and len(self.leaves) < max_leaves:
            margin = 80 + scout_level * 60
            lx = random.randint(margin, W - margin)
            ly = random.randint(H // 2 - 100, H // 2 + 50)
            if not self.nest_entrance_rect.collidepoint(lx, ly):
                pieces = 6 if bigger_bite else 4
                self.leaves.add(Leaf(lx, ly, pieces_override=pieces))
            self.spawn_timer = max(3.0, self.spawn_interval - scout_level * 1.5)
        for cloud in range(5):
            self.cloud_x[cloud] = (self.cloud_x[cloud] + self.cloud_speeds[cloud] * dt) % (W + 200)
        for leaf in list(self.leaves):
            leaf.update()
            if leaf.fully_harvested:
                self.leaves.discard(leaf)

    def draw(self, surf):
        # Sky gradient
        for y in range(H // 2):
            factor = y / (H // 2)
            r = int(135 + factor * 30)
            g = int(195 + factor * 10)
            b = int(120 + factor * (-20))
            pygame.draw.line(surf, (r, g, b), (0, y), (W, y))

        # Ground
        pygame.draw.rect(surf, C["grass"], (0, H // 2, W, H // 2))
        for i in range(0, W, 4):
            shade = random.randint(0, 15)
            pygame.draw.line(surf, (45 + shade, 100 + shade, 45),
                             (i, H // 2), (i, H // 2 + 3))

        # Clouds
        for i, cx in enumerate(self.cloud_x):
            self._draw_cloud(surf, cx - 100, 50 + i * 30)

        # Trees
        for tx, ty, tr in self.trees:
            pygame.draw.rect(surf, (100, 65, 30), (tx - 5, ty + 20, 10, 40))
            pygame.draw.circle(surf, (34, 100, 34), (tx, ty), tr)
            pygame.draw.circle(surf, (45, 120, 45), (tx - 8, ty - 5), tr - 8)

        # Grass tufts
        for gx, gy in self.grass_tufts:
            for j in range(3):
                angle = math.radians(-60 + j * 30)
                pygame.draw.line(surf, (55, 130, 55),
                                 (gx, gy), (int(gx + math.cos(angle) * 8), int(gy - 12)), 1)

        # Nest entrance
        pygame.draw.ellipse(surf, C["dirt"], self.nest_entrance_rect)
        pygame.draw.ellipse(surf, (80, 50, 15), self.nest_entrance_rect, 3)
        ent_lbl = FONT_SM.render("▼ NEST", True, C["white"])
        surf.blit(ent_lbl, (self.nest_entrance_rect.centerx - ent_lbl.get_width() // 2,
                             self.nest_entrance_rect.centery - 7))

        # Soil underground hint
        pygame.draw.rect(surf, C["soil"], (0, H - 60, W, 60))
        for i in range(0, W, 40):
            pygame.draw.circle(surf, C["soil2"], (i, H - 40), 8)

    def _draw_cloud(self, surf, cx, cy):
        for ox, oy, r in [(0, 0, 25), (30, -10, 30), (60, 0, 20), (15, -15, 22), (45, -12, 18)]:
            pygame.draw.circle(surf, (240, 245, 255), (int(cx + ox), int(cy + oy)), r)


# ── Nest View ──────────────────────────────────────────────────────────────────
class NestView:
    # World-space origin for the nest canvas (larger than screen)
    WORLD_W = 2400
    WORLD_H = 2000

    def __init__(self, colony_color):
        self.colony_color = colony_color
        self.rooms: List[Room] = []
        self.tunnels = []  # list of (x1,y1, x2,y2) in world coords

        # Camera offset (top-left of viewport in world space)
        self.cam_x = self.WORLD_W // 2 - W // 2
        self.cam_y = 100
        self.dragging_cam = False
        self.drag_start = (0, 0)
        self.cam_start = (0, 0)

        # Pre-generate soil texture patches (world space)
        self.soil_patches = [
            (random.randint(0, self.WORLD_W),
             random.randint(0, self.WORLD_H),
             random.randint(-8, 8))
            for _ in range(6000)
        ]

        self._init_rooms()

    # ── coordinate helpers ──
    def w2s(self, wx, wy):
        """World → screen"""
        return wx - self.cam_x, wy - self.cam_y

    def s2w(self, sx, sy):
        """Screen → world"""
        return sx + self.cam_x, sy + self.cam_y

    def rect_w2s(self, rect: pygame.Rect) -> pygame.Rect:
        sx, sy = self.w2s(rect.x, rect.y)
        return pygame.Rect(sx, sy, rect.w, rect.h)

    # ── layout ──
    def _init_rooms(self):
        cx = self.WORLD_W // 2
        queen_rect = pygame.Rect(cx - 120, 180, 240, 160)
        self.rooms.append(Room(RoomType.QUEEN, queen_rect))

        storage_rect = pygame.Rect(cx - 100, 420, 200, 130)
        self.rooms.append(Room(RoomType.STORAGE, storage_rect))

        self._gen_tunnels()

    def _find_free_spot(self, rw, rh) -> pygame.Rect:
        """Place a new room mostly downward with slight horizontal drift, no overlaps."""
        # Find the lowest existing room bottom as baseline
        max_bottom = max(r.rect.bottom for r in self.rooms)
        cx = self.WORLD_W // 2

        for _ in range(80):
            # Mostly straight down, small horizontal jitter
            x_drift = random.randint(-120, 120)
            y_gap = random.randint(60, 110)
            nx = cx - rw // 2 + x_drift
            ny = max_bottom + y_gap
            candidate = pygame.Rect(nx, ny, rw, rh)

            # World bounds
            if (candidate.x < 80 or candidate.right > self.WORLD_W - 80 or
                    candidate.y < 80 or candidate.bottom > self.WORLD_H - 80):
                continue

            # No overlap (with generous padding)
            padded = candidate.inflate(30, 30)
            if not any(padded.colliderect(r.rect) for r in self.rooms):
                return candidate

        # Hard fallback: exactly centered below lowest room
        return pygame.Rect(cx - rw // 2, max_bottom + 80, rw, rh)

    def add_room(self, rtype: RoomType) -> Room:
        sizes = {
            RoomType.LEAF:     (200, 130),
            RoomType.FOOD:     (190, 130),
            RoomType.NURSERY:  (180, 120),
            RoomType.BARRACKS: (180, 120),
        }
        rw, rh = sizes.get(rtype, (180, 120))
        rect = self._find_free_spot(rw, rh)
        room = Room(rtype, rect)
        self.rooms.append(room)
        # Connect tunnel from the nearest existing room
        parent = min(self.rooms[:-1], key=lambda r: math.hypot(r.cx() - room.cx(), r.cy() - room.cy()))
        self.tunnels.append((parent.cx(), parent.cy(), room.cx(), room.cy(), parent, room))
        return room

    def _gen_tunnels(self):
        """Initial tunnels between starting rooms."""
        self.tunnels = []
        q = self.rooms[0]
        s = self.rooms[1]
        self.tunnels.append((q.cx(), q.cy(), s.cx(), s.cy(), q, s))

    def get_room(self, rtype: RoomType) -> Optional[Room]:
        return next((r for r in self.rooms if r.rtype == rtype), None)

    def update(self, dt):
        for r in self.rooms:
            r.update(dt)

    # ── camera drag ──
    def start_cam_drag(self, screen_pos):
        self.dragging_cam = True
        self.drag_start = screen_pos
        self.cam_start = (self.cam_x, self.cam_y)

    def update_cam_drag(self, screen_pos):
        if self.dragging_cam:
            dx = screen_pos[0] - self.drag_start[0]
            dy = screen_pos[1] - self.drag_start[1]
            self.cam_x = max(0, min(self.WORLD_W - W, self.cam_start[0] - dx))
            self.cam_y = max(0, min(self.WORLD_H - H, self.cam_start[1] - dy))

    def stop_cam_drag(self):
        self.dragging_cam = False

    # ── draw ──
    def draw(self, surf, queen: Queen, workers: List[Ant], soldiers: List[Ant] = None):
        surf.fill(C["soil"])

        # Soil texture (only patches in view)
        for px, py, shade in self.soil_patches:
            sx, sy = self.w2s(px, py)
            if -20 < sx < W + 20 and -20 < sy < H + 20:
                col = (max(0, min(255, C["soil"][0] + shade)),
                       max(0, min(255, C["soil"][1] + shade)),
                       max(0, min(255, C["soil"][2] + shade)))
                pygame.draw.circle(surf, col, (sx, sy), 10)

        # Tunnels — drawn as rounded, organic-looking tubes
        for x1, y1, x2, y2, *_ in self.tunnels:
            sx1, sy1 = self.w2s(x1, y1)
            sx2, sy2 = self.w2s(x2, y2)
            # Outer dark tunnel
            pygame.draw.line(surf, C["tunnel"], (sx1, sy1), (sx2, sy2), 26)
            # Inner lighter dirt channel
            pygame.draw.line(surf, C["soil2"], (sx1, sy1), (sx2, sy2), 18)
            # Floor highlight
            pygame.draw.line(surf, (max(0,C["soil2"][0]-10),
                                    max(0,C["soil2"][1]-8),
                                    max(0,C["soil2"][2]-4)),
                             (sx1, sy1), (sx2, sy2), 8)

        # Rooms
        for room in self.rooms:
            sr = self.rect_w2s(room.rect)
            _draw_room_at(surf, room, sr)
            # Show soldier count on barracks
            if room.rtype == RoomType.BARRACKS and soldiers:
                cnt = FONT_SM.render(f"{len(soldiers)} soldiers  |  Click to train (3🍄)", True, (200, 120, 100))
                surf.blit(cnt, (sr.x + 4, sr.bottom - 16))

        # Queen + eggs (translate positions)
        _draw_queen_translated(surf, queen, self.cam_x, self.cam_y)

        # Workers
        for ant in workers:
            _draw_ant_translated(surf, ant, self.cam_x, self.cam_y)

        # Soldiers (drawn in barracks area)
        if soldiers:
            for ant in soldiers:
                _draw_ant_translated(surf, ant, self.cam_x, self.cam_y)

        # Camera drag hint
        hint = FONT_SM.render("Left-drag to pan", True, (120, 100, 70))
        surf.blit(hint, (W - hint.get_width() - 10, H - 18))


# ── Camera-translated draw helpers ────────────────────────────────────────────
def _draw_room_at(surf, room: "Room", screen_rect: pygame.Rect):
    """Draw a room at a given screen rect (camera-translated)."""
    col = ROOM_COLORS[room.rtype]
    pygame.draw.rect(surf, col, screen_rect, border_radius=8)
    glow_col = tuple(min(255, int(c + room.glow * 40)) for c in col)
    pygame.draw.rect(surf, glow_col, screen_rect, 2, border_radius=8)

    lbl = FONT_SM.render(room.rtype.value, True, C["white"])
    surf.blit(lbl, (screen_rect.x + 4, screen_rect.y + 4))

    # Leaf pieces (offset by cam)
    ox = screen_rect.x - room.rect.x
    oy = screen_rect.y - room.rect.y
    for piece in room.leaves[-12:]:
        # Temporarily shift piece position for drawing
        piece.x += ox
        piece.y += oy
        piece.draw(surf)
        piece.x -= ox
        piece.y -= oy

    # Mushrooms
    for m in room.mushrooms:
        room._draw_mushroom(surf, m["x"] + ox, m["y"] + oy, m.get("grow", 1.0))

    # Food room: "Process all" button
    if room.rtype == RoomType.FOOD:
        btn = pygame.Rect(screen_rect.x + 4, screen_rect.bottom - 26, screen_rect.w - 8, 20)
        pulse = abs(math.sin(time.time() * 3))
        bcol = (int(40 + pulse*30), int(130 + pulse*40), int(40 + pulse*30))
        pygame.draw.rect(surf, bcol, btn, border_radius=4)
        bl = FONT_SM.render("Send workers: process leaves", True, (220, 255, 220))
        surf.blit(bl, (btn.centerx - bl.get_width() // 2, btn.centery - bl.get_height() // 2))
        cnt = FONT_SM.render(f"{len(room.leaves)} pieces", True, (180, 220, 180))
        surf.blit(cnt, (screen_rect.x + 4, screen_rect.bottom - 16))

    # Farm room hint
    if room.rtype == RoomType.FARM:
        hint = FONT_SM.render("Passive food every 20s", True, (140, 200, 120))
        surf.blit(hint, (screen_rect.x + 4, screen_rect.bottom - 16))

    # Hospital room hint
    if room.rtype == RoomType.HOSPITAL:
        hint = FONT_SM.render("+30% soldier HP in battle", True, (120, 200, 200))
        surf.blit(hint, (screen_rect.x + 4, screen_rect.bottom - 16))

    # Tunnels room hint
    if room.rtype == RoomType.TUNNELS:
        hint = FONT_SM.render("All ants +25% speed", True, (200, 180, 120))
        surf.blit(hint, (screen_rect.x + 4, screen_rect.bottom - 16))

    for p in room.particles:
        p.draw(surf)


def _draw_ant_translated(surf, ant: "Ant", cam_x, cam_y):
    ant.x -= cam_x
    ant.y -= cam_y
    if ant.carrying_piece:
        ant.carrying_piece.x -= cam_x
        ant.carrying_piece.y -= cam_y
    ant.draw(surf, show_trail=False)
    ant.x += cam_x
    ant.y += cam_y
    if ant.carrying_piece:
        ant.carrying_piece.x += cam_x
        ant.carrying_piece.y += cam_y


def _draw_queen_translated(surf, queen: "Queen", cam_x, cam_y):
    queen.ant.x -= cam_x
    queen.ant.y -= cam_y
    queen.ant.draw(surf)
    queen.ant.x += cam_x
    queen.ant.y += cam_y
    for egg in queen.eggs:
        ex, ey = egg.x - cam_x, egg.y - cam_y
        if -20 < ex < W + 20 and -20 < ey < H + 20:
            egg.x -= cam_x
            egg.y -= cam_y
            egg.draw(surf)
            egg.x += cam_x
            egg.y += cam_y


# ── HUD / UI ──────────────────────────────────────────────────────────────────
def draw_hud(surf, game):
    # Top bar
    panel = pygame.Surface((W, 60), pygame.SRCALPHA)
    panel.fill((15, 8, 3, 200))
    surf.blit(panel, (0, 0))
    pygame.draw.line(surf, C["ui_border"], (0, 60), (W, 60), 1)

    # Colony color indicator
    ant_col = C["red_ant"] if game.colony_color == "red" else C["black_ant"]
    pygame.draw.circle(surf, ant_col, (30, 30), 14)
    pygame.draw.circle(surf, C["gold"], (30, 30), 14, 2)

    # Stats
    stats = [
        ("🏠", f"Ants: {len(game.workers) + 1}"),
        ("🥚", f"Eggs: {len(game.queen.eggs)}"),
        ("🍄", f"Food: {game.queen.food}"),
        ("🍃", f"Pieces: {sum(len(r.leaves) for r in game.nest.rooms)}"),
    ]
    for i, (icon, text) in enumerate(stats):
        lbl = FONT_MD.render(text, True, C["white"])
        surf.blit(lbl, (70 + i * 170, 20))

    # View toggle
    view_text = "[ OUTSIDE ]" if game.state == GameState.NEST else "[ INSIDE NEST ]"
    v_lbl = FONT_MD.render(view_text, True, C["gold"])
    surf.blit(v_lbl, (W - 200, 20))

    # Shop button
    shop_lbl = FONT_MD.render("[ SHOP ]", True, C["gold"])
    surf.blit(shop_lbl, (W - 440, 20))

    # Upgrades button
    upg_lbl = FONT_MD.render("[ UPGRADES ]", True, (180, 140, 220))
    surf.blit(upg_lbl, (W - 590, 20))

    # Battle button — only when barracks built
    if hasattr(game, 'nest') and game.nest and game.nest.get_room(RoomType.BARRACKS):
        n_sol = len(game.soldiers) if hasattr(game, 'soldiers') else 0
        ready = n_sol >= MIN_SOLDIERS
        bcol = (220, 80, 60) if ready else (140, 70, 55)
        b_lbl = FONT_MD.render(f"[ \u2694 BATTLE ({n_sol}/{MIN_SOLDIERS}) ]", True, bcol)
        surf.blit(b_lbl, (W - 800, 20))

    # View label
    view_label = "NEST VIEW" if game.state == GameState.NEST else "OUTSIDE"
    if hasattr(game, 'auto_harvest') and game.auto_harvest and game.state == GameState.OUTSIDE:
        view_label += "  ⚡ AUTO"
    vl = FONT_SM.render(view_label, True, (180, 180, 180))
    surf.blit(vl, (10, H - 20))

    # Controls hint
    hint = FONT_SM.render("Tab: switch view  |  Click leaf = send workers  |  M: turn off music", True, (140, 140, 120))
    surf.blit(hint, (W // 2 - hint.get_width() // 2, H - 20))

    # Music indicator
    music_on = SFX and SFX.music_playing
    mic = FONT_SM.render("Music ON" if music_on else "Music OFF", True, C["gold"] if music_on else (100, 100, 100))
    surf.blit(mic, (W - 60, H - 20))


# ── Shop Screen ───────────────────────────────────────────────────────────────
# ── Upgrade System ────────────────────────────────────────────────────────────
UPGRADES = {
    "auto_harvest": {
        "name":   "Auto Harvest",
        "icon":   "🍃",
        "desc":   "Workers automatically detect\nand harvest nearby leaves\nwithout being commanded.",
        "cost":   [8, 0, 0],
        "levels": 1, "max": 1,
        "effect": "Workers collect leaves on\ntheir own every 2.5s.",
    },
    "faster_legs": {
        "name":   "Faster Legs",
        "icon":   "⚡",
        "desc":   "Workers move 40% faster\nper level. More trips\nper minute.",
        "cost":   [6, 0, 0],
        "levels": 3, "max": 3,
        "effect": "+40% worker speed per level.",
    },
    "bigger_bite": {
        "name":   "Bigger Bite",
        "icon":   "🦷",
        "desc":   "Each leaf yields 6 pieces\ninstead of 4. More food\nfrom every leaf found.",
        "cost":   [10, 0, 0],
        "levels": 1, "max": 1,
        "effect": "Leaves break into 6 pieces.",
    },
    "queen_boost": {
        "name":   "Royal Appetite",
        "icon":   "👑",
        "desc":   "Queen lays eggs twice as\nfast when fed. Grow your\ncolony quicker.",
        "cost":   [12, 0, 0],
        "levels": 1, "max": 1,
        "effect": "Queen egg interval halved.",
    },
    "scout_range": {
        "name":   "Scout Range",
        "icon":   "🔭",
        "desc":   "Workers roam a wider area\noutside, finding leaves\nfurther from the nest.",
        "cost":   [5, 0, 0],
        "levels": 2, "max": 2,
        "effect": "Outside roam area +50% per level.",
    },
    "leaf_capacity": {
        "name":   "Leaf Capacity",
        "icon":   "📦",
        "desc":   "Leaf Room holds more pieces.\nExpand your reserves\nfor busy seasons.",
        "cost":   [7, 0, 0],
        "levels": 3, "max": 3,
        "effect": "+20 piece capacity per level.",
    },
    "armored_shell": {
        "name":   "Armored Shell",
        "icon":   "🛡",
        "desc":   "Soldiers start with more HP.\nSurvive longer in battle\nand win more fights.",
        "cost":   [10, 0, 0],
        "levels": 3, "max": 3,
        "effect": "+30 HP per soldier per level.",
    },
    "battle_frenzy": {
        "name":   "Battle Frenzy",
        "icon":   "⚔",
        "desc":   "Soldiers attack faster\nand deal more damage.\nDominate the battlefield.",
        "cost":   [12, 0, 0],
        "levels": 2, "max": 2,
        "effect": "+25% attack speed, +5 dmg per level.",
    },
    "deep_roots": {
        "name":   "Deep Roots",
        "icon":   "🌱",
        "desc":   "Queen can hold more eggs\nat once. Bigger batches\nmean faster growth.",
        "cost":   [9, 0, 0],
        "levels": 3, "max": 3,
        "effect": "+3 max eggs per level.",
    },
    "poison_glands": {
        "name":   "Poison Glands",
        "icon":   "☠",
        "desc":   "Soldiers deal 20% extra\ndamage in battle. A little\npoison goes a long way.",
        "cost":   [14, 0, 0],
        "levels": 1, "max": 1,
        "effect": "Soldiers deal +20% damage.",
    },
    "efficient_colony": {
        "name":   "Efficiency",
        "icon":   "⚙",
        "desc":   "Eggs cost 1 less food to\nlay. Queen breeds more\nwithout starving.",
        "cost":   [11, 0, 0],
        "levels": 2, "max": 2,
        "effect": "-1 food per egg per level.",
    },
    "mushroom_yield": {
        "name":   "Mushroom Yield",
        "icon":   "🍄",
        "desc":   "Each leaf piece deposited\nin the Food Lab gives\n+1 extra food.",
        "cost":   [8, 0, 0],
        "levels": 2, "max": 2,
        "effect": "+1 food per piece per level.",
    },
}

class UpgradeScreen:
    COLS = 4
    CARD_W, CARD_H = 188, 205

    def __init__(self):
        self.purchased: dict = {k: 0 for k in UPGRADES}
        self._layout()

    def _layout(self):
        pad = 16
        total_w = self.COLS * self.CARD_W + (self.COLS - 1) * pad
        sx = W // 2 - total_w // 2
        sy = 110
        self.rects = {}
        keys = list(UPGRADES.keys())
        for i, k in enumerate(keys):
            col = i % self.COLS
            row = i // self.COLS
            x = sx + col * (self.CARD_W + pad)
            y = sy + row * (self.CARD_H + pad)
            self.rects[k] = pygame.Rect(x, y, self.CARD_W, self.CARD_H)

    def can_afford(self, key, game):
        upg = UPGRADES[key]
        lvl = self.purchased[key]
        if lvl >= upg["max"]:
            return False
        # Cost scales with level
        base_food = upg["cost"][0]
        food_cost = base_food + lvl * (base_food // 2)
        return game.queen.food >= food_cost

    def food_cost(self, key):
        upg = UPGRADES[key]
        lvl = self.purchased[key]
        base = upg["cost"][0]
        return base + lvl * (base // 2)

    def buy(self, key, game):
        if not self.can_afford(key, game):
            return False
        cost = self.food_cost(key)
        game.queen.food -= cost
        self.purchased[key] += 1
        self._apply(key, game)
        SFX.play('build')
        return True

    def _apply(self, key, game):
        lvl = self.purchased[key]
        if key == "auto_harvest":
            game.auto_harvest = True
        elif key == "faster_legs":
            game.worker_speed_bonus = 1 + 0.4 * lvl
            for ant in game.workers:
                ant.speed = 45 * game.worker_speed_bonus
        elif key == "bigger_bite":
            game.bigger_bite = True
        elif key == "queen_boost":
            game.queen.egg_interval = max(4.0, 12.0 / (2 ** lvl))
        elif key == "scout_range":
            game.scout_range_level = lvl
        elif key == "leaf_capacity":
            game.leaf_capacity = 20 + lvl * 20
        elif key == "armored_shell":
            game.soldier_hp_bonus = lvl * 30
        elif key == "battle_frenzy":
            game.soldier_frenzy_level = lvl
        elif key == "deep_roots":
            game.queen.max_eggs = 6 + lvl * 3
        elif key == "poison_glands":
            game.soldier_poison = True
        elif key == "efficient_colony":
            game.egg_food_discount = lvl
        elif key == "mushroom_yield":
            game.mushroom_yield_bonus = lvl

    def draw(self, surf, game):
        overlay = pygame.Surface((W, H), pygame.SRCALPHA)
        overlay.fill((0, 0, 0, 210))
        surf.blit(overlay, (0, 0))

        title = FONT_LG.render("COLONY UPGRADES", True, C["gold"])
        surf.blit(title, (W // 2 - title.get_width() // 2, 55))
        sub = FONT_SM.render("Spend food to enhance your colony's abilities", True, (160, 130, 80))
        surf.blit(sub, (W // 2 - sub.get_width() // 2, 90))

        mx, my = pygame.mouse.get_pos()

        for key, rect in self.rects.items():
            upg = UPGRADES[key]
            lvl = self.purchased[key]
            maxed = lvl >= upg["max"]
            hovered = rect.collidepoint(mx, my)
            affordable = self.can_afford(key, game)
            cost = self.food_cost(key)

            # Card bg
            if maxed:
                bg = (20, 45, 20)
                border = (60, 160, 60)
            elif hovered and affordable:
                bg = (50, 40, 15)
                border = C["gold"]
            elif affordable:
                bg = (30, 25, 10)
                border = (100, 80, 35)
            else:
                bg = (20, 18, 18)
                border = (50, 45, 45)

            pygame.draw.rect(surf, bg, rect, border_radius=10)
            pygame.draw.rect(surf, border, rect, 2, border_radius=10)

            # Icon + name header
            hdr_rect = pygame.Rect(rect.x + 8, rect.y + 8, rect.w - 16, 36)
            pygame.draw.rect(surf, tuple(max(0, c - 10) for c in bg), hdr_rect, border_radius=6)
            icon_lbl = FONT_LG.render(upg["icon"], True, C["white"])
            surf.blit(icon_lbl, (rect.x + 12, rect.y + 12))
            name_lbl = FONT_MD.render(upg["name"], True, C["white"])
            surf.blit(name_lbl, (rect.x + 44, rect.y + 18))

            # Level pips
            pip_x = rect.x + rect.w - 12
            for p in range(upg["max"]):
                filled = p < lvl
                pcol = C["gold"] if filled else (60, 55, 40)
                pygame.draw.circle(surf, pcol, (pip_x - p * 14, rect.y + 18), 5)
                pygame.draw.circle(surf, (100, 80, 30) if filled else (40, 38, 30),
                                   (pip_x - p * 14, rect.y + 18), 5, 1)

            # Description
            for j, line in enumerate(upg["desc"].split("\n")):
                dl = FONT_SM.render(line, True, (190, 175, 155))
                surf.blit(dl, (rect.x + 10, rect.y + 52 + j * 16))

            # Effect line
            eff = FONT_SM.render(upg["effect"], True, (120, 200, 120) if maxed else (140, 140, 100))
            surf.blit(eff, (rect.x + 10, rect.y + 108))

            # Cost / status
            if maxed:
                ml = FONT_MD.render("MAXED", True, (80, 220, 80))
                surf.blit(ml, (rect.centerx - ml.get_width() // 2, rect.bottom - 34))
            else:
                cost_col = C["gold"] if affordable else (140, 90, 50)
                cl = FONT_SM.render(f"{cost} food", True, cost_col)
                surf.blit(cl, (rect.centerx - cl.get_width() // 2, rect.bottom - 34))
                if hovered and affordable:
                    bl = FONT_SM.render("Click to upgrade", True, (200, 180, 100))
                    surf.blit(bl, (rect.centerx - bl.get_width() // 2, rect.bottom - 18))
                elif hovered and not affordable:
                    bl = FONT_SM.render(f"Need {cost - game.queen.food} more food", True, (180, 80, 60))
                    surf.blit(bl, (rect.centerx - bl.get_width() // 2, rect.bottom - 18))

        # Close hint
        close_rect = pygame.Rect(W // 2 - 70, H - 55, 140, 38)
        pygame.draw.rect(surf, C["red_btn"], close_rect, border_radius=8)
        cl = FONT_MD.render("CLOSE  [ESC]", True, C["white"])
        surf.blit(cl, (close_rect.centerx - cl.get_width() // 2,
                       close_rect.centery - cl.get_height() // 2))
        return close_rect

    def handle_click(self, pos, game):
        for key, rect in self.rects.items():
            if rect.collidepoint(pos):
                if self.buy(key, game):
                    game.notify(f"✓ {UPGRADES[key]['name']} upgraded!")
                else:
                    lvl = self.purchased[key]
                    if lvl >= UPGRADES[key]["max"]:
                        game.notify("Already maxed out!")
                    else:
                        game.notify(f"Need {self.food_cost(key)} food to upgrade.")
                return True
        return False



class ShopScreen:
    BUYABLE = [RoomType.FOOD, RoomType.NURSERY, RoomType.BARRACKS,
               RoomType.HOSPITAL, RoomType.FARM, RoomType.TUNNELS]

    def __init__(self):
        self.buttons = {}
        self._layout()

    def _layout(self):
        cols = 3
        bw, bh = 230, 195
        pad = 22
        sx = W // 2 - (cols * (bw + pad)) // 2
        sy = 120
        for i, rt in enumerate(self.BUYABLE):
            col = i % cols
            row = i // cols
            x = sx + col * (bw + pad)
            y = sy + row * (bh + pad)
            self.buttons[rt] = pygame.Rect(x, y, bw, bh)

    def draw(self, surf, game):
        # Dark overlay
        overlay = pygame.Surface((W, H), pygame.SRCALPHA)
        overlay.fill((0, 0, 0, 200))
        surf.blit(overlay, (0, 0))

        # Title
        title = FONT_LG.render("BUILD ROOMS", True, C["gold"])
        surf.blit(title, (W // 2 - title.get_width() // 2, 60))
        sub = FONT_SM.render("Expand your colony's capabilities", True, (180, 160, 130))
        surf.blit(sub, (W // 2 - sub.get_width() // 2, 100))

        mx, my = pygame.mouse.get_pos()

        for rt, rect in self.buttons.items():
            owned = game.nest.get_room(rt) is not None
            hovered = rect.collidepoint(mx, my)
            cost = ROOM_COSTS.get(rt, {})
            can_afford = (game.queen.food >= cost.get("food", 0) and
                          sum(len(r.leaves) for r in game.nest.rooms) >= cost.get("leaves", 0))

            # Card background
            if owned:
                bg = (30, 50, 30)
                border = (80, 160, 80)
            elif hovered and can_afford:
                bg = (50, 40, 20)
                border = C["gold"]
            elif can_afford:
                bg = (35, 28, 15)
                border = (100, 80, 40)
            else:
                bg = (25, 20, 20)
                border = (60, 50, 50)

            pygame.draw.rect(surf, bg, rect, border_radius=10)
            pygame.draw.rect(surf, border, rect, 2, border_radius=10)

            room_col = ROOM_COLORS[rt]
            pygame.draw.rect(surf, room_col, pygame.Rect(rect.x + 10, rect.y + 10, rect.w - 20, 50),
                             border_radius=6)

            name_lbl = FONT_MD.render(rt.value, True, C["white"])
            surf.blit(name_lbl, (rect.x + rect.w // 2 - name_lbl.get_width() // 2, rect.y + 22))

            # Description
            desc = ROOM_DESCRIPTIONS.get(rt, "")
            for j, line in enumerate(desc.split("\n")):
                dl = FONT_SM.render(line, True, (200, 185, 165))
                surf.blit(dl, (rect.x + 10, rect.y + 75 + j * 16))

            if owned:
                ol = FONT_MD.render("BUILT", True, (100, 220, 100))
                surf.blit(ol, (rect.x + rect.w // 2 - ol.get_width() // 2, rect.y + 158))
            else:
                parts = []
                if cost.get("food", 0):
                    parts.append(f"🍄 {cost['food']} food")
                if cost.get("leaves", 0):
                    parts.append(f"{cost['leaves']} pieces")
                cost_str = "  ".join(parts) if parts else "Free"
                cl = FONT_SM.render(cost_str, True, C["gold"] if can_afford else (160, 100, 60))
                surf.blit(cl, (rect.x + rect.w // 2 - cl.get_width() // 2, rect.y + 158))

        # Close button
        close_rect = pygame.Rect(W // 2 - 60, H - 70, 120, 40)
        pygame.draw.rect(surf, C["red_btn"], close_rect, border_radius=8)
        cl = FONT_MD.render("CLOSE", True, C["white"])
        surf.blit(cl, (close_rect.centerx - cl.get_width() // 2, close_rect.centery - cl.get_height() // 2))
        return close_rect

    def handle_click(self, pos, game) -> bool:
        for rt, rect in self.buttons.items():
            if rect.collidepoint(pos):
                if game.nest.get_room(rt) is not None:
                    return True  # already owned
                cost = ROOM_COSTS.get(rt, {})
                total_leaves = sum(len(r.leaves) for r in game.nest.rooms)
                if (game.queen.food >= cost.get("food", 0) and
                        total_leaves >= cost.get("leaves", 0)):
                    game.queen.food -= cost.get("food", 0)
                    # Consume leaves
                    leaves_needed = cost.get("leaves", 0)
                    for r in game.nest.rooms:
                        while leaves_needed > 0 and r.leaves:
                            r.leaves.pop()
                            leaves_needed -= 1
                    game.nest.add_room(rt)
                    SFX.play('build')
                    # Tunnel Network: boost all current workers
                    if rt == RoomType.TUNNELS:
                        for ant in game.workers:
                            ant.speed *= 1.25
                    game.particles.extend([
                        Particle(W // 2, H // 2,
                                 random.uniform(-80, 80), random.uniform(-120, -40),
                                 2.0, 2.0, C["gold"], 6)
                        for _ in range(20)
                    ])
                return True
        return False


# ── Splash Screen ─────────────────────────────────────────────────────────────
class SplashScreen:
    def __init__(self):
        self.elapsed   = 0.0
        self.done      = False
        self.toast_y   = 0.0        # 0 = hidden inside toaster, 1 = fully popped
        self.toast_vel = 0.0
        self.toast_popped = False
        self.steam_phase = 0.0
        self.fade_out  = 0.0        # 0-1 fade to black at end
        self.text_alpha = 0.0
        self.shine_phase = 0.0

        # Toaster center on screen — body is 160px wide so offset by 80
        self.tx = W // 2 - 80
        self.ty = H // 2 - 80

    def update(self, dt):
        self.elapsed += dt
        self.shine_phase += dt * 1.8

        # Toast pops at t=2.0
        if self.elapsed >= 2.0 and not self.toast_popped:
            self.toast_popped = True
            self.toast_vel = -420.0  # shoot upward fast

        if self.toast_popped:
            # Spring physics — settle at y = -68
            target = -68.0
            spring = 180.0
            damp   = 14.0
            acc = (target - self.toast_y) * spring - self.toast_vel * damp
            self.toast_vel += acc * dt
            self.toast_y   += self.toast_vel * dt
            self.steam_phase += dt * 3.5

        # Text fades in 0.4s after toast pops
        if self.elapsed >= 2.5:
            self.text_alpha = min(1.0, (self.elapsed - 2.5) / 0.6)

        # Fade out after 4.2s
        if self.elapsed >= 4.2:
            self.fade_out = min(1.0, (self.elapsed - 4.2) / 0.5)
            if self.fade_out >= 1.0:
                self.done = True

    def draw(self, surf):
        # Background — warm dark
        surf.fill((26, 16, 8))

        # Subtle radial glow behind toaster
        for r in range(120, 0, -8):
            alpha = max(0, int((1 - r / 120) * 18))
            c = (min(255, 40 + alpha), min(255, 25 + alpha // 2), 8)
            pygame.draw.circle(surf, c, (W // 2, H // 2 + 20), r)

        tx, ty = self.tx, self.ty

        # Countertop
        pygame.draw.rect(surf, (44, 31, 14), (0, ty + 148, W, H))
        pygame.draw.rect(surf, (61, 44, 20), (0, ty + 148, W, 3))

        # ── Toaster shadow ──
        shadow_surf = pygame.Surface((170, 20), pygame.SRCALPHA)
        pygame.draw.ellipse(shadow_surf, (0, 0, 0, 120), (0, 0, 170, 20))
        surf.blit(shadow_surf, (tx - 5, ty + 152))

        # ── Toaster body ──
        body_rect = pygame.Rect(tx, ty + 30, 160, 115)
        pygame.draw.rect(surf, (200, 160, 96), body_rect, border_radius=14)
        # base band
        pygame.draw.rect(surf, (176, 136, 64),
                         pygame.Rect(tx, ty + 115, 160, 30), border_radius=14)
        pygame.draw.rect(surf, (176, 136, 64),
                         pygame.Rect(tx, ty + 115, 160, 10))
        # highlight strip top
        pygame.draw.rect(surf, (232, 200, 128),
                         pygame.Rect(tx + 8, ty + 32, 144, 5), border_radius=3)

        # Brushed lines
        for i in range(6):
            y = ty + 50 + i * 10
            pygame.draw.line(surf, (176, 144, 80), (tx + 8, y), (tx + 152, y), 1)

        # Lever
        pygame.draw.rect(surf, (160, 112, 48),
                         pygame.Rect(tx + 152, ty + 75, 14, 28), border_radius=4)
        pygame.draw.rect(surf, (200, 144, 80),
                         pygame.Rect(tx + 153, ty + 77, 12, 5), border_radius=2)
        pygame.draw.circle(surf, (144, 96, 32), (tx + 159, ty + 107), 5)

        # Crumb tray
        pygame.draw.rect(surf, (144, 96, 48),
                         pygame.Rect(tx + 10, ty + 134, 140, 6), border_radius=2)

        # Feet
        pygame.draw.rect(surf, (58, 40, 8),
                         pygame.Rect(tx + 15, ty + 139, 18, 9), border_radius=3)
        pygame.draw.rect(surf, (58, 40, 8),
                         pygame.Rect(tx + 127, ty + 139, 18, 9), border_radius=3)

        # Shine shimmer
        shine_a = int(abs(math.sin(self.shine_phase)) * 28 + 8)
        shine_surf = pygame.Surface((50, 106), pygame.SRCALPHA)
        shine_surf.fill((255, 248, 224, shine_a))
        surf.blit(shine_surf, (tx + 8, ty + 32))

        # ── Slots ──
        for sx in [tx + 38, tx + 88]:
            pygame.draw.rect(surf, (26, 16, 8),
                             pygame.Rect(sx, ty + 28, 34, 22), border_radius=4)
            pygame.draw.rect(surf, (58, 18, 5),
                             pygame.Rect(sx + 2, ty + 30, 30, 18), border_radius=3)
            # heating coil lines
            for li, ly2 in enumerate([ty + 36, ty + 40, ty + 44]):
                alpha = [180, 180, 130][li]
                r, g = min(255, 200 + li * 10), 68
                pygame.draw.line(surf, (r, g, 0),
                                 (sx + 4, ly2), (sx + 26, ly2), 1)

        # ── Toast (animated) ──
        if self.toast_popped or self.elapsed >= 2.0:
            ty_offset = int(self.toast_y)

            for i, (slotx, col_main, col_crust, col_burn) in enumerate([
                (tx + 38, (200, 114, 42), (168, 88, 24), (139, 64, 16)),
                (tx + 88, (196, 108, 34), (160, 80, 18), (135, 58, 12)),
            ]):
                base_y = ty + 28 + ty_offset
                # bread body
                pygame.draw.rect(surf, col_main,
                                 pygame.Rect(slotx, base_y, 34, 52), border_radius=5)
                # crust top arc
                pygame.draw.ellipse(surf, col_crust,
                                    pygame.Rect(slotx, base_y - 5, 34, 14))
                # toasted spots
                spots = [(4,8,9,6),(16,13,7,5),(6,21,6,4),(18,26,10,5),(5,34,8,4),(19,38,7,4)]
                for bx, by2, bw, bh in spots:
                    pygame.draw.rect(surf, col_burn,
                                     pygame.Rect(slotx + bx, base_y + by2, bw, bh),
                                     border_radius=2)
                # highlight edge
                pygame.draw.rect(surf, (232, 144, 64),
                                 pygame.Rect(slotx + 1, base_y + 6, 3, 38),
                                 border_radius=1)

            # ── Steam wisps ──
            if self.elapsed >= 2.7:
                for sx, offset in [(tx + 55, 0), (tx + 65, 0.8), (tx + 75, 1.6),
                                   (tx + 105, 0.3), (tx + 115, 1.1), (tx + 125, 0)]:
                    phase = (self.steam_phase + offset) % (2 * math.pi)
                    prog  = (math.sin(phase) + 1) / 2
                    alpha = int(prog * 160)
                    sy    = ty + 28 + ty_offset - int(prog * 32)
                    wobble = int(math.sin(phase * 1.7) * 3)
                    s = pygame.Surface((4, 4), pygame.SRCALPHA)
                    s.fill((212, 200, 160, alpha))
                    surf.blit(s, (sx + wobble, sy))
                    # draw a short wavy line upward
                    for seg in range(5):
                        seg_prog = seg / 5
                        wy = sy - seg * 5
                        wx = sx + wobble + int(math.sin(phase * 2 + seg * 0.8) * 2)
                        a2 = max(0, alpha - seg * 30)
                        if a2 > 10:
                            ps = pygame.Surface((3, 3), pygame.SRCALPHA)
                            ps.fill((212, 200, 160, a2))
                            surf.blit(ps, (wx, wy))

        # ── Text ──
        if self.text_alpha > 0:
            a = int(self.text_alpha * 255)

            def blit_alpha_text(text, font, color, cx, cy):
                rendered = font.render(text, True, color)
                ts = rendered.copy()
                ts.set_alpha(a)
                surf.blit(ts, (cx - rendered.get_width() // 2, cy))

            blit_alpha_text("TOASTEDBREAD", FONT_LG,  (232, 200, 112), W // 2, ty + 175)
            blit_alpha_text("PRODUCTIONS",  FONT_SM,  (160, 128, 64),  W // 2, ty + 207)
            blit_alpha_text("warm games since 2024", FONT_SM, (90, 64, 32), W // 2, ty + 228)

        # ── Fade out overlay ──
        if self.fade_out > 0:
            fo_surf = pygame.Surface((W, H))
            fo_surf.fill((0, 0, 0))
            fo_surf.set_alpha(int(self.fade_out * 255))
            surf.blit(fo_surf, (0, 0))

    def skip(self):
        self.elapsed = 99.0
        self.done = True


# ── Colony Selection ──────────────────────────────────────────────────────────

class SelectScreen:
    def __init__(self):
        self.red_rect = pygame.Rect(W // 2 - 320, H // 2 - 120, 260, 240)
        self.black_rect = pygame.Rect(W // 2 + 60, H // 2 - 120, 260, 240)
        self.hover_red = False
        self.hover_black = False
        self.time = 0

    def update(self, dt):
        self.time += dt
        mx, my = pygame.mouse.get_pos()
        self.hover_red = self.red_rect.collidepoint(mx, my)
        self.hover_black = self.black_rect.collidepoint(mx, my)

    def draw(self, surf):
        surf.fill((15, 10, 5))

        # Animated soil texture
        for i in range(0, W, 60):
            for j in range(0, H, 60):
                shade = int(math.sin(self.time + i * 0.05 + j * 0.03) * 5)
                pygame.draw.rect(surf, (max(0, 20 + shade), max(0, 13 + shade), max(0, 5 + shade)), (i, j, 60, 60))

        # Title
        t1 = FONT_XL.render("ANT COLONY", True, C["gold"])
        t2 = FONT_MD.render("The underground empire awaits your command", True, (160, 130, 80))
        surf.blit(t1, (W // 2 - t1.get_width() // 2, 60))
        surf.blit(t2, (W // 2 - t2.get_width() // 2, 155))

        subtitle = FONT_LG.render("Choose Your Colony", True, C["white"])
        surf.blit(subtitle, (W // 2 - subtitle.get_width() // 2, 210))

        self._draw_colony_card(surf, self.red_rect, "red", "RED ANTS",
                               "Aggressive foragers.\nQuick to expand.\nFear no enemy.",
                               self.hover_red)
        self._draw_colony_card(surf, self.black_rect, "black", "BLACK ANTS",
                               "Master architects.\nStrong defenders.\nBuild deep.",
                               self.hover_black)

        hint = FONT_SM.render("Click a colony to begin your reign", True, (120, 100, 70))
        surf.blit(hint, (W // 2 - hint.get_width() // 2, H - 50))

    def _draw_colony_card(self, surf, rect, color, name, desc, hovered):
        scale = 1.05 if hovered else 1.0
        sw = int(rect.w * scale)
        sh = int(rect.h * scale)
        sx = rect.centerx - sw // 2
        sy = rect.centery - sh // 2
        scaled_rect = pygame.Rect(sx, sy, sw, sh)

        ant_col = C["red_ant"] if color == "red" else C["black_ant"]
        bg_col = (50, 20, 20) if color == "red" else (20, 20, 30)
        border_col = (220, 80, 60) if color == "red" else (80, 80, 120)
        if hovered:
            border_col = C["gold"]

        pygame.draw.rect(surf, bg_col, scaled_rect, border_radius=14)
        pygame.draw.rect(surf, border_col, scaled_rect, 3, border_radius=14)

        # Animated ant preview
        t = self.time
        for i in range(3):
            ax = scaled_rect.centerx + math.sin(t * 1.2 + i * 2.1) * 30
            ay = scaled_rect.y + 55 + i * 12 + math.cos(t + i) * 8
            # Mini ant body
            pygame.draw.circle(surf, ant_col, (int(ax), int(ay)), 8)
            pygame.draw.circle(surf, ant_col, (int(ax + 10), int(ay)), 6)
            pygame.draw.circle(surf, ant_col, (int(ax - 9), int(ay)), 7)
            # Antennae
            pygame.draw.line(surf, ant_col, (int(ax + 14), int(ay - 3)),
                             (int(ax + 20), int(ay - 10)), 1)
            pygame.draw.line(surf, ant_col, (int(ax + 14), int(ay - 3)),
                             (int(ax + 22), int(ay - 5)), 1)

        # Crown on middle ant
        crown_x = int(scaled_rect.centerx + math.sin(t * 1.2 + 2) * 30)
        crown_y = int(scaled_rect.y + 55 + 12 + math.cos(t + 1) * 8 - 14)
        for ci in range(3):
            pygame.draw.line(surf, C["gold"], (crown_x + (ci - 1) * 4, crown_y),
                             (crown_x + (ci - 1) * 4, crown_y - 6), 2)

        name_lbl = FONT_LG.render(name, True, ant_col)
        surf.blit(name_lbl, (scaled_rect.centerx - name_lbl.get_width() // 2,
                              scaled_rect.y + 110))

        for j, line in enumerate(desc.split("\n")):
            dl = FONT_SM.render(line, True, (200, 185, 165))
            surf.blit(dl, (scaled_rect.centerx - dl.get_width() // 2,
                           scaled_rect.y + 150 + j * 18))

    def handle_click(self, pos):
        if self.red_rect.collidepoint(pos):
            return "red"
        if self.black_rect.collidepoint(pos):
            return "black"
        return None


# ── Main Game ──────────────────────────────────────────────────────────────────
# ── Battle System ─────────────────────────────────────────────────────────────
MIN_SOLDIERS = 5

class BattleSoldier:
    """A soldier unit on the battle screen (screen-space only)."""
    def __init__(self, x, y, color, side):
        self.x = float(x)
        self.y = float(y)
        self.color = color            # "red" or "black"
        self.side  = side             # "player" or "enemy"
        self.hp    = 100
        self.max_hp = 100
        self.alive  = True
        self.target: Optional["BattleSoldier"] = None
        self.attack_timer = 0.0
        self.attack_interval = random.uniform(0.9, 1.4)
        self.hit_flash = 0.0
        self.leg_phase = random.uniform(0, math.pi * 2)
        self.vx = 0.0
        self.vy = 0.0
        self.angle = 0.0
        self.size  = 9
        self.death_timer = 0.0       # counts up after death for fade
        self.slash_timer = 0.0       # visual slash flash

    def body_col(self):
        if self.hit_flash > 0:
            f = self.hit_flash
            return (min(255, int(255 * f + (200 if self.color=="red" else 30) * (1-f))),
                    int((50 if self.color=="red" else 30) * (1-f)),
                    int((30 if self.color=="red" else 35) * (1-f)))
        return C["red_ant"] if self.color == "red" else C["black_ant"]

    def dark_col(self):
        return C["red_dark"] if self.color == "red" else C["black_dark"]

    def update(self, dt, enemies, allies):
        if not self.alive:
            self.death_timer += dt
            return
        self.leg_phase += dt * 7
        self.hit_flash  = max(0, self.hit_flash  - dt * 4)
        self.slash_timer= max(0, self.slash_timer- dt * 5)
        self.attack_timer -= dt

        # Find nearest living enemy as target
        living = [e for e in enemies if e.alive]
        if not living:
            return
        self.target = min(living, key=lambda e: math.hypot(e.x - self.x, e.y - self.y))

        # Move toward target
        dx = self.target.x - self.x
        dy = self.target.y - self.y
        dist = math.hypot(dx, dy)
        engage_dist = 28

        if dist > engage_dist:
            spd = 55 * dt
            self.vx = (dx / dist) * spd
            self.vy = (dy / dist) * spd
            self.x += self.vx
            self.y += self.vy
            self.angle = math.degrees(math.atan2(dy, dx))
        else:
            # Attack
            if self.attack_timer <= 0:
                dmg = random.randint(12, 22)
                if getattr(self, '_poison', False):
                    dmg = int(dmg * 1.2)
                self.target.hp -= dmg
                self.target.hit_flash = 1.0
                self.slash_timer = 1.0
                self.attack_timer = self.attack_interval
                if self.target.hp <= 0:
                    self.target.alive = False

        # Separate from allies
        for ally in allies:
            if ally is self or not ally.alive:
                continue
            adx = self.x - ally.x
            ady = self.y - ally.y
            adist = math.hypot(adx, ady)
            if 0 < adist < 20:
                push = (20 - adist) / 20 * 0.4
                self.x += (adx / adist) * push
                self.y += (ady / adist) * push

    def draw(self, surf):
        alpha = max(0, 1.0 - max(0, self.death_timer - 0.3) * 3)
        if alpha <= 0:
            return

        a = math.radians(self.angle)
        s = self.size
        bc = self.body_col()
        dc = self.dark_col()

        # Fade dead soldiers
        if not self.alive or alpha < 1.0:
            tmp = pygame.Surface((40, 40), pygame.SRCALPHA)
            tmp.set_alpha(int(alpha * 255))
            ox, oy = int(self.x) - 20, int(self.y) - 20
            self._draw_body(tmp, 20, 20, a, s, bc, dc)
            surf.blit(tmp, (ox, oy))
        else:
            self._draw_body(surf, self.x, self.y, a, s, bc, dc)

        # HP bar
        if self.alive and self.hp < self.max_hp:
            bw = 24
            bx = int(self.x) - bw // 2
            by = int(self.y) - s - 10
            pygame.draw.rect(surf, (60, 20, 20), (bx, by, bw, 4), border_radius=2)
            filled = int(bw * max(0, self.hp / self.max_hp))
            if filled > 0:
                col = (80, 200, 80) if self.hp > 50 else (220, 180, 40) if self.hp > 25 else (220, 60, 40)
                pygame.draw.rect(surf, col, (bx, by, filled, 4), border_radius=2)

        # Slash effect
        if self.slash_timer > 0 and self.target:
            tx, ty = int(self.target.x), int(self.target.y)
            f = self.slash_timer
            col = (255, int(200 * f), int(100 * f))
            for _ in range(3):
                ox2 = random.randint(-8, 8)
                oy2 = random.randint(-8, 8)
                pygame.draw.line(surf, col,
                                 (tx + ox2, ty + oy2 - 6),
                                 (tx - ox2, ty - oy2 + 6), max(1, int(f * 2)))

    def _draw_body(self, surf, cx, cy, a, s, bc, dc):
        # Legs
        for i in range(3):
            off = (i - 1) * s * 0.6
            swing = math.sin(self.leg_phase + i * 1.2) * s * 0.8
            lx = cx + math.cos(a + math.pi/2)*off - math.sin(a)*swing
            ly = cy + math.sin(a + math.pi/2)*off - math.cos(a)*swing*0.5
            rx = cx - math.cos(a + math.pi/2)*off + math.sin(a)*swing
            ry = cy - math.sin(a + math.pi/2)*off + math.cos(a)*swing*0.5
            alx = int(cx + math.cos(a+math.pi/2)*s*0.4 + math.cos(a)*off*0.3)
            aly = int(cy + math.sin(a+math.pi/2)*s*0.4 + math.sin(a)*off*0.3)
            arx = int(cx - math.cos(a+math.pi/2)*s*0.4 + math.cos(a)*off*0.3)
            ary = int(cy - math.sin(a+math.pi/2)*s*0.4 + math.sin(a)*off*0.3)
            pygame.draw.line(surf, dc, (alx,aly), (int(lx),int(ly)), 1)
            pygame.draw.line(surf, dc, (arx,ary), (int(rx),int(ry)), 1)
        # Abdomen
        abx = cx - math.cos(a)*s*0.9
        aby = cy - math.sin(a)*s*0.9
        pygame.draw.circle(surf, bc, (int(abx),int(aby)), int(s*0.7))
        # Thorax
        pygame.draw.circle(surf, bc, (int(cx),int(cy)), int(s*0.55))
        # Head
        hdx = cx + math.cos(a)*s*0.85
        hdy = cy + math.sin(a)*s*0.85
        pygame.draw.circle(surf, bc, (int(hdx),int(hdy)), int(s*0.45))
        # Antennae
        for side in [-1,1]:
            atx = hdx + math.cos(a+side*0.6)*s*0.9
            aty = hdy + math.sin(a+side*0.6)*s*0.9
            pygame.draw.line(surf, dc, (int(hdx),int(hdy)), (int(atx),int(aty)), 1)


class BattleScreen:
    PREP_TIME = 2.0   # seconds before fighting starts

    def __init__(self, player_color, num_soldiers):
        self.player_color = player_color
        self.enemy_color  = "black" if player_color == "red" else "red"
        self.phase = "prep"   # prep → fighting → result
        self.timer = 0.0
        self.result = None    # "win" or "lose"
        self.reward = {}
        self.done   = False

        # Spawn soldiers
        self.player_soldiers: List[BattleSoldier] = []
        self.enemy_soldiers:  List[BattleSoldier] = []

        rows = math.ceil(num_soldiers / 3)
        for i in range(num_soldiers):
            col_i = i % 3
            row_i = i // 3
            # Player: right side
            px = W - 120 - col_i * 38 + random.randint(-8, 8)
            py = H//2 - rows*20 + row_i*42 + random.randint(-6, 6)
            self.player_soldiers.append(BattleSoldier(px, py, player_color, "player"))

            # Enemy: left side (same count)
            ex = 120 + col_i * 38 + random.randint(-8, 8)
            ey = H//2 - rows*20 + row_i*42 + random.randint(-6, 6)
            self.enemy_soldiers.append(BattleSoldier(ex, ey, self.enemy_color, "enemy"))

        # Particles for battle effects
        self.particles: List[Particle] = []

        # Background dirt patches (static)
        self.dirt = [(random.randint(0, W), random.randint(80, H-60),
                      random.randint(20, 55), random.randint(-6, 6)) for _ in range(60)]

        self.countdown_shown = True
        self.skip_rect = pygame.Rect(20, H - 55, 120, 36)
        self.result_alpha = 0.0

    def update(self, dt):
        self.timer += dt
        self.particles = [p for p in self.particles if p.life > 0]
        for p in self.particles:
            p.update(dt)

        if self.phase == "prep":
            if self.timer >= self.PREP_TIME:
                self.phase = "fighting"
                self.timer = 0.0

        elif self.phase == "fighting":
            # Update all soldiers
            for s in self.player_soldiers:
                s.update(dt, self.enemy_soldiers, self.player_soldiers)
            for s in self.enemy_soldiers:
                s.update(dt, self.player_soldiers, self.enemy_soldiers)

            # Spawn hit particles
            for s in self.player_soldiers + self.enemy_soldiers:
                if s.hit_flash > 0.8 and random.random() < 0.3:
                    col = (255, 80, 30) if s.color == "red" else (80, 80, 100)
                    self.particles.append(Particle(
                        s.x + random.randint(-5,5), s.y + random.randint(-5,5),
                        random.uniform(-40,40), random.uniform(-60,-10),
                        0.4, 0.4, col, 3))

            # Check end condition
            living_player = [s for s in self.player_soldiers if s.alive]
            living_enemy  = [s for s in self.enemy_soldiers  if s.alive]

            if not living_player or not living_enemy:
                self.phase = "result"
                self.timer = 0.0
                if living_player:
                    self.result = "win"
                    # Reward scales with soldiers remaining
                    survived = len(living_player)
                    self.reward = {
                        "soldiers": survived,
                        "food":     random.randint(6, 10) + survived,
                        "leaves":   random.randint(12, 22) + survived * 2,
                    }
                else:
                    self.result = "lose"
                    self.reward = {}

        elif self.phase == "result":
            self.result_alpha = min(1.0, self.result_alpha + dt * 2.5)

    def skip_to_result(self):
        """Fast-forward battle instantly."""
        if self.phase != "fighting":
            return
        # Simulate remaining combat
        max_iter = 2000
        i = 0
        while i < max_iter:
            lp = [s for s in self.player_soldiers if s.alive]
            le = [s for s in self.enemy_soldiers  if s.alive]
            if not lp or not le:
                break
            for s in lp:
                s.update(0.05, self.enemy_soldiers, self.player_soldiers)
            for s in le:
                s.update(0.05, self.player_soldiers, self.enemy_soldiers)
            i += 1
        self.phase = "result"
        self.timer = 0.0
        living_player = [s for s in self.player_soldiers if s.alive]
        if living_player:
            self.result = "win"
            survived = len(living_player)
            self.reward = {
                "soldiers": survived,
                "food":     random.randint(6, 10) + survived,
                "leaves":   random.randint(12, 22) + survived * 2,
            }
        else:
            self.result = "lose"
            self.reward = {}

    def draw(self, surf):
        # Background
        surf.fill((55, 38, 18))
        # Dirt texture
        for dx, dy, dr, dshade in self.dirt:
            col = (max(0,min(255,75+dshade)), max(0,min(255,52+dshade)), max(0,min(255,22+dshade)))
            pygame.draw.circle(surf, col, (dx, dy), dr)

        # Dividing line (battle line)
        pygame.draw.line(surf, (100, 70, 30), (W//2, 60), (W//2, H-40), 1)
        dl = FONT_SM.render("BATTLE LINE", True, (80, 55, 22))
        surf.blit(dl, (W//2 - dl.get_width()//2, 42))

        # Side labels
        pcol = C["red_ant"] if self.player_color == "red" else C["black_ant"]
        ecol = C["red_ant"] if self.enemy_color  == "red" else C["black_ant"]
        pl = FONT_MD.render(f"YOUR SOLDIERS", True, pcol)
        el = FONT_MD.render(f"ENEMY ANTS", True, ecol)
        surf.blit(pl, (W - pl.get_width() - 20, 20))
        surf.blit(el, (20, 20))

        # Draw soldiers
        for s in self.enemy_soldiers:
            s.draw(surf)
        for s in self.player_soldiers:
            s.draw(surf)

        # Particles
        for p in self.particles:
            p.draw(surf)

        # Prep countdown
        if self.phase == "prep":
            remaining = self.PREP_TIME - self.timer
            pulse = abs(math.sin(self.timer * 3))
            cnt_col = (min(255,int(200+55*pulse)), min(255,int(160+55*pulse)), 50)
            cnt = FONT_XL.render(f"{remaining:.1f}", True, cnt_col)
            surf.blit(cnt, (W//2 - cnt.get_width()//2, H//2 - 50))
            ready = FONT_LG.render("GET READY!", True, (200, 160, 60))
            surf.blit(ready, (W//2 - ready.get_width()//2, H//2 + 20))

        # Live soldier counts during fight
        if self.phase == "fighting":
            lp = sum(1 for s in self.player_soldiers if s.alive)
            le = sum(1 for s in self.enemy_soldiers  if s.alive)
            pc = FONT_LG.render(f"⚔ {lp}", True, pcol)
            ec = FONT_LG.render(f"{le} ⚔", True, ecol)
            surf.blit(pc, (W - pc.get_width() - 20, H - 50))
            surf.blit(ec, (20, H - 50))

            # Skip button
            pygame.draw.rect(surf, (50, 35, 15), self.skip_rect, border_radius=6)
            pygame.draw.rect(surf, (120, 85, 35), self.skip_rect, 1, border_radius=6)
            sl = FONT_SM.render("SKIP", True, (200, 160, 70))
            surf.blit(sl, (self.skip_rect.centerx - sl.get_width()//2,
                           self.skip_rect.centery - sl.get_height()//2))

        # Result overlay
        if self.phase == "result":
            a = int(self.result_alpha * 210)
            ov = pygame.Surface((W, H), pygame.SRCALPHA)
            ov.fill((0, 0, 0, a))
            surf.blit(ov, (0, 0))

            if self.result_alpha > 0.3:
                ta = min(1.0, (self.result_alpha - 0.3) / 0.7)

                def at(text, font, col, cx, cy):
                    lbl = font.render(text, True, col)
                    lbl.set_alpha(int(ta * 255))
                    surf.blit(lbl, (cx - lbl.get_width()//2, cy))

                if self.result == "win":
                    at("VICTORY!", FONT_XL, (255, 215, 50), W//2, H//2 - 140)
                    at("Your colony triumphed!", FONT_MD, (200, 180, 100), W//2, H//2 - 80)
                    # Rewards
                    at("REWARDS", FONT_LG, (200, 160, 60), W//2, H//2 - 35)
                    ry = H//2 + 10
                    for label, val in [
                        (f"{self.reward.get('soldiers',0)} soldiers kept", (120, 200, 120)),
                        (f"🍄 +{self.reward.get('food',0)} food", (200, 200, 100)),
                        (f"🍃 +{self.reward.get('leaves',0)} leaf pieces", (100, 200, 120)),
                    ]:
                        at(label, FONT_MD, val, W//2, ry)
                        ry += 34
                else:
                    at("DEFEAT", FONT_XL, (200, 60, 40), W//2, H//2 - 100)
                    at("Your soldiers were overwhelmed.", FONT_MD, (180, 100, 80), W//2, H//2 - 40)
                    at("Train more soldiers and try again.", FONT_SM, (140, 80, 60), W//2, H//2)

                if self.result_alpha >= 1.0:
                    cont = FONT_MD.render("Click anywhere to continue", True, (140, 120, 70))
                    cont.set_alpha(int(abs(math.sin(time.time()*2)) * 200 + 55))
                    surf.blit(cont, (W//2 - cont.get_width()//2, H - 55))


# ── Raid System ───────────────────────────────────────────────────────────────
def raid_count(food: int) -> int:
    if food < 50:   return 8
    if food < 150:  return 12
    if food < 400:  return 18
    if food < 800:  return 25
    if food < 2000: return 35
    return min(55, 35 + (food - 2000) // 80)


class Raider:
    SPEED = 55.0

    def __init__(self, x, y, enemy_color):
        self.x = float(x)
        self.y = float(y)
        self.color = enemy_color
        self.hp = 60
        self.max_hp = 60
        self.alive = True
        self.angle = 180.0
        self.leg_phase = random.uniform(0, math.pi * 2)
        self.size = 8
        self.hit_flash = 0.0
        self.attack_timer = 0.0
        self.phase = "walk_in"
        self.target_ant = None
        self.carrying_food = False
        self.done = False
        self.death_timer = 0.0
        self.wobble = random.uniform(-0.25, 0.25)
        self._raider_dmg_accum = 0  # damage dealt to target worker

    def body_col(self):
        if self.hit_flash > 0:
            f = self.hit_flash
            base = C["red_ant"] if self.color == "red" else C["black_ant"]
            return (min(255, int(255*f + base[0]*(1-f))),
                    int(base[1]*(1-f)), int(base[2]*(1-f)))
        return C["red_ant"] if self.color == "red" else C["black_ant"]

    def dark_col(self):
        return C["red_dark"] if self.color == "red" else C["black_dark"]

    def update(self, dt, nest_entrance, workers, food_ref):
        self.leg_phase += dt * 7
        self.hit_flash = max(0, self.hit_flash - dt * 4)
        self.attack_timer -= dt

        if not self.alive:
            self.death_timer += dt
            if self.death_timer > 1.2:
                self.done = True
            return

        if self.phase == "walk_in":
            tx, ty = nest_entrance
            dx, dy = tx - self.x, ty - self.y
            dist = math.hypot(dx, dy)
            if dist < 20:
                self.phase = "fight_or_steal"
                self.attack_timer = random.uniform(0.4, 1.0)
            else:
                ang = math.atan2(dy, dx) + self.wobble * math.sin(time.time() + id(self)*0.001)
                self.x += math.cos(ang) * self.SPEED * dt
                self.y += math.sin(ang) * self.SPEED * dt
                self.angle = math.degrees(math.atan2(dy, dx))

        elif self.phase == "fight_or_steal":
            nearby = [w for w in workers if math.hypot(w.x - self.x, w.y - self.y) < 90]
            if nearby:
                self.target_ant = min(nearby, key=lambda w: math.hypot(w.x - self.x, w.y - self.y))
                dx, dy = self.target_ant.x - self.x, self.target_ant.y - self.y
                dist = math.hypot(dx, dy)
                if dist > 20:
                    self.x += (dx/dist) * self.SPEED * 0.8 * dt
                    self.y += (dy/dist) * self.SPEED * 0.8 * dt
                    self.angle = math.degrees(math.atan2(dy, dx))
                elif self.attack_timer <= 0:
                    dmg = random.randint(8, 16)
                    self.target_ant._raider_hp = getattr(self.target_ant, '_raider_hp', 50)
                    self.target_ant._raider_hp -= dmg
                    self.target_ant._hit_flash = 1.0
                    self.attack_timer = random.uniform(0.9, 1.5)
                    if self.target_ant._raider_hp <= 0:
                        self.target_ant._killed_by_raider = True
            else:
                # No workers nearby — go for food
                if food_ref[0] > 0:
                    stolen = max(1, min(3, food_ref[0]))
                    food_ref[0] = max(0, food_ref[0] - stolen)
                    self.carrying_food = True
                self.phase = "walk_out"

        elif self.phase == "walk_out":
            self.x -= self.SPEED * 1.4 * dt
            self.angle = 180
            if self.x < -40:
                self.done = True

    def take_damage(self, dmg):
        self.hp -= dmg
        self.hit_flash = 1.0
        if self.hp <= 0:
            self.alive = False
            self.phase = "dead"

    def draw(self, surf):
        if self.done:
            return
        alpha = max(0, 1.0 - max(0, self.death_timer - 0.1) * 2.5)
        if alpha <= 0:
            return

        a = math.radians(self.angle)
        s = self.size
        bc = self.body_col()
        dc = self.dark_col()

        # Draw on temp surface for alpha fade on death
        tmp = pygame.Surface((60, 60), pygame.SRCALPHA)
        tmp.set_alpha(int(alpha * 255))
        cx, cy = 30, 30

        for i in range(3):
            off = (i-1)*s*0.6
            swing = math.sin(self.leg_phase + i*1.2) * s * 0.8
            for sign in [1, -1]:
                lx = cx + math.cos(a+sign*math.pi/2)*off - math.sin(a)*swing*sign
                ly = cy + math.sin(a+sign*math.pi/2)*off - math.cos(a)*swing*sign*0.5
                alx = int(cx + math.cos(a+sign*math.pi/2)*s*0.4 + math.cos(a)*off*0.3)
                aly = int(cy + math.sin(a+sign*math.pi/2)*s*0.4 + math.sin(a)*off*0.3)
                pygame.draw.line(tmp, dc, (alx,aly), (int(lx),int(ly)), 1)

        abx = cx - math.cos(a)*s*0.9; aby = cy - math.sin(a)*s*0.9
        pygame.draw.circle(tmp, bc, (int(abx),int(aby)), int(s*0.7))
        pygame.draw.circle(tmp, bc, (cx,cy), int(s*0.55))
        hdx = cx + math.cos(a)*s*0.85; hdy = cy + math.sin(a)*s*0.85
        pygame.draw.circle(tmp, bc, (int(hdx),int(hdy)), int(s*0.45))
        pygame.draw.circle(tmp, dc, (int(hdx),int(hdy)), int(s*0.45), 1)
        for sd in [-1, 1]:
            atx = hdx + math.cos(a+sd*0.6)*s*0.9
            aty = hdy + math.sin(a+sd*0.6)*s*0.9
            pygame.draw.line(tmp, dc, (int(hdx),int(hdy)), (int(atx),int(aty)), 1)

        if self.carrying_food:
            pygame.draw.circle(tmp, C["mushroom"], (cx, cy - s - 3), 4)

        surf.blit(tmp, (int(self.x) - 30, int(self.y) - 30))

        # HP bar
        if self.alive and self.hp < self.max_hp:
            bw = 22
            bx = int(self.x) - bw//2
            by = int(self.y) - s - 14
            pygame.draw.rect(surf, (60,20,20), (bx,by,bw,4), border_radius=2)
            filled = int(bw * max(0, self.hp / self.max_hp))
            if filled > 0:
                col = (80,200,80) if self.hp > 30 else (220,60,40)
                pygame.draw.rect(surf, col, (bx,by,filled,4), border_radius=2)

        if self.hit_flash > 0.6:
            pygame.draw.circle(surf, (255,220,50), (int(self.x),int(self.y)), s+5, 2)


class RaidEvent:
    BANNER_TIME = 3.5

    def __init__(self, player_color, food_ref, workers):
        self.enemy_color = "black" if player_color == "red" else "red"
        self.food_ref = food_ref
        self.phase = "banner"
        self.timer = 0.0
        self.done = False
        self.banner_alpha = 0.0
        self.raiders: List[Raider] = []
        self.particles: List[Particle] = []
        self.result_msg = ""
        self.queen_killed = False
        self._spawn_raiders(food_ref[0])

    def _spawn_raiders(self, food):
        n = raid_count(food)
        for i in range(n):
            x = random.randint(-140, -20)
            y = random.randint(H//2 - 120, H//2 + 60)
            self.raiders.append(Raider(x, y, self.enemy_color))

    @property
    def nest_entrance(self):
        return (W//2, H//2 + 30)

    def update(self, dt, workers, food_ref):
        self.timer += dt
        if self.phase == "banner":
            self.banner_alpha = min(1.0, self.timer / 0.5)
            if self.timer >= self.BANNER_TIME:
                self.phase = "active"
                self.timer = 0.0
            return

        if self.phase == "active":
            for r in self.raiders:
                r.update(dt, self.nest_entrance, workers, food_ref)

            # Remove killed workers
            for w in list(workers):
                if getattr(w, '_killed_by_raider', False):
                    col = C["red_ant"] if w.colony_color == "red" else C["black_ant"]
                    for _ in range(8):
                        self.particles.append(Particle(
                            w.x, w.y, random.uniform(-50,50),
                            random.uniform(-80,-10), 1.0, 1.0, col, 4))
                    workers.remove(w)

            self.particles = [p for p in self.particles if p.life > 0]
            for p in self.particles:
                p.update(dt)

            # End: all raiders done (fled or dead)
            active = [r for r in self.raiders if not r.done]
            if not active:
                self.phase = "over"
                self.timer = 0.0
                killed = sum(1 for r in self.raiders if not r.alive)
                fled = sum(1 for r in self.raiders if r.alive and r.done)
                if not workers and food_ref[0] <= 0:
                    self.queen_killed = True
                    self.result_msg = "All food taken and all ants killed... THE QUEEN IS DEAD."
                elif killed == len(self.raiders):
                    self.result_msg = f"Raid repelled! All {killed} raiders eliminated!"
                else:
                    self.result_msg = f"Raid over. {killed} raiders killed, {fled} fled with food."

        elif self.phase == "over":
            if self.timer > 3.5:
                self.done = True

    def draw_banner(self, surf):
        if self.phase != "banner":
            return
        pulse = abs(math.sin(self.timer * 5))
        a = int(self.banner_alpha * 190)
        ov = pygame.Surface((W, H), pygame.SRCALPHA)
        ov.fill((140, 0, 0, a))
        surf.blit(ov, (0,0))

        rc = (min(255, int(220+35*pulse)), int(40*pulse), 0)
        r1 = FONT_XL.render("!! RAID !!", True, rc)
        r1.set_alpha(int(self.banner_alpha * 255))
        surf.blit(r1, (W//2 - r1.get_width()//2, H//2 - 80))

        r2 = FONT_LG.render("KEEP YOUR COLONY SAFE!", True, (230, 185, 80))
        r2.set_alpha(int(self.banner_alpha * 220))
        surf.blit(r2, (W//2 - r2.get_width()//2, H//2 + 5))

        r3 = FONT_MD.render("Click enemy ants to damage them!", True, (180, 150, 100))
        r3.set_alpha(int(self.banner_alpha * 200))
        surf.blit(r3, (W//2 - r3.get_width()//2, H//2 + 50))

    def draw_raiders(self, surf):
        for r in self.raiders:
            r.draw(surf)
        for p in self.particles:
            p.draw(surf)
        if self.phase == "over" and self.result_msg:
            alpha = min(255, int(self.timer / 3.5 * 255))
            col = (80, 220, 80) if not self.queen_killed else (220, 50, 50)
            lbl = FONT_LG.render(self.result_msg[:70], True, col)
            lbl.set_alpha(alpha)
            surf.blit(lbl, (W//2 - lbl.get_width()//2, H//2 - 20))

    def click_at(self, pos):
        for r in self.raiders:
            if r.alive and math.hypot(r.x - pos[0], r.y - pos[1]) < r.size + 12:
                r.take_damage(random.randint(10, 18))
                for _ in range(5):
                    self.particles.append(Particle(
                        r.x, r.y, random.uniform(-40,40),
                        random.uniform(-60,-10), 0.5, 0.5, (255,200,50), 3))
                return True
        return False


class Game:
    def __init__(self):
        self.screen = pygame.display.set_mode((W, H))
        pygame.display.set_caption("Ant Colony Simulator")
        self.clock = pygame.time.Clock()
        self.state = GameState.SPLASH
        self.colony_color = None

        self.splash_screen = SplashScreen()
        self.select_screen = SelectScreen()
        self.shop_screen = ShopScreen()
        self.upgrade_screen = UpgradeScreen()
        self.outside = None
        self.nest = None
        self.queen: Optional[Queen] = None
        self.workers:  List[Ant] = []
        self.soldiers: List[Ant] = []
        self.particles: List[Particle] = []

        self.selected_ant: Optional[Ant] = None
        self.dragging_leaf: Optional[Leaf] = None
        self.drag_offset = (0, 0)

        self.battle_screen: Optional[BattleScreen] = None
        self.raid_event: Optional[RaidEvent] = None
        self.raid_timer = 0.0
        self.raid_check_interval = 50.0
        self.queen_dead = False

        # Upgrade state
        self.auto_harvest = False
        self.worker_speed_bonus = 1.0
        self.bigger_bite = False
        self.scout_range_level = 0
        self.leaf_capacity = 20
        self.auto_harvest_timer = 0.0
        self.soldier_hp_bonus = 0
        self.soldier_frenzy_level = 0
        self.soldier_poison = False
        self.egg_food_discount = 0
        self.mushroom_yield_bonus = 0
        self.farm_timer = 0.0

        self.notification = ""
        self.notif_timer = 0
        self.menu_time = 0
        self._loading_frames = 0

        # Init sound engine
        global SFX
        SFX = SoundEngine()

    def _draw_loading(self):
        surf = self.screen
        surf.fill((10, 6, 2))

        # Animated bar — pulses while waiting
        bar_w = 360
        bar_h = 18
        bx = W // 2 - bar_w // 2
        by = H // 2 + 20

        # Track
        pygame.draw.rect(surf, (40, 28, 10), (bx, by, bar_w, bar_h), border_radius=9)
        pygame.draw.rect(surf, (80, 55, 18), (bx, by, bar_w, bar_h), 1, border_radius=9)

        # Indeterminate fill — sliding block
        t = time.time()
        block_w = 120
        pos = int(((t * 0.6) % 1.0) * (bar_w + block_w)) - block_w
        fill_x = max(bx, bx + pos)
        fill_w = min(block_w, (bx + bar_w) - fill_x)
        if fill_w > 0:
            pygame.draw.rect(surf, (200, 150, 50), (fill_x, by + 2, fill_w, bar_h - 4), border_radius=7)

        # Text
        lbl = FONT_MD.render("Loading music...", True, (180, 140, 60))
        surf.blit(lbl, (W // 2 - lbl.get_width() // 2, by - 36))

        # Dots animation
        dots = "." * (int(t * 2) % 4)
        dot_lbl = FONT_SM.render(dots, True, (120, 90, 35))
        surf.blit(dot_lbl, (W // 2 + lbl.get_width() // 2 + 4, by - 32))

    def start_game(self, color):
        self.colony_color = color
        self.outside = OutsideWorld(color)
        self.nest = NestView(color)
        queen_room = self.nest.get_room(RoomType.QUEEN)
        qx, qy = queen_room.cx(), queen_room.cy()
        self.queen = Queen(qx, qy, color)
        self.queen.food = 0
        self.nest.add_room(RoomType.LEAF)  # leaf room is free from the start
        self.state = GameState.NEST

        # Start with 3 workers
        for i in range(3):
            wx = qx + random.randint(-60, 60)
            wy = qy + random.randint(50, 150)
            w = Ant(wx, wy, AntRole.WORKER, color)
            w._in_outside = False
            self.workers.append(w)

        self.notify(f"Your {color} colony begins! Go outside and harvest leaves, then build a Food Lab.")

    def _swap_workers_to_outside(self):
        entrance_x = W // 2
        entrance_y = H // 2 + 20
        for ant in self.workers:
            ant._nest_x = ant.x
            ant._nest_y = ant.y
            ant.x = entrance_x + random.randint(-40, 40)
            ant.y = entrance_y + random.randint(-20, 20)
            ant.target_x = ant.x
            ant.target_y = ant.y
            ant._in_outside = True
            # Only reset idle ants — don't interrupt carrying
            if ant.state in (AntState.IDLE, AntState.WANDER):
                ant.state = AntState.IDLE
                ant.idle_timer = random.uniform(0.2, 0.8)

    def _swap_workers_to_nest(self):
        for ant in self.workers:
            ant._in_outside = False
            if hasattr(ant, '_nest_x'):
                ant.x = ant._nest_x
                ant.y = ant._nest_y
            else:
                qr = self.nest.get_room(RoomType.QUEEN)
                if qr:
                    ant.x = qr.cx() + random.randint(-50, 50)
                    ant.y = qr.cy() + random.randint(20, 80)
            ant.target_x = ant.x
            ant.target_y = ant.y
            if ant.state in (AntState.IDLE, AntState.WANDER):
                ant.state = AntState.IDLE

    def notify(self, msg, duration=3.5):
        self.notification = msg
        self.notif_timer = duration

    def get_nest_bounds(self):
        return (60, 80, NestView.WORLD_W - 60, NestView.WORLD_H - 60)

    def get_outside_bounds(self):
        # Ants roam only in the above-ground half, with margin from edges
        return (40, 75, W - 40, H // 2 + 40)

    def update(self, dt):
        if self.state == GameState.SPLASH:
            self.splash_screen.update(dt)
            if self.splash_screen.done:
                self.state = GameState.LOADING
                self._loading_frames = 0  # give it 2 frames to draw before synthesizing
            return
        if self.state == GameState.LOADING:
            self._loading_frames += 1
            if self._loading_frames >= 2:
                SFX.start_music()           # synthesize + start (blocks ~3s)
                self.state = GameState.MENU
            return
        if self.state == GameState.BATTLE:
            if self.battle_screen:
                self.battle_screen.update(dt)
            return
        if self.state == GameState.MENU:
            self.menu_time += dt
            return

        self.particles = [p for p in self.particles if p.life > 0]
        for p in self.particles:
            p.update(dt)

        if self.notif_timer > 0:
            self.notif_timer -= dt

        # Always update outside world and workers (even when in nest view)
        if self.outside:
            self.outside.update(dt, self.bigger_bite, self.scout_range_level)
            outside_bounds = self.get_outside_bounds()
            nest_entrance = (W // 2, H // 2 + 30)
            for ant in self.workers:
                if getattr(ant, '_in_outside', True):
                    ant.update(dt, outside_bounds, self.nest.rooms, nest_entrance)

            # Auto-harvest
            if self.auto_harvest and self.state == GameState.OUTSIDE:
                self.auto_harvest_timer -= dt
                if self.auto_harvest_timer <= 0:
                    self.auto_harvest_timer = 2.5
                    idle = [a for a in self.workers
                            if a.state in (AntState.IDLE, AntState.WANDER)
                            and getattr(a, '_in_outside', True)]
                    for leaf in self.outside.leaves:
                        if not idle:
                            break
                        pieces = leaf.available_pieces()
                        for piece in pieces:
                            if not idle:
                                break
                            worker = min(idle, key=lambda a: math.hypot(a.x-leaf.x, a.y-leaf.y))
                            idle.remove(worker)
                            worker.command_fetch_piece(piece, leaf, self.nest.rooms,
                                                       deposit_pos=nest_entrance)

        if self.state in (GameState.OUTSIDE, GameState.NEST, GameState.SHOP, GameState.UPGRADES):
            self.nest.update(dt)
            bounds = self.get_nest_bounds()
            nursery = self.nest.get_room(RoomType.NURSERY)
            nursery_bonus = 2.0 if nursery else 1.0
            queen_room = self.nest.get_room(RoomType.QUEEN)

            hatched = self.queen.update(dt, queen_room.rect, nursery_bonus, self.egg_food_discount)

            # Sync food room mushrooms to queen.food — remove one when food is consumed
            food_room = self.nest.get_room(RoomType.FOOD)
            if food_room:
                while len(food_room.mushrooms) > self.queen.food:
                    food_room.mushrooms.pop(0)
            for egg in hatched:
                self.queen.eggs.remove(egg)
                wx = queen_room.cx() + random.randint(-40, 40)
                wy = queen_room.cy() + random.randint(20, 60)
                new_ant = Ant(wx, wy, AntRole.WORKER, self.colony_color)
                new_ant._in_outside = False
                # Apply tunnel speed bonus to new workers
                if self.nest.get_room(RoomType.TUNNELS):
                    new_ant.speed *= 1.25
                new_ant.speed *= self.worker_speed_bonus
                self.workers.append(new_ant)
                self.notify(f"An egg hatched! Worker #{len(self.workers)} joins the colony!")
                SFX.play('hatch')
                for _ in range(12):
                    self.particles.append(Particle(
                        wx, wy, random.uniform(-60, 60), random.uniform(-80, -20),
                        1.2, 1.2, C["egg_c"], 4))

            # Underground Farm — passive food every 20s if leaf pieces stored
            farm = self.nest.get_room(RoomType.FARM)
            if farm:
                self.farm_timer -= dt
                if self.farm_timer <= 0:
                    self.farm_timer = 20.0
                    total_pieces = sum(len(r.leaves) for r in self.nest.rooms)
                    if total_pieces >= 2:
                        self.queen.food += 1
                        farm.add_food_particle()
                        self.notify("Underground Farm produced 1 food!")

            # Hospital — slowly heal soldiers between battles
            hospital = self.nest.get_room(RoomType.HOSPITAL)
            if hospital and self.soldiers:
                # Not in battle — not applicable here but track for future

                pass

            for ant in self.workers:
                ant.update(dt, bounds, self.nest.rooms, (W // 2, H // 2))

            # Collect pending food from ant processing runs
            food_room = self.nest.get_room(RoomType.FOOD)
            if food_room and getattr(food_room, '_pending_food', 0) > 0:
                gained = food_room._pending_food * (1 + self.mushroom_yield_bonus)
                self.queen.food += gained
                food_room._pending_food = 0
                food_room.add_food_particle()
                SFX.play('food')

            # Soldiers wander inside barracks
            barracks = self.nest.get_room(RoomType.BARRACKS)
            if barracks:
                sol_bounds = (barracks.rect.x, barracks.rect.y,
                              barracks.rect.right, barracks.rect.bottom)
                for sol in self.soldiers:
                    sol.update(dt, sol_bounds, self.nest.rooms, (barracks.cx(), barracks.cy()))

        # (held piece position is updated in draw loop to follow cursor)

        # ── Raid check ─────────────────────────────────────────────────────────
        if (self.queen and not self.queen_dead and self.raid_event is None and
                self.state in (GameState.NEST, GameState.OUTSIDE,
                               GameState.SHOP, GameState.UPGRADES)):
            food = self.queen.food
            if food >= 10:
                self.raid_timer -= dt
                if self.raid_timer <= 0:
                    self.raid_timer = self.raid_check_interval
                    raid_prob = min(0.65, 0.05 + (food - 10) / 5000 * 0.60)
                    if random.random() < raid_prob:
                        food_ref = [self.queen.food]
                        self.raid_event = RaidEvent(
                            self.colony_color, food_ref, self.workers)
                        SFX.play('warn')
                        # Force outside view so raiders are visible
                        if self.state == GameState.NEST:
                            self._swap_workers_to_outside()
                            self.state = GameState.OUTSIDE
                        # Override ALL worker activities — cancel fetching, processing, auto-harvest
                        for ant in self.workers:
                            # Release any held piece
                            if ant.carrying_piece:
                                ant.carrying_piece.being_carried = False
                                ant.carrying_piece.carrier = None
                                ant.carrying_piece = None
                            if ant.assigned_piece:
                                ant.assigned_piece.being_carried = False
                                ant.assigned_piece.carrier = None
                                ant.assigned_piece = None
                            ant._keep_processing = False
                            ant._process_food_room = None
                            ant._deposit_pos_override = None
                            ant.state = AntState.WANDER  # will naturally engage raiders via proximity

        # ── Raid event update ──────────────────────────────────────────────────
        if self.raid_event and self.state == GameState.OUTSIDE:
            # Keep suppressing auto-harvest during raid
            if self.auto_harvest:
                for ant in self.workers:
                    if ant.state in (AntState.FETCH_LEAF, AntState.CARRY_LEAF,
                                     AntState.PROCESS_LEAF, AntState.PROCESS_CARRY):
                        if ant.carrying_piece:
                            ant.carrying_piece.being_carried = False
                            ant.carrying_piece.carrier = None
                            ant.carrying_piece = None
                        if ant.assigned_piece:
                            ant.assigned_piece.being_carried = False
                            ant.assigned_piece.carrier = None
                            ant.assigned_piece = None
                        ant._keep_processing = False
                        ant.state = AntState.WANDER
            food_ref = [self.queen.food]
            self.raid_event.update(dt, self.workers, food_ref)
            self.queen.food = max(0, food_ref[0])
            if self.raid_event.done:
                if self.raid_event.queen_killed:
                    self.queen_dead = True
                    self.notify("YOUR QUEEN IS DEAD. Game over.")
                    self.state = GameState.MENU
                else:
                    self.notify(self.raid_event.result_msg)
                self.raid_event = None
                self.raid_timer = self.raid_check_interval * 1.5  # cooldown

    def handle_event(self, event):
        if event.type == pygame.QUIT:
            return False

        if event.type == pygame.KEYDOWN:
            if event.key == pygame.K_TAB:
                if self.state == GameState.NEST:
                    self._swap_workers_to_outside()
                    self.state = GameState.OUTSIDE
                elif self.state == GameState.OUTSIDE:
                    self._swap_workers_to_nest()
                    self.state = GameState.NEST
            if event.key == pygame.K_ESCAPE:
                if self.state == GameState.SHOP:
                    self.state = GameState.NEST
                elif self.state == GameState.UPGRADES:
                    self.state = GameState.NEST
                elif self.state == GameState.SPLASH:
                    self.splash_screen.skip()
            # Any key skips splash after toast has popped
            if self.state == GameState.SPLASH and self.splash_screen.toast_popped:
                self.splash_screen.skip()
            if event.key == pygame.K_m and SFX:
                SFX.toggle_music()

        # Mouse button down
        if event.type == pygame.MOUSEBUTTONDOWN:
            if self.state == GameState.SPLASH and self.splash_screen.toast_popped:
                self.splash_screen.skip()
                return True
            if event.button == 1:
                self._mouse_down_pos = event.pos
                self._mouse_dragged = False
                if self.nest and self.state in (GameState.NEST, GameState.SHOP, GameState.UPGRADES) and not self.dragging_leaf:
                    self.nest.start_cam_drag(event.pos)
            elif event.button in (2, 3):
                if self.nest and self.state in (GameState.NEST, GameState.SHOP, GameState.UPGRADES):
                    self.nest.start_cam_drag(event.pos)

        if event.type == pygame.MOUSEMOTION:
            if self.nest and self.state in (GameState.NEST, GameState.SHOP, GameState.UPGRADES):
                if hasattr(self, '_mouse_down_pos') and self._mouse_down_pos:
                    dx = event.pos[0] - self._mouse_down_pos[0]
                    dy = event.pos[1] - self._mouse_down_pos[1]
                    if math.hypot(dx, dy) > 5:
                        self._mouse_dragged = True
                if not self.dragging_leaf:
                    self.nest.update_cam_drag(event.pos)

        if event.type == pygame.MOUSEBUTTONUP:
            if event.button == 1:
                if self.nest:
                    self.nest.stop_cam_drag()
                # Always fire click - whether holding a piece or doing a short tap
                if self.dragging_leaf or not getattr(self, '_mouse_dragged', False):
                    self._handle_click(event.pos)
                self._mouse_down_pos = None
                self._mouse_dragged = False
            elif event.button in (2, 3):
                if self.nest:
                    self.nest.stop_cam_drag()

        return True

    def _handle_click(self, pos):
        if self.state == GameState.MENU:
            self.state = GameState.SELECT
            return

        if self.state == GameState.SELECT:
            choice = self.select_screen.handle_click(pos)
            if choice:
                SFX.play('fanfare')
                self.start_game(choice)
            return

        # HUD buttons
        shop_area    = pygame.Rect(W - 440, 5, 90, 50)
        upg_area     = pygame.Rect(W - 590, 5, 140, 50)
        battle_area  = pygame.Rect(W - 800, 5, 200, 50)
        view_area    = pygame.Rect(W - 200, 5, 130, 50)

        if (battle_area.collidepoint(pos) and self.nest and
                self.nest.get_room(RoomType.BARRACKS) and
                self.state not in (GameState.BATTLE, GameState.SHOP, GameState.UPGRADES)):
            n = len(self.soldiers)
            if n >= MIN_SOLDIERS:
                self.battle_screen = BattleScreen(self.colony_color, n)
                # Apply upgrade buffs to player soldiers
                for s in self.battle_screen.player_soldiers:
                    s.hp += self.soldier_hp_bonus
                    s.max_hp = s.hp
                    if self.soldier_frenzy_level:
                        s.attack_interval *= max(0.4, 1.0 - 0.25 * self.soldier_frenzy_level)
                    if self.soldier_poison:
                        s._poison = True
                # Hospital: player soldiers start with extra HP if hospital built
                if self.nest.get_room(RoomType.HOSPITAL):
                    for s in self.battle_screen.player_soldiers:
                        s.hp = int(s.hp * 1.3)
                        s.max_hp = s.hp
                self.state = GameState.BATTLE
                SFX.play('dispatch')
            else:
                self.notify(f"Need {MIN_SOLDIERS} soldiers! ({n}/{MIN_SOLDIERS})")
            return

        if upg_area.collidepoint(pos) and self.state not in (GameState.SHOP, GameState.UPGRADES):
            self.state = GameState.UPGRADES
            return
        if shop_area.collidepoint(pos) and self.state not in (GameState.SHOP, GameState.UPGRADES):
            self.state = GameState.SHOP
            return
        if view_area.collidepoint(pos):
            if self.state == GameState.NEST:
                self._swap_workers_to_outside()
                self.state = GameState.OUTSIDE
            elif self.state == GameState.OUTSIDE:
                self._swap_workers_to_nest()
                self.state = GameState.NEST
            return

        if self.state == GameState.SHOP:
            close = self.shop_screen.draw(self.screen, self)
            if close.collidepoint(pos):
                self.state = GameState.NEST
                return
            self.shop_screen.handle_click(pos, self)
            return

        if self.state == GameState.UPGRADES:
            close = self.upgrade_screen.draw(self.screen, self)
            if close.collidepoint(pos):
                self.state = GameState.NEST
                return
            self.upgrade_screen.handle_click(pos, self)
            return

        if self.state == GameState.BATTLE:
            bs = self.battle_screen
            if not bs:
                return
            if bs.phase == "fighting" and bs.skip_rect.collidepoint(pos):
                bs.skip_to_result()
                return
            if bs.phase == "result" and bs.result_alpha >= 1.0:
                if bs.result == "win":
                    self.queen.food += bs.reward.get("food", 0)
                    leaf_room = self.nest.get_room(RoomType.LEAF)
                    store_room = self.nest.get_room(RoomType.STORAGE)
                    target_room = leaf_room or store_room
                    if target_room:
                        for _ in range(bs.reward.get("leaves", 0)):
                            shapes = make_piece_shapes(1, 10)
                            p = LeafPiece(
                                target_room.rect.x + random.randint(15, target_room.rect.w - 15),
                                target_room.rect.y + random.randint(25, target_room.rect.h - 15),
                                shapes[0])
                            p.deposited = True
                            target_room.leaves.append(p)
                    surviving = bs.reward.get("soldiers", 0)
                    self.soldiers = self.soldiers[:surviving]
                    self.notify(f"Victory! +{bs.reward.get('food',0)} food, +{bs.reward.get('leaves',0)} leaf pieces!")
                    SFX.play('build')
                else:
                    self.soldiers.clear()
                    self.notify("Defeat. Your soldiers were lost. Train more in the Barracks.")
                self.battle_screen = None
                self.state = GameState.NEST
            return

        if self.state == GameState.OUTSIDE:
            # Click on a raider during raid — deal damage
            if self.raid_event and self.raid_event.phase == "active":
                if self.raid_event.click_at(pos):
                    return  # consumed by raid click

            # Click on a leaf → assign ALL available workers, one piece each
            for leaf in list(self.outside.leaves):
                if leaf.get_rect().collidepoint(pos):
                    # Deselect previously selected leaf
                    for other in self.outside.leaves:
                        other.selected = False
                    leaf.selected = True

                    available_pieces = leaf.available_pieces()
                    if not available_pieces:
                        self.notify("This leaf is fully harvested!")
                        return

                    idle_workers = [a for a in self.workers
                                    if a.state in (AntState.IDLE, AntState.WANDER)]
                    if not idle_workers:
                        self.notify("All workers are busy! Wait for them to finish.")
                        return

                    dispatched = 0
                    nest_entrance = (W // 2, H // 2 + 30)
                    for i, piece in enumerate(available_pieces):
                        if i >= len(idle_workers):
                            break
                        worker = min(idle_workers,
                                     key=lambda a: math.hypot(a.x - leaf.x, a.y - leaf.y))
                        idle_workers.remove(worker)
                        worker.command_fetch_piece(piece, leaf, self.nest.rooms,
                                                   deposit_pos=nest_entrance)
                        dispatched += 1

                    self.notify(f"{dispatched} workers sent to harvest the leaf!")
                    SFX.play('dispatch')
                    return

        elif self.state == GameState.NEST:
            wx, wy = self.nest.s2w(pos[0], pos[1])
            wpos = (wx, wy)

            food_room = self.nest.get_room(RoomType.FOOD)
            leaf_room = self.nest.get_room(RoomType.LEAF)
            storage_room = self.nest.get_room(RoomType.STORAGE)

            # Click "Process all leaves" button on the food room
            if food_room:
                food_sr = self.nest.rect_w2s(food_room.rect)
                btn_rect_screen = pygame.Rect(food_sr.x + 4, food_sr.bottom - 26, food_sr.w - 8, 20)
                if btn_rect_screen.collidepoint(pos):
                    # Collect all pieces from leaf room + storage
                    all_pieces = []
                    for src in [r for r in [leaf_room, storage_room] if r]:
                        for piece in list(src.leaves):
                            if piece.carrier is None:
                                all_pieces.append(piece)
                    if not all_pieces:
                        self.notify("No leaf pieces to process! Send workers to harvest leaves first.")
                        return
                    # Dispatch idle nest workers, one per piece
                    idle = [a for a in self.workers
                            if a.state in (AntState.IDLE, AntState.WANDER)
                            and not getattr(a, '_in_outside', False)]
                    dispatched = 0
                    for piece in all_pieces:
                        if not idle:
                            break
                        worker = idle.pop(0)
                        worker.command_process(piece, food_room)
                        dispatched += 1
                    remaining = len(all_pieces) - dispatched
                    msg = f"{dispatched} workers sent to process leaves!"
                    if remaining > 0:
                        msg += f" ({remaining} pieces queued - need more idle workers)"
                    self.notify(msg)
                    SFX.play('dispatch')
                    return

            # If already holding a piece — click food room to deposit, anywhere else to cancel
            if self.dragging_leaf:
                if food_room and food_room.rect.collidepoint(wpos):
                    self._deposit_held_piece(food_room)
                else:
                    # Cancel — return piece to leaf room
                    target = leaf_room or storage_room
                    if target:
                        self.dragging_leaf.x = target.rect.x + random.randint(15, target.rect.w - 15)
                        self.dragging_leaf.y = target.rect.y + random.randint(25, target.rect.h - 15)
                        target.leaves.append(self.dragging_leaf)
                    self.dragging_leaf = None
                    self.notify("Cancelled.")
                return

            # Click on barracks → train a soldier (costs 3 food)
            barracks = self.nest.get_room(RoomType.BARRACKS)
            if barracks and barracks.rect.collidepoint(wpos):
                TRAIN_COST = 3
                if self.queen.food >= TRAIN_COST:
                    self.queen.food -= TRAIN_COST
                    new_sol = Ant(barracks.cx() + random.randint(-30,30),
                                  barracks.cy() + random.randint(-20,20),
                                  AntRole.SOLDIER, self.colony_color)
                    self.soldiers.append(new_sol)
                    SFX.play('dispatch')
                    self.notify(f"Soldier trained! ({len(self.soldiers)}/{MIN_SOLDIERS} needed) - 3 food spent.")
                else:
                    self.notify(f"Need 3 food to train a soldier. (have {self.queen.food})")
                return

            # Click on a stored piece to pick it up
            for room in [r for r in [leaf_room, storage_room] if r]:
                for piece in list(room.leaves):
                    if piece.get_rect().collidepoint(wpos):
                        if not food_room:
                            self.notify("Build a Food Lab first! (Shop -> Food Lab)")
                            return
                        self.dragging_leaf = piece
                        room.leaves.remove(piece)
                        SFX.play('pickup')
                        self.notify("Piece picked up - click the Food Lab to deposit!")
                        return

    def _deposit_held_piece(self, food_room):
        food_room.mushrooms.append({
            "x": food_room.rect.x + random.randint(20, food_room.rect.w - 20),
            "y": food_room.rect.y + random.randint(30, food_room.rect.h - 30),
            "grow": 0.0
        })
        food_gained = 1 + self.mushroom_yield_bonus
        self.queen.food += food_gained
        food_room.add_food_particle()
        SFX.play('food')
        self.notify(f"Converted! +{food_gained} food  (total: {self.queen.food})")
        for _ in range(15):
            self.particles.append(Particle(
                food_room.cx(), food_room.cy(),
                random.uniform(-70, 70), random.uniform(-90, -20),
                1.5, 1.5, C["mushroom"], 5))
        self.dragging_leaf = None

    def _handle_release(self, pos):
        # No longer used for drag-drop — kept for compatibility
        pass

    def draw_menu(self):
        self.screen.fill((10, 6, 2))
        t = self.menu_time
        for i in range(0, W, 50):
            for j in range(0, H, 50):
                shade = int(math.sin(t * 0.3 + i * 0.02 + j * 0.02) * 8)
                pygame.draw.rect(self.screen, (max(0, 15 + shade), max(0, 9 + shade), max(0, 3 + shade)), (i, j, 50, 50))

        # Animated ants crawling
        for i in range(8):
            phase = t * 30 + i * 45
            ax = int((phase % (W + 100)) - 50)
            ay = 120 + i * 60 + int(math.sin(t + i) * 20)
            ant_col = C["red_ant"] if i % 2 == 0 else C["black_ant"]
            pygame.draw.circle(self.screen, ant_col, (ax, ay), 8)
            pygame.draw.circle(self.screen, ant_col, (ax + 10, ay), 6)
            pygame.draw.circle(self.screen, ant_col, (ax - 9, ay), 7)

        title = FONT_XL.render("ANT COLONY", True, C["gold"])
        self.screen.blit(title, (W // 2 - title.get_width() // 2, H // 2 - 80))
        sub = FONT_LG.render("Simulator", True, (180, 140, 60))
        self.screen.blit(sub, (W // 2 - sub.get_width() // 2, H // 2 + 10))

        pulse = abs(math.sin(t * 2))
        start_col = tuple(int(c * (0.6 + 0.4 * pulse)) for c in C["gold"])
        start = FONT_MD.render("Click anywhere to begin", True, start_col)
        self.screen.blit(start, (W // 2 - start.get_width() // 2, H // 2 + 80))

        credit = FONT_SM.render("Build your empire. One tunnel at a time.", True, (80, 65, 40))
        self.screen.blit(credit, (W // 2 - credit.get_width() // 2, H - 40))

    def draw(self):
        if self.state == GameState.SPLASH:
            self.splash_screen.draw(self.screen)
        elif self.state == GameState.LOADING:
            self._draw_loading()
        elif self.state == GameState.BATTLE:
            if self.battle_screen:
                self.battle_screen.draw(self.screen)
            pygame.display.flip()
            return
        elif self.state == GameState.MENU:
            self.draw_menu()
        elif self.state == GameState.SELECT:
            self.select_screen.draw(self.screen)
        else:
            if self.state == GameState.OUTSIDE:
                self.outside.draw(self.screen)
                for leaf in self.outside.leaves:
                    if not leaf.fully_harvested:
                        leaf.draw(self.screen)
                for ant in self.workers:
                    ant.draw(self.screen)
                # Draw raiders and raid banner
                if self.raid_event:
                    self.raid_event.draw_raiders(self.screen)
                    self.raid_event.draw_banner(self.screen)
            else:
                self.nest.draw(self.screen, self.queen, self.workers, self.soldiers)

            # Shop overlay
            if self.state == GameState.SHOP:
                self.shop_screen.draw(self.screen, self)

            # Upgrades overlay
            if self.state == GameState.UPGRADES:
                self.upgrade_screen.draw(self.screen, self)

            # Particles
            for p in self.particles:
                p.draw(self.screen)

            # Held piece — draw following cursor
            if self.dragging_leaf and self.state in (GameState.NEST, GameState.SHOP, GameState.UPGRADES):
                mx, my = pygame.mouse.get_pos()
                self.dragging_leaf.x, self.dragging_leaf.y = mx, my
                self.dragging_leaf.draw(self.screen)

                food_room = self.nest.get_room(RoomType.FOOD)
                if food_room:
                    sr = self.nest.rect_w2s(food_room.rect)
                    highlight = pygame.Surface((sr.w, sr.h), pygame.SRCALPHA)
                    alpha = int(abs(math.sin(time.time() * 4)) * 120 + 60)
                    highlight.fill((max(0, C["gold"][0]), max(0, C["gold"][1]), max(0, C["gold"][2]), alpha))
                    self.screen.blit(highlight, sr.topleft)
                    lbl = FONT_SM.render("▼ CLICK TO DEPOSIT", True, C["gold"])
                    self.screen.blit(lbl, (sr.centerx - lbl.get_width() // 2, sr.y - 18))

                cancel = FONT_SM.render("Click elsewhere to cancel", True, (180, 140, 100))
                self.screen.blit(cancel, (mx + 14, my - 8))

            # HUD
            draw_hud(self.screen, self)

            # Notification
            if self.notif_timer > 0:
                alpha = min(255, int(self.notif_timer * 100))
                notif = FONT_MD.render(self.notification, True, C["gold"])
                nx = W // 2 - notif.get_width() // 2
                ny = H - 55
                bg_rect = pygame.Rect(nx - 10, ny - 5, notif.get_width() + 20, notif.get_height() + 10)
                bg_surf = pygame.Surface((bg_rect.w, bg_rect.h), pygame.SRCALPHA)
                bg_surf.fill((15, 8, 3, min(200, alpha)))
                self.screen.blit(bg_surf, bg_rect.topleft)
                self.screen.blit(notif, (nx, ny))

        pygame.display.flip()

    def run(self):
        running = True
        while running:
            dt = self.clock.tick(FPS) / 1000.0
            dt = min(dt, 0.05)  # cap delta time

            for event in pygame.event.get():
                if not self.handle_event(event):
                    running = False

            self.update(dt)
            self.draw()

        pygame.quit()


if __name__ == "__main__":
    game = Game()
    game.run()