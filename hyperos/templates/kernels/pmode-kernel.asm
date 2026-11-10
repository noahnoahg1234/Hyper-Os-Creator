; @name: 32-bit protected mode kernel
; @description: Switches the CPU to 32-bit protected mode and paints the screen. Loaded by HyperBoot.
; @difficulty: advanced
;
; HyperBoot loads us to linear address 0x10000. In 32-bit mode we use flat
; segments (base 0), so every absolute address must include KBASE.
bits 16
org 0

KBASE equ 0x10000

start:
    cli
    mov ax, cs
    mov ds, ax
    in al, 0x92             ; enable the A20 line (fast A20)
    or al, 2
    out 0x92, al
    lgdt [gdt_desc]
    mov eax, cr0
    or eax, 1               ; set the PE (protection enable) bit
    mov cr0, eax
    jmp dword 0x08:(KBASE + pm_entry)

bits 32
pm_entry:
    mov ax, 0x10
    mov ds, ax
    mov es, ax
    mov ss, ax
    mov esp, 0x90000

    ; paint the screen in 8 horizontal colour bands (3 rows each)
    mov edi, 0xB8000
    xor ecx, ecx
.paint:
    mov eax, ecx
    xor edx, edx
    mov ebx, 3 * 80
    div ebx                 ; eax = band number (cell index / 240)
    and eax, 7
    shl eax, 12             ; band number -> background colour bits
    or eax, 0x0F20          ; white on that colour, space character
    mov [edi + ecx * 2], ax
    inc ecx
    cmp ecx, 2000
    jb .paint

    ; write a message in the middle of the screen
    mov esi, KBASE + message
    mov edi, 0xB8000 + (12 * 80 + 22) * 2
.msg:
    lodsb
    test al, al
    jz .halt
    mov ah, 0x1F
    stosw
    jmp .msg
.halt:
    cli
    hlt
    jmp .halt

message: db ' Hello from 32-bit protected mode! ', 0

align 8
gdt:
    dq 0                                    ; null descriptor
    dq 0x00CF9A000000FFFF                   ; 0x08: code, base 0, 4 GB
    dq 0x00CF92000000FFFF                   ; 0x10: data, base 0, 4 GB
gdt_end:
gdt_desc:
    dw gdt_end - gdt - 1
    dd KBASE + gdt
