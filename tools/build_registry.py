#!/usr/bin/env python3
"""Build the starter resources in registry/ and regenerate registry/index.json.

registry/ is the public resource registry that Hyper OS Creator reads from
GitHub by default. To add your own resource: build a .hyperpkg (in the app:
Resources -> Publish -> "Just download the package", or with
``hyperos resources create/pack``), copy it into registry/packages/, run
``python tools/build_registry.py`` and open a pull request.
"""
import json
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from hyperos import resources  # noqa: E402

REGISTRY = ROOT / "registry"
AUTHOR = "Hyper OS Creator team"


def theme(desktop, box, text, shell, banner):
    pair = lambda v: {"fg": v[0], "bg": v[1]}  # noqa: E731
    return {"theme.json": json.dumps({"desktop": pair(desktop), "box": pair(box), "text": pair(text),
                                      "shell": pair(shell), "banner": pair(banner)}, indent=2)}


CLASSIC_DESKTOP = {"elements": [
    {"type": "fill", "fg": 15, "bg": 3},
    {"type": "text", "x": 2, "y": 1, "fg": 15, "bg": 3, "text": "[#] My Computer"},
    {"type": "text", "x": 2, "y": 3, "fg": 15, "bg": 3, "text": "[=] Documents"},
    {"type": "text", "x": 2, "y": 5, "fg": 15, "bg": 3, "text": "[@] Internet"},
    {"type": "text", "x": 2, "y": 7, "fg": 15, "bg": 3, "text": "[x] Recycle Bin"},
    {"type": "box", "x": 22, "y": 4, "w": 44, "h": 13, "fg": 0, "bg": 7, "style": "double", "title": " Welcome "},
    {"type": "box", "x": 22, "y": 4, "w": 44, "h": 3, "fg": 15, "bg": 1, "style": "double", "title": " Welcome "},
    {"type": "text", "x": 25, "y": 8, "fg": 0, "bg": 7, "text": "Thanks for trying my operating system."},
    {"type": "text", "x": 25, "y": 10, "fg": 0, "bg": 7, "text": "Press any key to open the shell and"},
    {"type": "text", "x": 25, "y": 11, "fg": 0, "bg": 7, "text": "type 'help' to see what it can do."},
    {"type": "box", "x": 50, "y": 13, "w": 12, "h": 3, "fg": 15, "bg": 2, "style": "single", "title": ""},
    {"type": "text", "x": 54, "y": 14, "fg": 15, "bg": 2, "text": "OK"},
    {"type": "box", "x": 0, "y": 23, "w": 80, "h": 2, "fg": 0, "bg": 7, "style": "none", "title": ""},
    {"type": "text", "x": 0, "y": 24, "fg": 15, "bg": 2, "text": " Start "},
    {"type": "text", "x": 9, "y": 24, "fg": 0, "bg": 7, "text": "| Welcome |"},
    {"type": "text", "x": 73, "y": 24, "fg": 0, "bg": 7, "text": "12:00"},
]}

TERMINAL_LAYOUT = {"elements": [
    {"type": "fill", "fg": 10, "bg": 0},
    {"type": "box", "x": 4, "y": 2, "w": 72, "h": 20, "fg": 10, "bg": 0, "style": "single", "title": " tty0 "},
    {"type": "text", "x": 7, "y": 4, "fg": 10, "bg": 0, "text": "> booting kernel ............... ok"},
    {"type": "text", "x": 7, "y": 5, "fg": 10, "bg": 0, "text": "> mounting imagination ......... ok"},
    {"type": "text", "x": 7, "y": 6, "fg": 10, "bg": 0, "text": "> loading coffee driver ........ ok"},
    {"type": "text", "x": 7, "y": 7, "fg": 10, "bg": 0, "text": "> starting shell ............... ok"},
    {"type": "text", "x": 7, "y": 10, "fg": 15, "bg": 0, "text": "SYSTEM READY."},
    {"type": "text", "x": 7, "y": 19, "fg": 2, "bg": 0, "text": "press any key to continue_"},
]}

FUN_COMMANDS = [
    {"name": "joke", "output": "Why do programmers prefer dark mode?\nBecause light attracts bugs!"},
    {"name": "fortune", "output": "You will write a bootloader that boots on the first try.\n(Results may vary.)"},
    {"name": "cowsay", "output": " _____________\n< Moo, world! >\n -------------\n        \\   ^__^\n         \\  (oo)\\_______\n"
                                 "            (__)\\       )\\/\\\n                ||----w |\n                ||     ||"},
    {"name": "coffee", "output": "    ( (\n     ) )\n  ........\n  |      |]\n  \\      /\n   `----'\nHere is your coffee."},
    {"name": "matrix", "output": "Wake up...\nThe Matrix has you.\nFollow the white rabbit."},
    {"name": "hack", "output": "ACCESS GRANTED\n(just kidding - this is your own computer)"},
]

