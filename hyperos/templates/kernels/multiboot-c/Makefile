CFLAGS = -m32 -ffreestanding -fno-pie -fno-stack-protector -O2 -Wall -Wextra

kernel.elf: boot.o kernel.o linker.ld
	ld -m elf_i386 -z noexecstack -T linker.ld -o $@ boot.o kernel.o

boot.o: boot.asm
	nasm -f elf32 boot.asm -o boot.o

kernel.o: kernel.c
	gcc $(CFLAGS) -c kernel.c -o kernel.o

run: kernel.elf
	qemu-system-i386 -kernel kernel.elf

clean:
	rm -f *.o kernel.elf
