; @name: Hello boot sector
; @description: The smallest possible bootloader: prints a message and stops. Great for learning.
; @difficulty: beginner
;
; The BIOS loads the first 512 bytes of the disk to address 0x7C00 and
; jumps there. The last two bytes must be 0x55, 0xAA.
bits 16
org 0x7C00

start:
    xor ax, ax
    mov ds, ax              ; data segment = 0
    mov si, message
    mov ah, 0x0E            ; BIOS teletype output
.next:
    lodsb                   ; al = [si], si++
    test al, al
    jz .done
    int 0x10                ; print character in al
    jmp .next
.done:
    cli
    hlt                     ; stop the CPU
    jmp .done

message: db 'Hello from my own bootloader!', 13, 10, 0

times 510 - ($ - $$) db 0  ; pad to 510 bytes
dw 0xAA55                   ; boot signature
