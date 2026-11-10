; =====================================================================
;  HyperKernel - a tiny 16-bit real-mode kernel for Hyper OS Creator
; ---------------------------------------------------------------------
;  Loaded by HyperBoot at 0x1000:0000. On start it draws the desktop
;  that was designed in the UI editor, waits for a key and then starts
;  a small command shell.
;
;  Everything that makes your system unique (name, version, prompt,
;  message of the day, desktop layout and custom commands) lives in a
;  data "blob" that Hyper OS Creator appends right after this kernel.
;
;  Blob layout (all offsets relative to the start of the blob):
;     db 'HYPR'
;     dw name, version, prompt, motd, ui, commands   ; offsets
;     db shell_attr
;  UI element list (terminated by type 0):
;     1 fill : db 1, attr
;     2 box  : db 2, x, y, w, h, attr, tl, tr, bl, br, horiz, vert, 'title', 0
;     3 text : db 3, x, y, attr, 'text', 0
;  Command table:  db count, then count x ('name', 0, 'output', 0)
;
;  Build manually:  nasm -f bin hyperkernel.asm -o hyperkernel.bin
; =====================================================================
bits 16
org 0

start:
    jmp short kmain
    nop
    db 'HYPK'                   ; +3 magic
blob_ptr: dw blob               ; +7 where the blob starts

kmain:
    mov ax, cs
    mov ds, ax
    mov es, ax
    cli
    mov ss, ax
    mov sp, 0xFFFE
    sti
    cld
    mov [boot_drive], dl

    cmp dword [blob], 'HYPR'
    je .blob_ok
    mov si, msg_noblob
    call print
    jmp halt
.blob_ok:
    mov si, blob + 4            ; turn the offsets into pointers
    mov di, p_name
    mov cx, 6
.fix:
    lodsw
    add ax, blob
    stosw
    loop .fix
    lodsb
    mov [shell_attr], al

    call draw_desktop
    xor ax, ax
    int 0x16
    jmp shell

; =====================================================================
;  Desktop renderer
; =====================================================================
draw_desktop:
    mov ax, 0x0003
    int 0x10
    mov ah, 0x01                ; hide cursor while on the desktop
    mov cx, 0x2607
    int 0x10
    push es
    mov ax, 0xB800
    mov es, ax
    mov si, [p_ui]
.next:
    lodsb
    cmp al, 1
    je .fill
    cmp al, 2
    je .box
    cmp al, 3
    je .text
    pop es
    ret

.fill:
    lodsb
    mov ah, al
    mov al, ' '
    xor di, di
    mov cx, 2000
    rep stosw
    jmp .next

.text:
    lodsb
    mov [bx_x], al
    lodsb
    mov [bx_y], al
    lodsb
    mov ah, al
    call cell_addr
.t:
    lodsb
    test al, al
    jz .next
    stosw
    jmp .t

.box:
    mov di, bx_x                ; copy x,y,w,h,attr + 6 border chars
    mov cx, 11
.copy:
    lodsb
    mov [di], al
    inc di
    loop .copy
    push si                     ; si -> title
    mov byte [row], 0
.row_loop:
    mov al, [row]
    cmp al, [bx_h]
    jae .rows_done
    mov al, [bx_y]
    add al, [row]
    mov [cur_y], al
    mov byte [col], 0
.col_loop:
    mov al, [col]
    cmp al, [bx_w]
    jae .col_done
    call box_char               ; al = char for (row, col)
    mov ah, [bx_attr]
    push ax
    mov al, [bx_x]
    add al, [col]
    mov ah, [cur_y]
    call cell_addr_xy
    pop ax
    stosw
    inc byte [col]
    jmp .col_loop
.col_done:
    inc byte [row]
    jmp .row_loop
.rows_done:
    pop si                      ; title at (x+2, y)
    mov al, [bx_x]
    add al, 2
    mov ah, [bx_y]
    call cell_addr_xy
    mov ah, [bx_attr]
.title:
    lodsb
    test al, al
    jz .next
    stosw
    jmp .title

; box_char: border character for [row],[col] of the current box
box_char:
    mov bl, [bx_w]
    dec bl
    mov bh, [bx_h]
    dec bh
    mov al, [row]
    mov ah, [col]
    test al, al
    jnz .not_top
    mov al, [b_tl]
    test ah, ah
    jz .r
    mov al, [b_tr]
    cmp ah, bl
    je .r
    mov al, [b_hz]
    ret
