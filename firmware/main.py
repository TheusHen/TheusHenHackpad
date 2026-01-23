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


def pin(*names):
    for n in names:
        if hasattr(board, n):
            return getattr(board, n)
    raise AttributeError("Pin não encontrado: " + ", ".join(names))

PIN_SW1 = pin("GP3", "D3")  # Tab/Super (top-left)
PIN_SW2 = pin("GP4", "D4")  # X/C (top-right)
PIN_SW3 = pin("GP2", "D2")  # Alt/Ctrl (bottom-left)
PIN_SW4 = pin("GP1", "D1")  # PrtSc/V (bottom-right)

PINS = [PIN_SW1, PIN_SW3, PIN_SW2, PIN_SW4]

# --- LEDs (SK6812MINI-E) - DATA no GPIO0/TX (pino 7 do XIAO)
PIXEL_PIN = pin("GP0", "D0", "TX")
NUM_PIXELS = 6

# --- OLED I2C
I2C_SDA = pin("GP6", "D6")
I2C_SCL = pin("GP7", "D7")
OLED_ADDR = 0x3C
OLED_W = 128
OLED_H = 32


def kc_print_screen():
    if hasattr(KC, "PSCR"):
        return KC.PSCR
    if hasattr(KC, "PRINT_SCREEN"):
        return KC.PRINT_SCREEN
    return KC.PSCR


# --- Keycodes custom para controlar LEDs
BL_NEXT = make_key(names=("BL_NEXT",))
BL_EFF = make_key(names=("BL_EFF",))
BL_BRI = make_key(names=("BL_BRI",))


