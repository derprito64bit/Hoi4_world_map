"""P00b in-game experiment kit (EXP-01..EXP-09).

Every experiment copies the vanilla files it needs from the local game install
(``HOI4_GAME_DIR``) into ``build/experiments/<ID>/`` at build time, applies one
change, and writes ``descriptor.mod`` + ``README.txt``. Nothing from the game
folder is ever written into the repository.

Entry points: ``tools/experiments/build.py`` and ``tools/experiments/install.py``.
"""
