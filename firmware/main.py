import time
import board
import busio
import neopixel

from kmk.kmk_keyboard import KMKKeyboard
from kmk.scanners.keypad import KeysScanner
from kmk.keys import KC, make_key
from kmk.modules import Module
from kmk.modules.layers import Layers
from kmk.modules.holdtap import HoldTap
from kmk.modules.tapdance import TapDance
from kmk.modules.combos import Combos, Chord
from kmk.modules.oneshot import OneShot


# ----------------------------
# Pin helpers (XIAO RP2040)
# ----------------------------
def pin(*names):
    """Return the first pin name that exists on this CircuitPython board."""
    for n in names:
        if hasattr(board, n):
            return getattr(board, n)
    raise AttributeError("Pin não encontrado: " + ", ".join(names))


# Switches (per schematic):
# SW1 -> GPIO3, SW2 -> GPIO4, SW3 -> GPIO2, SW4 -> GPIO1
PIN_SW1 = pin("GP3", "D3")
PIN_SW2 = pin("GP4", "D4")
PIN_SW3 = pin("GP2", "D2")
PIN_SW4 = pin("GP1", "D1")

# NOTE: KeysScanner uses list order as the key coordinate (0..n-1).
# This order matches your original behavior:
#   coord 0 = SW1 (top-left)
#   coord 1 = SW3 (bottom-left)
#   coord 2 = SW2 (top-right)
#   coord 3 = SW4 (bottom-right)
PINS = [PIN_SW1, PIN_SW3, PIN_SW2, PIN_SW4]

# LEDs (SK6812MINI-E) - DATA on GPIO0/TX (pin 7 on XIAO)
PIXEL_PIN = pin("GP0", "D0", "TX")
NUM_PIXELS = 6

# OLED I2C
I2C_SDA = pin("GP6", "D6")
I2C_SCL = pin("GP7", "D7")
OLED_ADDR = 0x3C
OLED_W = 128
OLED_H = 32


def kc_print_screen():
    """Best-effort PrintScreen keycode across KMK builds."""
    if hasattr(KC, "PSCR"):
        return KC.PSCR
    if hasattr(KC, "PRINT_SCREEN"):
        return KC.PRINT_SCREEN
    # Fallback: don't crash firmware if a build lacks PrintScreen.
    return KC.NO


# Custom keycodes to control LEDs via combos
BL_NEXT = make_key(names=("BL_NEXT",))
BL_EFF = make_key(names=("BL_EFF",))
BL_BRI = make_key(names=("BL_BRI",))


