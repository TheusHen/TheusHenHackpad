import board

from kmk.kmk_keyboard import KMKKeyboard
from kmk.scanners.keypad import KeysScanner
from kmk.keys import KC

from kmk.modules.combos import Combos, Chord
from kmk.modules.holdtap import HoldTap
from kmk.modules.oneshot import OneShot
from kmk.modules.tapdance import TapDance
from kmk.modules.layers import Layers
from kmk.modules.macros import Press, Release, Tap, Macros

# Keyboard base
keyboard = KMKKeyboard()

PINS = [board.D3, board.D4, board.D2, board.D1]

keyboard.matrix = KeysScanner(
    pins=PINS,
    value_when_pressed=False,
)
combos = Combos()
keyboard.modules.append(combos)

holdtap = HoldTap()
holdtap.tap_time = 220
keyboard.modules.append(holdtap)

oneshot = OneShot()
oneshot.tap_time = 1200
keyboard.modules.append(oneshot)

tapdance = TapDance()
tapdance.tap_time = 280
keyboard.modules.append(tapdance)

keyboard.modules.append(Layers())

macros = Macros()
keyboard.modules.append(macros)

# ------
# Macros
# ------
ALT_TAB = KC.Macro(
    Press(KC.LALT),
    Tap(KC.TAB),
    Release(KC.LALT),
)

ALT_SHIFT_TAB = KC.Macro(
    Press(KC.LALT),
    Press(KC.LSFT),
    Tap(KC.TAB),
    Release(KC.LSFT),
    Release(KC.LALT),
)

NEW_TAB = KC.Macro(Press(KC.LCTL), Tap(KC.T), Release(KC.LCTL))
CLOSE_TAB = KC.Macro(Press(KC.LCTL), Tap(KC.W), Release(KC.LCTL))
REOPEN_TAB = KC.Macro(
    Press(KC.LCTL),
    Press(KC.LSFT),
    Tap(KC.T),
    Release(KC.LSFT),
    Release(KC.LCTL),
)

NEXT_TAB = KC.Macro(Press(KC.LCTL), Tap(KC.TAB), Release(KC.LCTL))
PREV_TAB = KC.Macro(
    Press(KC.LCTL),
    Press(KC.LSFT),
    Tap(KC.TAB),
    Release(KC.LSFT),
    Release(KC.LCTL),
)

COPY = KC.Macro(Press(KC.LCTL), Tap(KC.C), Release(KC.LCTL))
CUT = KC.Macro(Press(KC.LCTL), Tap(KC.X), Release(KC.LCTL))
PASTE = KC.Macro(Press(KC.LCTL), Tap(KC.V), Release(KC.LCTL))

OS_CTRL = KC.OS(KC.LCTL)

# ---------------
# Key definitions
# ---------------

# Botão 1
# 1 toque: Super
# 2 toques: Nova aba
# Segurar: Fechar aba
B1 = KC.TD(
    KC.HT(KC.LGUI, CLOSE_TAB, prefer_hold=False),
    NEW_TAB,
)

# Botão 2
# 1 toque: Ctrl (OneShot)
# Segurar: Alt
# 2 toques: Toggle modo Browser Tabs (Layer 1)
B2 = KC.TD(
    KC.HT(OS_CTRL, KC.LALT, prefer_hold=True),
    KC.TG(1),
)

# Botão 3
# 1 toque: Copiar
# 2 toques: Cortar
B3 = KC.TD(
    COPY,
    CUT,
)

# Botão 4
# 1 toque: Colar
# 2 toques: Reabrir aba
# Segurar: Print Screen
B4 = KC.TD(
    KC.HT(PASTE, KC.PSCREEN, prefer_hold=False),
    REOPEN_TAB,
)

# Combos
combos.combos = [
    # Alt + Tab
    Chord((0, 1), ALT_TAB, match_coord=True, timeout=250),

    # Alt + Shift + Tab
    Chord((0, 1, 2), ALT_SHIFT_TAB, match_coord=True, timeout=400),
]

# Keymap
keyboard.keymap = [
    # Layer 0
    [B1, B2, B3, B4],

    # Layer 1 - Browser Tabs
    [PREV_TAB, KC.TRNS, NEXT_TAB, KC.TD(CLOSE_TAB, REOPEN_TAB)],
]

if __name__ == "__main__":
    keyboard.go()
