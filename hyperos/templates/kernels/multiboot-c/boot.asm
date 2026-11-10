; Multiboot header + entry point for the C kernel
MB_MAGIC equ 0x1BADB002
MB_FLAGS equ 0x00000003          ; align modules, provide memory map

section .multiboot
align 4
    dd MB_MAGIC
    dd MB_FLAGS
    dd -(MB_MAGIC + MB_FLAGS)

section .bss
align 16
stack_bottom:
    resb 16384
stack_top:

section .text
global _start
extern kernel_main
_start:
    mov esp, stack_top
    call kernel_main
.hang:
    cli
    hlt
    jmp .hang