class BacklightFX(Module):
    """
    Themes/effects for 6 NeoPixels + key-react flashes.

    IMPORTANT (matches the schematic):
      Data enters D1 first, then D2..D6.
      Pixel indices therefore map as:
        0=D1, 1=D2, 2=D3, 3=D4, 4=D5, 5=D6
    """

    def __init__(self, pixel_pin, n):
        self.pixels = neopixel.NeoPixel(
            pixel_pin,
            n,
            brightness=0.12,
            auto_write=False,
            pixel_order=neopixel.GRB,
        )

        # Map from key coordinate (int_coord) -> pixel index
        # Coordinates come from PINS order above.
        self.under_keys = {
            0: 0,  # SW1 -> D1
            1: 2,  # SW3 -> D3
            2: 1,  # SW2 -> D2
            3: 3,  # SW4 -> D4
        }
        self.top_pixels = (4, 5)  # D5 and D6

        self.theme_i = 0
        self.effect_i = 0
        self.bri_i = 0
        self.brightness_steps = [0.06, 0.12, 0.20]

        # flash_end_time per pixel
        self.flash = [0.0] * n

        self._last_anim = 0.0
        self._anim_t = 0
        self._dirty = True
        self.active_layer = 0

        self.themes = [
            # (under_key_color, top_color_layer0, top_color_layer1)
            ((0, 18, 0), (0, 10, 0), (0, 0, 12)),     # Verde base / Azul layer1
            ((18, 0, 18), (12, 0, 12), (0, 10, 18)),  # Roxo / Cyan
            ((18, 6, 0), (18, 4, 0), (0, 8, 18)),     # Laranja / Azul
            ((0, 12, 18), (0, 10, 14), (18, 0, 6)),   # Azul / Rosa
            ((18, 18, 18), (10, 10, 10), (0, 10, 0)), # Branco suave / Verde layer1
        ]

        self.effects = ("static", "breathe", "rainbow")

    def name(self):
        return "BacklightFX"

    # ---- helpers ----
    def _active_layer_from_keyboard(self, keyboard):
        if getattr(keyboard, "active_layers", None):
            return keyboard.active_layers[0]
        st = getattr(keyboard, "_state", None)
        if st and getattr(st, "active_layers", None):
            return st.active_layers[0]
        return 0

    @staticmethod
    def _wheel(pos):
        pos = pos & 0xFF
        if pos < 85:
            return (pos * 3, 255 - pos * 3, 0)
        if pos < 170:
            pos -= 85
            return (255 - pos * 3, 0, pos * 3)
        pos -= 170
        return (0, pos * 3, 255 - pos * 3)

    @staticmethod
    def _scale(c, k):
        return (int(c[0] * k), int(c[1] * k), int(c[2] * k))

    def _any_flash_active(self, now):
        for t_end in self.flash:
            if now < t_end:
                return True
        return False

    # ---- renderers ----
    def _apply_static(self):
        under, top0, top1 = self.themes[self.theme_i]
        top = top0 if self.active_layer == 0 else top1

        self.pixels.fill((0, 0, 0))
        for i in self.top_pixels:
            if i < self.pixels.n:
                self.pixels[i] = top
        for px in self.under_keys.values():
            if px < self.pixels.n:
                self.pixels[px] = under

    def _apply_breathe(self):
        under, top0, top1 = self.themes[self.theme_i]
        top = top0 if self.active_layer == 0 else top1

        phase = (self._anim_t % 80) / 79.0
        k = phase * 2.0 if phase < 0.5 else (1.0 - phase) * 2.0

        self.pixels.fill((0, 0, 0))
        for i in self.top_pixels:
            if i < self.pixels.n:
                self.pixels[i] = self._scale(top, k)
        for px in self.under_keys.values():
            if px < self.pixels.n:
                self.pixels[px] = self._scale(under, k)

    def _apply_rainbow(self):
        self.pixels.fill((0, 0, 0))
        base = (self._anim_t * 4) & 0xFF
        for i in range(self.pixels.n):
            self.pixels[i] = self._wheel(base + i * 20)

    def _apply_flash(self, now):
        for i in range(self.pixels.n):
            if now < self.flash[i]:
                self.pixels[i] = (40, 40, 40)

    def _render(self, now=None):
        if now is None:
            now = time.monotonic()

        eff = self.effects[self.effect_i]
        if eff == "static":
            self._apply_static()
        elif eff == "breathe":
            self._apply_breathe()
        else:
            self._apply_rainbow()

        self._apply_flash(now)
        self.pixels.show()
        self._dirty = False

    # ---- KMK hooks ----
    def during_bootup(self, keyboard):
        self.pixels.brightness = self.brightness_steps[self.bri_i]
        self._render()

    def before_matrix_scan(self, keyboard):
        return

    def after_matrix_scan(self, keyboard):
        layer = self._active_layer_from_keyboard(keyboard)
        if layer != self.active_layer:
            self.active_layer = layer
            self._dirty = True

        now = time.monotonic()

        eff = self.effects[self.effect_i]
        wants_anim = eff in ("breathe", "rainbow")
        has_flash = self._any_flash_active(now)

        if not wants_anim and not has_flash and not self._dirty:
            return

        if self._dirty or (now - self._last_anim) > 0.04:
            self._last_anim = now
            if wants_anim:
                self._anim_t += 1
            self._render(now=now)

    def process_key(self, keyboard, key, is_pressed, int_coord):
        if not is_pressed:
            return key

        if int_coord is not None:
            px = self.under_keys.get(int_coord)
            if px is not None and px < self.pixels.n:
                self.flash[px] = time.monotonic() + 0.08
                self._dirty = True

        if key == BL_NEXT:
            self.theme_i = (self.theme_i + 1) % len(self.themes)
            self._dirty = True
            return KC.NO

        if key == BL_EFF:
            self.effect_i = (self.effect_i + 1) % len(self.effects)
            self._dirty = True
            return KC.NO

        if key == BL_BRI:
            self.bri_i = (self.bri_i + 1) % len(self.brightness_steps)
            self.pixels.brightness = self.brightness_steps[self.bri_i]
            self._dirty = True
            return KC.NO

        return key

    def info(self):
        return {
            "theme": self.theme_i,
            "effect": self.effects[self.effect_i],
            "brightness": self.brightness_steps[self.bri_i],
            "layer": self.active_layer,
        }


