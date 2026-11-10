; @name: Hello kernel (real mode)
; @description: A minimal 16-bit kernel loaded by HyperBoot: prints text and echoes what you type.
; @difficulty: beginner
;
; HyperBoot loads kernels to segment 0x1000 offset 0, so we use org 0
; and set every segment register to CS.
bits 16
org 0

start:
    mov ax, cs
    mov ds, ax
    mov es, ax
    mov ss, ax
    mov sp, 0xFFFE

    mov si, banner
    call print
.loop:
    xor ax, ax
    int 0x16                ; read key -> al
    cmp al, 13
    jne .echo
    mov si, newline
    call print
    jmp .loop
.echo:
    mov ah, 0x0E
    int 0x10
    jmp .loop

print:
    mov ah, 0x0E
.p:
    lodsb
    test al, al
    jz .e
    int 0x10
    jmp .p
.e:
    ret

banner:  db 'My kernel is running!', 13, 10, 'Type something: ', 0
newline: db 13, 10, 0
