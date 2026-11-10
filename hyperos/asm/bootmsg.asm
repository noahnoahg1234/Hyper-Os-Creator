; =====================================================================
;  HyperSplash - a stand-alone boot sector "mini OS" (Hyper OS Creator)
; ---------------------------------------------------------------------
;  Fills the screen with a colour and draws text records directly into
;  VGA text memory. Hyper OS Creator writes the records after the code,
;  so a custom splash/boot sector can be generated without NASM.
;
;  Record format:  dw screen_offset, db attribute, db 'text', 0
;  End marker:     dw 0xFFFF
; =====================================================================
bits 16
org 0x7C00

start:
    jmp short main
    nop
cfg_magic: db 'HYPM'            ; +3
cfg_bg:    db 0x17              ; +7  background attribute
cfg_flags: db 3                 ; +8  bit0 reboot on key, bit1 hide cursor
cfg_rec:   dw records           ; +9  address of the record table

main:
    cli
    xor ax, ax
    mov ds, ax
    mov ss, ax
    mov sp, 0x7C00
    sti
    cld
    mov ax, 0x0003
    int 0x10
    test byte [cfg_flags], 2
    jz .cursor_ok
    mov ah, 0x01
    mov cx, 0x2607
    int 0x10
.cursor_ok:
    mov ax, 0xB800
    mov es, ax
    xor di, di
    mov cx, 2000
    mov ah, [cfg_bg]
    mov al, ' '
    rep stosw
    mov si, [cfg_rec]
.next:
    lodsw
    cmp ax, 0xFFFF
    je .done
    mov di, ax
    lodsb
    mov ah, al
.ch:
    lodsb
    test al, al
    jz .next
    stosw
    jmp .ch
.done:
    test byte [cfg_flags], 1
    jz .halt
    xor ax, ax
    int 0x16
    jmp 0xFFFF:0x0000
.halt:
    hlt
    jmp .halt

records:
    dw 0xFFFF
    times 510 - ($ - $$) db 0
    dw 0xAA55
