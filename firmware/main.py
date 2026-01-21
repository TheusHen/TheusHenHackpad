import time
import board
import neopixel

from kmk.kmk_keyboard import KMKKeyboard
from kmk.scanners.keypad import KeysScanner
from kmk.keys import KC
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

PIXEL_PIN = pin("GP6", "D6")
NUM_PIXELS = 2


def kc_print_screen():
    if hasattr(KC, "PSCR"):
        return KC.PSCR
    if hasattr(KC, "PRINT_SCREEN"):
        return KC.PRINT_SCREEN
    return KC.PSCR


class NeoLayerStatus(Module):
    def __init__(self, pixel_pin, n):
        self.pixels = neopixel.NeoPixel(
            pixel_pin,
            n,
            brightness=0.12,
            auto_write=False,
            pixel_order=neopixel.GRB,
        )
        self.flash_until = 0.0

    def _active_layer(self, keyboard):
        if hasattr(keyboard, "active_layers") and keyboard.active_layers:
            return keyboard.active_layers[0]
        if hasattr(keyboard, "_state") and keyboard._state and keyboard._state.active_layers:
            return keyboard._state.active_layers[0]
        return 0

    def _paint(self, layer, flash=False):
        if layer == 0:
            base0, base1 = (0, 18, 0), (0, 0, 0)
        else:
            base0, base1 = (0, 0, 18), (0, 0, 10)

        self.pixels[0] = base0
        self.pixels[1] = (18, 18, 18) if flash else base1
        self.pixels.show()

    def during_bootup(self, keyboard):
        self._paint(self._active_layer(keyboard), flash=True)

    def before_matrix_scan(self, keyboard):
        return

    def after_matrix_scan(self, keyboard):
        layer = self._active_layer(keyboard)
        now = time.monotonic()
        self._paint(layer, flash=(now < self.flash_until))

    def process_key(self, keyboard, key, is_pressed, int_coord):
        if is_pressed:
            self.flash_until = time.monotonic() + 0.08
        return key

    def before_hid_send(self, keyboard):
        return

    def after_hid_send(self, keyboard):
        return

    def on_powersave_enable(self, keyboard):
        self.pixels.fill((0, 0, 0))
        self.pixels.show()

    def on_powersave_disable(self, keyboard):
        self._paint(self._active_layer(keyboard), flash=True)


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

keyboard.modules.append(NeoLayerStatus(PIXEL_PIN, NUM_PIXELS))


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
    Chord((K_B1, K_B2), KC.LALT(KC.TAB), timeout=180),                 # Alt+Tab
    Chord((K_B1, K_B2, K_B3), KC.LALT(KC.LSFT(KC.TAB)), timeout=220),  # Alt+Shift+Tab
]

keyboard.keymap = [
    [K_B1, K_B2, K_B3, K_B4],
    [
        KC.TG(1),                         # sair do modo Browser Tabs
        KC.LCTL(KC.TAB),                  # próxima aba
        KC.LCTL(KC.LSFT(KC.TAB)),         # aba anterior
        KC.HT(KC.LCTL(KC.T), KC.LCTL(KC.W)),  # toque: nova aba | segurar: fechar aba
    ],
]

if __name__ == "__main__":
    keyboard.go()
