"""Tips shown in the app and on the command line."""
from __future__ import annotations

import random
from typing import Dict, List, Optional

TIPS: List[Dict[str, str]] = [
    # getting started
    {"topic": "start", "tip": "New here? Create a system, press Build, then Run. You have a bootable OS in under a minute."},
    {"topic": "start", "tip": "Every system builds into two files: a .img (floppy/USB image) and a .iso (CD image). Both boot in QEMU and VirtualBox."},
    {"topic": "start", "tip": "No tools needed: HyperBoot and HyperKernel are built in, so building works even without NASM installed."},
    {"topic": "start", "tip": "Install QEMU to test your system with one click: 'sudo apt install qemu-system-x86' or download it from qemu.org."},
    {"topic": "start", "tip": "To try your ISO in VirtualBox: New VM -> Type 'Other', Version 'DOS' or 'Other/Unknown' -> attach the .iso as an optical drive."},
    # ui editor
    {"topic": "ui", "tip": "UI editor: drag elements to move them, drag the bottom-right corner of a box to resize it."},
    {"topic": "ui", "tip": "UI editor: use arrow keys to nudge the selected element, Delete to remove it and Ctrl+D to duplicate it."},
    {"topic": "ui", "tip": "The screen is 80 columns x 25 rows of text - exactly what the real VGA text mode shows."},
    {"topic": "ui", "tip": "Double boxes look great for title bars, single boxes for windows. Try the 'block' style for chunky buttons."},
    {"topic": "ui", "tip": "Colours 8-15 are the bright versions of 0-7. Bright backgrounds may blink on some real hardware."},
    {"topic": "ui", "tip": "Elements are drawn top to bottom in the layer list: put the fill first and text after the box it sits on."},
    # code editor
    {"topic": "code", "tip": "Code editor: press Ctrl+Space for suggestions and Tab to expand snippets like 'print', 'loop' or 'bootsector'."},
    {"topic": "code", "tip": "Hover over an instruction such as 'int' or 'lodsb' in the reference panel to learn what it does."},
    {"topic": "code", "tip": "Build errors are clickable: click one to jump to the line that caused it."},
    {"topic": "code", "tip": "Ctrl+S saves, Ctrl+B builds, Ctrl+/ toggles a comment, Ctrl+F finds text."},
    {"topic": "code", "tip": "A boot sector must be exactly 512 bytes and end with 'dw 0xAA55'. Use 'times 510-($-$$) db 0' to pad it."},
    {"topic": "code", "tip": "Real mode code uses 'bits 16'. After switching to protected mode use 'bits 32' - see the pmode kernel template."},
    {"topic": "code", "tip": "BIOS interrupts are your friends in real mode: int 0x10 = video, int 0x13 = disk, int 0x16 = keyboard."},
    # bootloaders
    {"topic": "bootloader", "tip": "HyperBoot reads the disk geometry from the BIOS, so the same image boots from floppy, hard disk and CD."},
    {"topic": "bootloader", "tip": "Want a real-world bootloader? Download Limine or GRUB from the Bootloaders page - Limine is a favourite for hobby OSes."},
    {"topic": "bootloader", "tip": "The 'Key menu' template shows how to make a boot menu - a great next step after 'Hello boot sector'."},
    {"topic": "bootloader", "tip": "HyperSplash fits a whole coloured screen in one 512-byte sector - try it as a boot-time easter egg."},
    # kernels
    {"topic": "kernel", "tip": "Custom commands are the easiest way to personalise your kernel - add them on the system page, no code needed."},
    {"topic": "kernel", "tip": "The Alpine 'virt' prebuilt kernel boots instantly with: qemu-system-x86_64 -kernel vmlinuz-virt -initrd initramfs-virt"},
    {"topic": "kernel", "tip": "Building Linux from source? Start with the 'tinyconfig' base and enable only the features you need - it builds in minutes."},
    {"topic": "kernel", "tip": "The Multiboot C kernel template can be booted directly by QEMU with 'qemu-system-i386 -kernel kernel.elf'."},
    # iso
    {"topic": "iso", "tip": "Modify an ISO by creating a project: add or replace files, remove what you don't need, then rebuild."},
    {"topic": "iso", "tip": "Installing xorriso gives the most faithful ISO remastering (it keeps USB hybrid boot too)."},
    {"topic": "iso", "tip": "Downloads are checked against the official SHA-256 checksums whenever the distribution publishes them."},
    {"topic": "iso", "tip": "Alpine and Tiny Core are tiny - perfect for experimenting with ISO modifications."},
    # resources
    {"topic": "resources", "tip": "Share your best desktop: Resources -> Publish -> 'UI layout from system'."},
    {"topic": "resources", "tip": "Run 'hyperos serve --host 0.0.0.0' to host a registry for your friends or class - they can publish to it too."},
    {"topic": "resources", "tip": "Themes recolour a whole system in one click without touching your layout."},
    {"topic": "resources", "tip": "A system template resource shares everything: layout, commands, colours and source code."},
    # cli
    {"topic": "cli", "tip": "Everything in the app also works on the command line - run 'hyperos --help' to see all commands."},
    {"topic": "cli", "tip": "Automate builds: 'hyperos system build my-os && hyperos system run my-os'."},
    {"topic": "cli", "tip": "'hyperos shell' opens an interactive console with tab completion for all commands."},
    {"topic": "cli", "tip": "The Console page in the web app runs the same commands as the terminal."},
    # suggestions
    {"topic": "suggestions", "tip": "Have an idea? Add it on the Suggestions page and vote for the ideas you like most."},
    {"topic": "suggestions", "tip": "Click 'Send to GitHub' on a suggestion to open a pre-filled issue for the developers."},
]

TOPICS = sorted({t["topic"] for t in TIPS})


def all_tips(topic: Optional[str] = None) -> List[Dict[str, str]]:
    return [t for t in TIPS if topic is None or t["topic"] == topic]


def random_tip(topic: Optional[str] = None) -> str:
    pool = all_tips(topic) or TIPS
    return random.choice(pool)["tip"]
