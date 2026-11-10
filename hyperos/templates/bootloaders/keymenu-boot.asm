; @name: Key menu bootloader
; @description: A tiny boot menu: 1 loads the kernel, 2 reboots, 3 shows memory size.
; @difficulty: intermediate
;
; Loads 32 sectors after the boot sector to 0x1000:0000 (where HyperKernel
; and the kernel templates expect to be). Uses the simple CHS read that
; works for floppy images (18 sectors per track).
bits 16
org 0x7C00

KERNEL_SEG     equ 0x1000
KERNEL_SECTORS equ 32

start:
    xor ax, ax
    mov ds, ax
    mov ss, ax
    mov sp, 0x7C00
    mov [drive], dl
menu:
    mov si, msg_menu
    call print
.key:
    xor ax, ax
    int 0x16                ; wait for a key
    cmp al, '1'
    je boot_kernel
    cmp al, '2'
    je reboot
    cmp al, '3'
    je memory
    jmp .key

memory:
    int 0x12                ; ax = KB of conventional memory
    mov bx, 10
    xor cx, cx
.div:
    xor dx, dx
    div bx
    push dx
    inc cx
    test ax, ax
    jnz .div
.out:
    pop ax
    add al, '0'
    mov ah, 0x0E
    int 0x10
    loop .out
    mov si, msg_kb
    call print
    jmp menu

reboot:
    jmp 0xFFFF:0x0000

boot_kernel:
    mov ax, KERNEL_SEG
    mov es, ax
    xor bx, bx
    mov ah, 0x02            ; read sectors
    mov al, 17              ; sectors 2..18 of track 0
    mov ch, 0
    mov cl, 2
    mov dh, 0
    mov dl, [drive]
    int 0x13
    jc disk_error
    mov bx, 17 * 512        ; then the rest from head 1
    mov ah, 0x02
    mov al, KERNEL_SECTORS - 17
    mov cl, 1
    mov dh, 1
    mov dl, [drive]
    int 0x13
    jc disk_error
    mov dl, [drive]
    mov ax, KERNEL_SEG
    mov ds, ax
    jmp KERNEL_SEG:0x0000

disk_error:
    mov si, msg_err
    call print
    jmp menu

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

drive:    db 0
msg_menu: db 13, 10, '== Boot menu ==', 13, 10, ' 1) Boot kernel', 13, 10, ' 2) Reboot', 13, 10
          db ' 3) Memory size', 13, 10, '> ', 0
msg_kb:   db ' KB', 13, 10, 0
msg_err:  db 'Disk error', 13, 10, 0

times 510 - ($ - $$) db 0
dw 0xAA55
