/* @name: Multiboot C kernel
 * @description: A 32-bit kernel in C that GRUB, Limine or "qemu -kernel" can boot.
 * @difficulty: advanced
 *
 * Build:  make            (needs gcc with -m32 support and ld)
 * Run:    qemu-system-i386 -kernel kernel.elf
 */
#include <stdint.h>
#include <stddef.h>

static volatile uint16_t *const VGA = (uint16_t *)0xB8000;
static size_t row, col;
static uint8_t colour = 0x1F;

static void put(char c) {
    if (c == '\n') { col = 0; row++; return; }
    VGA[row * 80 + col] = (uint16_t)colour << 8 | (uint8_t)c;
    if (++col == 80) { col = 0; row++; }
    if (row == 25) row = 0;
}

static void print(const char *s) { while (*s) put(*s++); }

void kernel_main(void) {
    for (size_t i = 0; i < 80 * 25; i++) VGA[i] = (uint16_t)colour << 8 | ' ';
    print("Hello from a C kernel built with Hyper OS Creator!\n");
    colour = 0x1E;
    print("Edit kernel.c in the code editor and make something amazing.\n");
    for (;;) __asm__ volatile ("hlt");
}