class BacklightFX(Module):
    """Temas/efeitos para 6 NeoPixels + reação por tecla."""

    def __init__(self, pixel_pin, n):
        self.pixels = neopixel.NeoPixel(
            pixel_pin,
            n,
            brightness=0.12,
            auto_write=False,
            pixel_order=neopixel.GRB,
        )


        self.under_keys = {
            0: 5,  # SW1 -> D1
            1: 4,  # SW3 -> D2
            2: 3,  # SW2 -> D3
            3: 2,  # SW4 -> D4
        }
        self.top_pixels = (0, 1)  # D6 e D5

        self.theme_i = 0
        self.effect_i = 0
        self.bri_i = 0
        self.brightness_steps = [0.06, 0.12, 0.20]

        self.flash = [0.0] * n
        self._last_anim = 0.0
        self._anim_t = 0

        self.themes = [
            # (under_key_color, top_color_layer0, top_color_layer1)
            ((0, 18, 0), (0, 10, 0), (0, 0, 12)),     # Verde base / Azul layer1
            ((18, 0, 18), (12, 0, 12), (0, 10, 18)),  # Roxo / Cyan
            ((18, 6, 0), (18, 4, 0), (0, 8, 18)),     # Laranja / Azul
            ((0, 12, 18), (0, 10, 14), (18, 0, 6)),   # Azul / Rosa
            ((18, 18, 18), (10, 10, 10), (0, 10, 0)), # Branco suave / Verde layer1
        ]

        self.effects = ["static", "breathe", "rainbow"]

        self.active_layer = 0

    def name(self):
        return "BacklightFX"

    def set_layer(self, layer):
        self.active_layer = layer

    def _wheel(self, pos):
        pos = pos % 256
        if pos < 85:
            return (pos * 3, 255 - pos * 3, 0)
        if pos < 170:
            pos -= 85
            return (255 - pos * 3, 0, pos * 3)
        pos -= 170
        return (0, pos * 3, 255 - pos * 3)

    def _apply_static(self):
        under, top0, top1 = self.themes[self.theme_i]
        top = top0 if self.active_layer == 0 else top1

        self.pixels.fill((0, 0, 0))
        for i in range(self.pixels.n):
            self.pixels[i] = (0, 0, 0)

        for i in self.top_pixels:
            if i < self.pixels.n:
                self.pixels[i] = top

        for _, px in self.under_keys.items():
            if px < self.pixels.n:
                self.pixels[px] = under

    def _apply_breathe(self):
        under, top0, top1 = self.themes[self.theme_i]
        top = top0 if self.active_layer == 0 else top1

        phase = (self._anim_t % 80) / 79.0
        if phase < 0.5:
            k = phase * 2.0
        else:
            k = (1.0 - phase) * 2.0

        def scale(c):
            return (int(c[0] * k), int(c[1] * k), int(c[2] * k))

        self.pixels.fill((0, 0, 0))
        for i in self.top_pixels:
            if i < self.pixels.n:
                self.pixels[i] = scale(top)
        for _, px in self.under_keys.items():
            if px < self.pixels.n:
                self.pixels[px] = scale(under)

    def _apply_rainbow(self):
        self.pixels.fill((0, 0, 0))
        base = (self._anim_t * 4) & 0xFF
        for i in range(self.pixels.n):
            self.pixels[i] = self._wheel(base + i * 20)

    def _apply_flash(self):
        now = time.monotonic()
        for i in range(self.pixels.n):
            if now < self.flash[i]:
                self.pixels[i] = (40, 40, 40)

    def _render(self):
        if self.effects[self.effect_i] == "static":
            self._apply_static()
        elif self.effects[self.effect_i] == "breathe":
            self._apply_breathe()
        else:
            self._apply_rainbow()

        self._apply_flash()
        self.pixels.show()

    def during_bootup(self, keyboard):
        self.pixels.brightness = self.brightness_steps[self.bri_i]
        self._render()

    def before_matrix_scan(self, keyboard):
        return

    def after_matrix_scan(self, keyboard):
        layer = 0
        if hasattr(keyboard, "active_layers") and keyboard.active_layers:
            layer = keyboard.active_layers[0]
        elif hasattr(keyboard, "_state") and keyboard._state and keyboard._state.active_layers:
            layer = keyboard._state.active_layers[0]

        if layer != self.active_layer:
            self.active_layer = layer

        now = time.monotonic()
        if now - self._last_anim > 0.04:
            self._last_anim = now
            self._anim_t += 1
            self._render()

    def process_key(self, keyboard, key, is_pressed, int_coord):
        if is_pressed:
            if int_coord is not None:
                px = self.under_keys.get(int_coord, None)
                if px is not None and px < self.pixels.n:
                    self.flash[px] = time.monotonic() + 0.08

            if key == BL_NEXT:
                self.theme_i = (self.theme_i + 1) % len(self.themes)
                self._render()
                return KC.NO

            if key == BL_EFF:
                self.effect_i = (self.effect_i + 1) % len(self.effects)
                self._render()
                return KC.NO

            if key == BL_BRI:
                self.bri_i = (self.bri_i + 1) % len(self.brightness_steps)
                self.pixels.brightness = self.brightness_steps[self.bri_i]
                self._render()
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
    """OLED status: nome, layer, tema/efeito/brilho, última tecla."""

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

    def _init_oled(self):
        try:
            import adafruit_ssd1306
        except Exception:
            return

        try:
            i2c = busio.I2C(self.scl, self.sda)
            while not i2c.try_lock():
                pass
            i2c.unlock()
        except Exception:
            return

        try:
            self.oled = adafruit_ssd1306.SSD1306_I2C(
                self.w, self.h, i2c, addr=self.addr
            )
            self.oled.fill(0)
            self.oled.show()
        except Exception:
            self.oled = None

    def during_bootup(self, keyboard):
        self._init_oled()
        self._draw(force=True)

    def before_matrix_scan(self, keyboard):
        return

    def after_matrix_scan(self, keyboard):
        self._draw()

    def process_key(self, keyboard, key, is_pressed, int_coord):
        if is_pressed:
            self.last_key = str(key)
        return key

    def _active_layer(self, keyboard):
        if hasattr(keyboard, "active_layers") and keyboard.active_layers:
            return keyboard.active_layers[0]
        if hasattr(keyboard, "_state") and keyboard._state and keyboard._state.active_layers:
            return keyboard._state.active_layers[0]
        return 0

    def _draw(self, force=False):
        if self.oled is None:
            return

        now = time.monotonic()
        if not force and (now - self._last_draw) < 0.25:
            return
        self._last_draw = now

        layer = self._active_layer(keyboard)
        mode = "BASE" if layer == 0 else "BROWSER"

        info = self.bl.info() if self.bl else {}
        theme = info.get("theme", 0)
        eff = info.get("effect", "static")
        bri = info.get("brightness", 0.0)

        self.oled.fill(0)
        self.oled.text("TheusHen", 0, 0, 1)
        self.oled.text(f"Mode: {mode}", 0, 10, 1)
        self.oled.text(f"BL t{theme} {eff} b{bri:.2f}", 0, 20, 1)
        if self.h >= 64:
            self.oled.text(f"Last: {self.last_key[:18]}", 0, 30, 1)
        self.oled.show()


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

# Combos:
# - B3+B4: troca tema de cor dos LEDs (debaixo das teclas)
# - B2+B3+B4: troca efeito (static/breathe/rainbow)
# - B1+B4: troca brilho (low/med/high)
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