.not_top:
    cmp al, bh
    jne .middle
    mov al, [b_bl]
    test ah, ah
    jz .r
    mov al, [b_br]
    cmp ah, bl
    je .r
    mov al, [b_hz]
    ret
.middle:
    mov al, [b_vt]
    test ah, ah
    jz .r
    cmp ah, bl
    je .r
    mov al, ' '
.r:
    ret

; cell_addr: DI = offset of ([bx_x], [bx_y]) in VGA memory
cell_addr:
    push ax
    mov al, [bx_x]
    mov ah, [bx_y]
    call cell_addr_xy
    pop ax
    ret

; cell_addr_xy: AL = x, AH = y  ->  DI = (y * 80 + x) * 2
cell_addr_xy:
    push ax
    push dx
    xor dx, dx
    mov dl, al
    mov al, ah
    xor ah, ah
    push dx
    mov dx, 80
    mul dx
    pop dx
    add ax, dx
    shl ax, 1
    mov di, ax
    pop dx
    pop ax
    ret

; =====================================================================
;  Shell
; =====================================================================
shell:
    call clear_screen
    mov si, [p_name]
    call print
    mov si, msg_space
    call print
    mov si, [p_ver]
    call print
    call newline
    mov si, [p_motd]
    call print
    call newline
.loop:
    call newline_if_needed
    mov si, [p_prompt]
    call print
    mov di, line
    call readline
    call newline
    mov si, line
    cmp byte [si], 0
    je .loop

    mov di, cmd_help
    call strcmp
    je do_help
    mov di, cmd_clear
    call strcmp
    je do_clear
    mov di, cmd_ver
    call strcmp
    je do_ver
    mov di, cmd_desktop
    call strcmp
    je do_desktop
    mov di, cmd_reboot
    call strcmp
    je do_reboot
    mov di, cmd_halt
    call strcmp
    je do_halt
    mov di, cmd_mem
    call strcmp
    je do_mem
    mov di, cmd_time
    call strcmp
    je do_time
    mov si, line                ; "echo <text>"
    mov di, cmd_echo
    mov cx, 5
    repe cmpsb
    je do_echo

    ; ---- custom commands from the blob
    mov si, [p_cmds]
    lodsb
    xor ch, ch
    mov cl, al
    jcxz .unknown
.cmd_loop:
    mov di, si                  ; di -> name
    push si
    mov si, line
    call strcmp
    pop si
    call skipz                  ; si -> output
    je .found
    call skipz                  ; si -> next name
    loop .cmd_loop
.unknown:
    mov si, msg_unknown
    call print
    mov si, line
    call print
    call newline
    jmp shell.loop
.found:
    call print
    call newline
    jmp shell.loop

do_help:
    mov si, msg_help
    call print
    mov si, [p_cmds]
    lodsb
    xor ch, ch
    mov cl, al
    jcxz .done
    push si
    mov si, msg_custom
    call print
    pop si
.l:
    push si
    mov si, msg_indent
    call print
    pop si
    call print
    call skipz
    call skipz
    loop .l
.done:
    call newline
    jmp shell.loop

do_clear:
    call clear_screen
    jmp shell.loop

do_ver:
    mov si, [p_name]
    call print
    mov si, msg_space
    call print
    mov si, [p_ver]
    call print
    mov si, msg_built
    call print
    jmp shell.loop

do_desktop:
    call draw_desktop
    xor ax, ax
    int 0x16
    jmp shell

do_reboot:
    jmp 0xFFFF:0x0000

do_halt:
    mov si, msg_halt
    call print
halt:
    cli
    hlt
    jmp halt

do_echo:
    call print                  ; si already points after "echo "
    call newline
    jmp shell.loop

do_mem:
    int 0x12                    ; AX = conventional memory in KB
    call print_dec
    mov si, msg_kb
    call print
    jmp shell.loop

do_time:
    mov ah, 0x02                ; RTC time, BCD in CH:CL:DH
    int 0x1A
    mov al, ch
    call print_bcd
    mov al, ':'
    call putch
    mov al, cl
    call print_bcd
    mov al, ':'
    call putch
    mov al, dh
    call print_bcd
    call newline
    jmp shell.loop