OS_FACTS = [
    {"name": "fact1", "output": "The BIOS loads exactly 512 bytes - the boot sector - to address 0x7C00."},
    {"name": "fact2", "output": "Text mode video memory starts at 0xB8000: one byte for the character, one for the colour."},
    {"name": "fact3", "output": "The first version of Linux (1991) was about 10,000 lines of code."},
    {"name": "fact4", "output": "'Real mode' dates back to the Intel 8086 from 1978. PCs still start in it today."},
    {"name": "fact5", "output": "The 0x55 0xAA boot signature tells the BIOS a disk is bootable."},
    {"name": "facts", "output": "Type fact1, fact2, fact3, fact4 or fact5 to learn something about operating systems."},
]

POCKET_OS = {
    "name": "Pocket OS", "version": "1.0", "description": "A tiny, friendly OS with a classic desktop and fun commands",
    "author": AUTHOR,
    "bootloader": {"type": "hyperboot", "banner": "Pocket OS is waking up...", "fg": 14, "bg": 3, "wait_key": False,
                   "source": "boot.asm"},
    "kernel": {"type": "hyperkernel", "source": "kernel.asm"},
    "shell": {"prompt": "pocket> ", "motd": "Pocket OS - small but mighty. Try: joke, cowsay, fortune, help",
              "fg": 15, "bg": 1},
    "ui": CLASSIC_DESKTOP,
    "commands": FUN_COMMANDS,
}

VGA_SNIPPET = """; vga_print - write a zero terminated string straight into VGA text memory
; in:  DS:SI = string, DH = row, DL = column, BL = colour attribute
vga_print:
    pusha
    push es
    mov ax, 0xB800
    mov es, ax
    xor ax, ax
    mov al, dh
    mov cx, 80
    mul cx              ; ax = row * 80
    xor dh, dh
    add ax, dx          ; + column
    shl ax, 1           ; * 2 bytes per cell
    mov di, ax
    mov ah, bl
.next:
    lodsb
    test al, al
    jz .done
    stosw
    jmp .next
.done:
    pop es
    popa
    ret
"""

SEEDS = [
    ({"name": "Retro Amber", "type": "theme", "tags": ["retro", "amber", "dark"],
      "description": "Warm amber-on-black like an 80s terminal."},
     theme((14, 0), (6, 0), (14, 0), (14, 0), (0, 6))),
    ({"name": "Ocean Breeze", "type": "theme", "tags": ["blue", "calm"],
      "description": "Calm blues and cyans."},
     theme((11, 1), (15, 3), (15, 1), (11, 1), (15, 3))),
    ({"name": "Hacker Green", "type": "theme", "tags": ["green", "hacker", "dark"],
      "description": "Bright green on black. Very mysterious."},
     theme((10, 0), (2, 0), (10, 0), (10, 0), (0, 2))),
    ({"name": "Sunset", "type": "theme", "tags": ["warm", "colourful"],
      "description": "Magenta desktop with yellow windows."},
     theme((14, 5), (0, 6), (15, 5), (14, 5), (15, 4))),
    ({"name": "Classic Desktop", "type": "ui-layout", "tags": ["desktop", "icons", "taskbar"],
      "description": "Desktop icons, a welcome window and a taskbar with a Start button."},
     {"ui.json": json.dumps(CLASSIC_DESKTOP, indent=2)}),
    ({"name": "Terminal Boot", "type": "ui-layout", "tags": ["terminal", "green", "boot"],
      "description": "A retro boot log screen."},
     {"ui.json": json.dumps(TERMINAL_LAYOUT, indent=2)}),
    ({"name": "Fun Commands", "type": "command-pack", "tags": ["fun", "jokes", "ascii"],
      "description": "joke, fortune, cowsay, coffee, matrix and hack."},
     {"commands.json": json.dumps(FUN_COMMANDS, indent=2)}),
    ({"name": "OS Facts", "type": "command-pack", "tags": ["learning", "facts"],
      "description": "Commands that teach fun facts about operating systems."},
     {"commands.json": json.dumps(OS_FACTS, indent=2)}),
    ({"name": "Pocket OS", "type": "system-template", "tags": ["starter", "desktop"],
      "description": "A complete starter system: classic desktop, fun commands and a cheerful boot banner."},
     {"system.json": json.dumps(POCKET_OS, indent=2)}),
    ({"name": "VGA print routine", "type": "snippet", "tags": ["asm", "vga", "real-mode"],
      "description": "Print coloured text anywhere on screen by writing to video memory."},
     {"vga_print.asm": VGA_SNIPPET}),
]


def main() -> None:
    packages = REGISTRY / "packages"
    packages.mkdir(parents=True, exist_ok=True)
    for meta, files in SEEDS:
        meta = {"author": AUTHOR, "version": "1.0.0", **meta}
        data = resources.make_package(meta, {k: v.encode() for k, v in files.items()})
        manifest = resources.read_package(data)["manifest"]
        out = packages / f"{manifest['id']}-{manifest['version']}.hyperpkg"
        # keep the file stable if nothing but the build date changed
        if not out.exists() or _content(out.read_bytes()) != _content(data):
            out.write_bytes(data)
    index = resources.rebuild_index(REGISTRY)
    print(f"registry: {len(index['resources'])} resources")


def _content(data: bytes):
    pkg = resources.read_package(data)
    m = {k: v for k, v in pkg["manifest"].items() if k != "created"}
    return m, pkg["files"]


if __name__ == "__main__":
    main()