class OLEDStatus(Module):
    """
    OLED status:
      - name
      - layer/mode
      - backlight (theme/effect/brightness)
      - last key

    Works with 128x32 by using 4 lines (8px each).
    """

    def __init__(self, sda, scl, addr=0x3C, w=128, h=32, bl=None):
        self.sda = sda
        self.scl = scl
        self.addr = addr
        self.w = w
        self.h = h
        self.bl = bl

        self.oled = None
        self.last_key = "-"
        self._last_draw = 0.0
        self._last_state = None

    def _init_oled(self):
        try:
            import adafruit_ssd1306
        except Exception:
            return

        try:
            i2c = busio.I2C(self.scl, self.sda)
            t0 = time.monotonic()
            while not i2c.try_lock():
                if (time.monotonic() - t0) > 0.5:
                    return
            i2c.unlock()
        except Exception:
            return

        try:
            self.oled = adafruit_ssd1306.SSD1306_I2C(self.w, self.h, i2c, addr=self.addr)
            self.oled.fill(0)
            self.oled.show()
        except Exception:
            self.oled = None

    @staticmethod
    def _active_layer_from_keyboard(keyboard):
        if getattr(keyboard, "active_layers", None):
            return keyboard.active_layers[0]
        st = getattr(keyboard, "_state", None)
        if st and getattr(st, "active_layers", None):
            return st.active_layers[0]
        return 0

    def during_bootup(self, keyboard):
        self._init_oled()
        self._draw(keyboard, force=True)

    def before_matrix_scan(self, keyboard):
        return

    def after_matrix_scan(self, keyboard):
        self._draw(keyboard)

    def process_key(self, keyboard, key, is_pressed, int_coord):
        if is_pressed:
            s = str(key)
            self.last_key = s if len(s) <= 16 else (s[:15] + "…")
        return key

    def _draw(self, keyboard, force=False):
        if self.oled is None:
            return

        now = time.monotonic()
        if not force and (now - self._last_draw) < 0.20:
            return

        layer = self._active_layer_from_keyboard(keyboard)
        mode = "BASE" if layer == 0 else f"L{layer}"

        info = self.bl.info() if self.bl else {}
        theme = info.get("theme", 0)
        eff = info.get("effect", "static")
        bri = info.get("brightness", 0.0)

        state = (mode, theme, eff, round(float(bri), 2), self.last_key)
        if not force and state == self._last_state:
            return

        self._last_state = state
        self._last_draw = now

        self.oled.fill(0)
        self.oled.text("TheusHen", 0, 0, 1)
        self.oled.text(f"Mode: {mode}", 0, 8, 1)
        self.oled.text(f"BL t{theme} {eff[:4]} b{bri:.2f}", 0, 16, 1)
        self.oled.text(f"Last: {self.last_key}", 0, 24, 1)
        self.oled.show()


# ----------------------------
# KMK setup
# ----------------------------
keyboard = KMKKeyboard()

keyboard.matrix = KeysScanner(
    pins=PINS,
    value_when_pressed=False,
)

holdtap = HoldTap()
holdtap.tap_time = 220
keyboard.modules.append(holdtap)

tapdance = TapDance()
tapdance.tap_time = 275
keyboard.modules.append(tapdance)

oneshot = OneShot()
keyboard.modules.append(oneshot)

layers = Layers()
keyboard.modules.append(layers)

combos = Combos()
keyboard.modules.append(combos)

backlight = BacklightFX(PIXEL_PIN, NUM_PIXELS)
keyboard.modules.append(backlight)

oled = OLEDStatus(I2C_SDA, I2C_SCL, addr=OLED_ADDR, w=OLED_W, h=OLED_H, bl=backlight)
keyboard.modules.append(oled)

# ----------------------------
# Key behavior (unchanged)
# ----------------------------
OS_LALT = KC.OS(KC.LALT, tap_time=None)

K_B1 = KC.HT(
    KC.TD(
        KC.LGUI,              # 1 toque: Super
        KC.LCTL(KC.T),        # 2 toques: Nova aba
        KC.TG(1),             # 3 toques: Toggle Browser Tabs (layer 1)
    ),
    KC.LCTL(KC.W),            # segurar: Fechar aba
)

K_B2 = KC.HT(
    OS_LALT,                  # toque: Alt (one-shot)
    KC.LCTL,                  # segurar: Ctrl
    prefer_hold=True,
)

K_B3 = KC.HT(
    KC.LCTL(KC.C),            # toque: Copiar
    KC.LCTL(KC.X),            # segurar: Cortar
)

K_B4 = KC.HT(
    KC.TD(
        KC.LCTL(KC.V),                     # 1 toque: Colar
        KC.LCTL(KC.LSFT(KC.T)),            # 2 toques: Reabrir aba
        KC.LGUI(KC.LSFT(KC.S)),            # 3 toques: Recorte (Win+Shift+S)
    ),
    kc_print_screen(),          # segurar: PrintScreen
)

combos.combos = [
    Chord((K_B1, K_B2), KC.LALT(KC.TAB), timeout=180),
    Chord((K_B1, K_B2, K_B3), KC.LALT(KC.LSFT(KC.TAB)), timeout=220),

    Chord((K_B3, K_B4), BL_NEXT, timeout=220),
    Chord((K_B2, K_B3, K_B4), BL_EFF, timeout=250),
    Chord((K_B1, K_B4), BL_BRI, timeout=220),
]

keyboard.keymap = [
    [K_B1, K_B2, K_B3, K_B4],
    [
        KC.TG(1),
        KC.LCTL(KC.TAB),
        KC.LCTL(KC.LSFT(KC.TAB)),
        KC.HT(KC.LCTL(KC.T), KC.LCTL(KC.W)),
    ],
]

if __name__ == "__main__":
    keyboard.go()