; =====================================================================
;  Helpers
; =====================================================================
clear_screen:
    pusha
    mov ax, 0x0003
    int 0x10
    push es                     ; paint the shell colour
    mov ax, 0xB800
    mov es, ax
    xor di, di
    mov cx, 2000
    mov ah, [shell_attr]
    mov al, ' '
    rep stosw
    pop es
    popa
    ret

newline_if_needed:
    pusha
    mov ah, 0x03
    xor bh, bh
    int 0x10
    test dl, dl
    jz .ok
    call newline
.ok:
    popa
    ret

; readline: read a line into DI (max 63 chars)
readline:
    pusha
    xor cx, cx
.k:
    xor ax, ax
    int 0x16
    cmp al, 13
    je .done
    cmp al, 8
    je .bs
    cmp al, 32
    jb .k
    cmp cx, 63
    jae .k
    stosb
    inc cx
    call putch
    jmp .k
.bs:
    jcxz .k
    dec di
    dec cx
    mov al, 8
    call putch
    mov al, ' '
    call putch
    mov al, 8
    call putch
    jmp .k
.done:
    mov byte [di], 0
    popa
    ret

; strcmp: compare zero terminated strings DS:SI and ES:DI, ZF=1 if equal
strcmp:
    pusha
.c:
    mov al, [si]
    cmp al, [di]
    jne .out
    test al, al
    jz .out
    inc si
    inc di
    jmp .c
.out:
    popa
    ret

; skipz: advance SI past the next NUL (flags preserved)
skipz:
    pushf
.s:
    lodsb
    test al, al
    jnz .s
    popf
    ret

print:
    pusha
.p:
    lodsb
    test al, al
    jz .e
    call putch
    jmp .p
.e:
    popa
    ret

putch:
    pusha
    mov ah, 0x0E
    xor bx, bx
    int 0x10
    popa
    ret

newline:
    push si
    mov si, msg_crlf
    call print
    pop si
    ret

print_dec:                      ; AX = unsigned number
    pusha
    xor cx, cx
    mov bx, 10
.d:
    xor dx, dx
    div bx
    push dx
    inc cx
    test ax, ax
    jnz .d
.o:
    pop ax
    add al, '0'
    call putch
    loop .o
    popa
    ret

print_bcd:                      ; AL = BCD byte
    pusha
    mov ah, al
    shr al, 4
    add al, '0'
    call putch
    mov al, ah
    and al, 0x0F
    add al, '0'
    call putch
    popa
    ret

; =====================================================================
;  Data
; =====================================================================
cmd_help:    db 'help', 0
cmd_clear:   db 'clear', 0
cmd_ver:     db 'ver', 0
cmd_desktop: db 'desktop', 0
cmd_reboot:  db 'reboot', 0
cmd_halt:    db 'halt', 0
cmd_mem:     db 'mem', 0
cmd_time:    db 'time', 0
cmd_echo:    db 'echo '

msg_noblob:  db 'HyperKernel: missing system blob!', 0
msg_unknown: db 'Unknown command: ', 0
msg_help:    db 'Built-in commands:', 13, 10
             db '  help  clear  ver  desktop  echo <text>  mem  time  reboot  halt', 13, 10, 0
msg_custom:  db 'Custom commands:', 13, 10, 0
msg_indent:  db '  ', 0
msg_space:   db ' ', 0
msg_built:   db ' (built with Hyper OS Creator)', 13, 10, 0
msg_halt:    db 'System halted. It is now safe to turn off your computer.', 0
msg_kb:      db ' KB conventional memory', 13, 10, 0
msg_crlf:    db 13, 10, 0

boot_drive:  db 0
shell_attr:  db 0x07
p_name:      dw 0
p_ver:       dw 0
p_prompt:    dw 0
p_motd:      dw 0
p_ui:        dw 0
p_cmds:      dw 0
bx_x:        db 0
bx_y:        db 0
bx_w:        db 0
bx_h:        db 0
bx_attr:     db 0
b_tl:        db 0
b_tr:        db 0
b_bl:        db 0
b_br:        db 0
b_hz:        db 0
b_vt:        db 0
row:         db 0
col:         db 0
cur_y:       db 0
line:        times 64 db 0

align 16
blob:                           ; <- Hyper OS Creator appends the blob here
