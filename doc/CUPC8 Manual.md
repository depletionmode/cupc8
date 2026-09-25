# CUPC/8 MANUAL

## 1. Introduction

> The _**C**ompletely **U**seless and **P**ointless **C**omputer / **8**_ bit.

**CUPC/8** is a simple 8-bit microcomputer designed and built by myself *(David Kaplan)* for fun over the years 2014-2016. The design is pretty dirty and 'evolved' as I added features necessary to achive the goal of a fully working, custom-designed 8-bit machine that could connect to the Internet.
The full hardware and software stacks have been designed and coded from the ground up (with the exception of certain 3rd-party open source pieces of software whch I ported over to the CUPC/8 ISA). This document serves as a manual detailing all aspects of the computer for anyone that may, however unlikely, be interested in my work in the future.

The entire project is open-sourced under a Creative Commons Attribution-NonCommercial 4.0 International license (with the exception of 3rd-party software where other licenses may apply).

## 2. System Overview
#### 2.1. Central Processing Unit SoC
The **CUPC/8** microcomputer is made up of a Central Processing Unit (a simple SoC really) implemented in VHDL and running on an FPGA. The CPU has an 8-bit data bus and a 16-bit address bus and runs a custom Instruction Set Architecture (ISA). Coupled with the CPU is a Memory Management Unit (MMU) which is responsible for memory mapping external interfaces. The last component of the CPU SoC is some Serial Peripheral Interface (SPI) logic which is used to provide an interface with external peripherals. Other than a memory-mapped 8-bit output only register hardwired to LEDs on the PCB, peripherals can only connect to the microprocessor over the SPI bus.

#### 2.2. Memory
As the CPU sports a 16-bit address bus, the maximum amount of RAM that can be addressed (without bank switching) is 64KB. This is provided by a external SRAM chip.
This RAM chip is loaded on poweron from an external ROM chip which provides the initial code to be executed by the CPU. This is necessary due to the fact that there is no code within the FPGA SoC itself and the CPU can therefore not know how to load any code directly from ROM over the SPI bus. The current memory board design has a microcontroller on board which is responsible for copying ROM into RAM on poweron. Furthermore this microcontroller can interface to another external computer and allows for RAM and ROM to be written over UART.

#### 2.3. Display
Display is piped over the SPI bus. Theoretically any display that works over SPI can be used (provided that a driver is writted for it). In reality, **CUPC/8** neither has sufficient bandwidth over its SPI bus nor enough memory to drive large displays with many colours. The display chosen reflects these limitations.

The M1 machine's console is its graphics card, one of two (a machine has one or the other): the **HDMI card**, 80 x 30 text or 320 x 240 graphics in 256 colours on a monitor (`doc/hardware/gpu-protocol.md`), or the **e-ink card**, the same text and graphics on an e-paper panel on the card's cable, a 5.83" 648 x 480 panel (or a 7.5" 800 x 480), plus the panel's own resolution in 4 greys (`doc/hardware/eink-card.md`). On e-paper the text is black on white (each cell's brighter colour is the ink), the cursor does not blink, and the card refreshes the panel by itself: a line typed reaches the panel about half a second later, and continuous output updates it about once a second. The kernel asks the card which it is and drives either.

#### 2.4. Input
*[TODO]*

#### 2.5. Software Stack
The software stack consists of a monolithic kernel which provides drivers for the SPI peripherals and filesystem, handles interrupts, etc. It also provides a limited set of fixed-vector 'libc-like' functions and graphic routines that can be used by applications. There is no separation between kernel- and user-space (it's more of a convention) and any application has full access to the entire memory space at any time. Ideally applications would take care not to overwrite kernel regions but there is nothing stopping them from doing so.

In addition to drivers and system functions, the kernel provides a 'terminal' interface which accepts a number of commands. A limited subset of BASIC is provided which allows BASIC programs to be executed directly from the terminal (in a non-interactive fashion).

The BASIC is uBASIC with 8-bit numbers (arithmetic wraps at 256), line numbers 1-255, one-letter variables `a`-`z`, and a 256-byte program buffer (a line that does not fit is refused with `PROGRAM FULL`; a typed line is at most 78 characters). Statements: `let`, `print` (`,` prints a space, `;` nothing), `if ... then ... else`, `for ... to ... next`, `goto`, `gosub`/`return`, `rem`, `end`, and, because an 8-bit number cannot hold an address, `poke hi, lo, value` and `peek hi, lo, var` (the address is hi*256+lo; `poke 240, 0, n` sets the LEDs at $f000). Operators: `+ - * / % & |`, `< > =`, parentheses. Dividing by 0 gives 0.

Terminal commands besides BASIC lines: `help`, `new` (clear the program), `run`, `clr` (clear the screen), `refresh` (on the e-ink card, a clean full refresh of the panel, which clears the faint ghosts partial refreshes leave; on HDMI it does nothing) and `net`, for the Wi-Fi card:

- `net join SSID PASSWORD` joins that network, keeps the credentials on the card (it joins them again at power-up) and prints the address it was given.
- `net get HOST [PORT]` sends `GET / HTTP/1.0` (with a `Host:` header) to HOST, port 80 unless given, and prints the reply until the server closes the connection. HOST is a name, looked up by the kernel's own DNS client, or a dotted address used as it is. A refused connection prints `connect failed`.
- `net lookup NAME` prints the address the DNS client finds for NAME. It asks the DNS server `net config` names (or the one DHCP gave), waits about a second, asks once more, and takes the first A record of the answer. It says `name not found` (the server has no such name), `no address for that name` (the name exists, with no IPv4 address), `DNS server not answering`, `DNS server error`, `bad answer from the DNS server` or `no DNS server`.
- `net ping HOST [COUNT]` sends COUNT (4 unless given, up to 255) ICMP echo requests to HOST (a name or an address), one after the other, and prints each reply's round-trip time in milliseconds (`seq 1 time 3 ms`), or `seq 2 timeout` when none comes within about a second, then `4 sent, 3 received, 2-5 ms` (the shortest and longest).
- `net config` shows the card's settings: `mode dhcp` or `mode static` with its address, mask and gateway; the DNS server (`from dhcp`, or an address) and its port; whether they are saved on the card. `net config dns IP [PORT]` sets the DNS server (port 53 unless given), `net config ip IP MASK GW` a static address, `net config dhcp` goes back to DHCP, and `net config save` keeps the settings on the card, applied at power-up (until then they last until the card is powered off).
- `net` on its own shows whether the link is up, and the address.

The times come from a clock the kernel runs only while it waits for the network: timer 1 counting instructions, so a millisecond is about a thousand instructions and the times are approximate.

`net` refuses to start the radio on a USB source under 3 A (see the power budget).

Files, on the storage card's microSD card (`doc/hardware/storage-card.md`). A card formatted on a PC works as it is (FAT12, FAT16 or FAT32). Names are 8.3 (`PROG.BAS`), in any case, with or without the quotes:

- `save "NAME"` writes the program as text, one line per program line, each ending in CR LF, so a PC can read and edit it. It replaces a file of that name.
- `load "NAME"` clears the program (`new`), then takes the file's lines as if they were typed: a line that does not start with a line number (a blank line, say) is skipped, and a line longer than 78 characters is cut. A line that does not fit stops the load with `PROGRAM FULL`.
- `dir` lists every file with its size in bytes.
- `del "NAME"` deletes a file.

They print `SAVED` or `LOADED` when done, or what went wrong: `no SD card`, `no storage card` (none fitted), `file not found`, `card full`, `write protected`, `bad file name` (not 8.3), `no file system on the card` (not formatted) or `card error`. On a USB source under 3 A, `save` and `del` print `USB power under 3A: SD writes off` and leave the card as it was; `load` and `dir` still work.

There is no compiler available for the CUPC/8 ISA. Development tools are cross-platform and consist of an assembler and a simulator which provides 1-to-1 simulation of the full computer (including display and input). The simulator can be executed natively or compiled to JavaScript (using emscripten) and run through a web browser.

## 3. Central Processing Unit

#### 3.1. Registers

The **CUPC/8** has two 8-bit General Purpose Reigsters (GPRs), **r0** and **r1**. These are available for use by arithmetic operations and *LOAD*/*STORE* operations.

A status register **f** exists which provides the internal logic with flags that are set due to operations. Bit 0 is the **Z** (*zero*) flag, set during comparison operations (*EQ*/*GT*/*LT*) and used by *BZF*. Bit 1 is the **I** (*interrupt enable*) flag. *CLI* clears **I**, *STI* sets it. **f** can be restored from the stack with *POP f* (the same *POP* opcode used for **r0**/**r1**/**pcl**/**pch**).

Two internal 16-bit address registers are provided for program flow; the **pc** (program counter) and **sp** (stack pointer) registers. The **pc** register holds the address of the next instruction awaiting execution. The **sp** register points to the address of the next free chunk of the stack memory region. Neither of these two registers can be acted upon directly and are modified through program flow and stack operations only.

There are two special 8-bit registers, **pcl** and **pch** (the 'low' and 'high' program counter registers). These registers can be acted upon through the use of stack operations (i.e. *PUSH*/*POP*) only. The **pch** register is special in that upon receiving a value though a stack *POP* operation, the 8-bit values of the **pcl** and **pch** registers are copied into the **pc** register such that _**pc** := **pch**||**pcl**_ and program flow jumps immediately to the new **pc** address. This is used to return from functions and from interrupts (there is no dedicated *RET* or *IRET* instruction).

#### 3.2. Memory layout

 Region | Start address | End Address 
 :--- | :---: | :---:
 Soft Reset Vector | $0000 | $0001
 *Reserved* | $0002 | $000f
 Interrupt Vector Table | $0010 | $00ff
 Stack | $0100 | $0fff
 Program | $1000 | $efff
 I/O | $f000 | $ffff

###### Soft Reset Vector (SRV) Region
On boot, the CPU will start executing from the Hard Reset Vector, *$f000* (i.e. _**pc** := $1000_) and **sp** will be reset to the bottom of the stack (_**sp** := $0100_). A configurable SRV can be set at *$0000*. Even if unused this vector should be set to *$1000* as soon as possible after boot.

###### Interrupt Vector Table (IVT) Region
Four 16-bit little-endian vectors sit at the bottom of the reserved IVT. The rest of *$0018*-*$00ff* is reserved.

IRQ | Vector | Source
:--- | :---: | :---
0 | *$0010* | Keyboard character ready
1 | *$0012* | Timer 0 expired
2 | *$0014* | Timer 1 expired
3 | *$0016* | SPI transaction complete

After an instruction finishes, if **I** is set and a pending unmasked source exists, the CPU takes the lowest numbered IRQ:

1. Push **pch**, then **pcl** (same order as a call).
2. Push **f** (bit 0 = **Z**, bit 1 = **I**).
3. Clear **I**.
4. Load **pc** from the vector.

Return is the same as a call return plus one extra pop for the flags:

	pop f
	pop pcl
	pop pch

*POP f* restores **I**, so an IRQ still pending is taken right after it, inside the epilogue and before the return. This nests correctly: the new handler pushes the address of the *POP pcl* (three more stack bytes), and its own return lands back in the epilogue, which then completes. Interrupts can therefore nest one level per pending source; leave room on the stack for it.

Sources are latched. *$f200* is the pending register (write-1-to-clear). *$f201* is the mask (1 = enabled). Reset leaves **I** and the mask clear; the kernel plants the vectors and *STI*s when it is ready.

*WAI* stops fetching until an IRQ is accepted. If **I** is clear it is a *NOP*. *HALT* still means stop forever.

###### Stack Region
The stack is an 8-bit stack which can be accessed by *PUSH*/*POP* operations. The architecture does not support addressing off the stack pointer (there is no way to access something like _[**sp** + $10]_ for example) or block allocation of stack regions (there are no base/frame pointers). *Warning: Overflowing the stack is completely possible and the CPU will not care - so **don't do this!***

###### Program Region
This is where the code goes. The CPU will start executing from *$1000* and the **CUPC/8** kernel places a jump to the kernel initialization function vector at this address.

###### Input/Output Region
The MMU is responsible for mapping peripherals to the memory space. Currently this region is used for the General Purpose Output (GPO) pins (8-bit mapped to *$f000*), the SPI bus (mapped at *$f1XX*), and the interrupt controller (*$f200*, *$f201*).


#### 3.3. Input/Output
###### General Purpose Output
GPOs are mapped to *$f000*, a simple 8-bit *STORE* operation to this address will set the pin states accordinly.

###### Serial Peripheral Interface Bus
The CPU can act as an SPI master for up to 4 SPI slaves. Each SPI controller is mapped to *$f1X0*-*$f1Xf*, where *X* denotes the device number (0-3).

The low nybble of the address denotes the SPI operation to be performed via interactions with the following registers:

Address | Operation | Descrption
:--- | :--- | :---
$f1X0 | STORE | Write byte to TX buffer
$f1X1 | LOAD | Read byte from RX buffer
$f1X2 | STORE | Perform transaction
$f1X3 | LOAD | Get SPI status
$f1Xf | STORE | Configure SPI

SPI master configuration is done via a *STORE* to the configuration register, *$f1Xf*. The register configuration bits are as follows:

```
00000 0 0 0
|   | | | |
 ---  | |  ----> continous
  |   |  ------> cpol
  |    --------> spha
   ------------> clk_div
```

The *continous*, *cpol* and *cpha* bits are self-explanatory to anyone familiar with SPI. 	*clk_div* allows the user to select the SPI bus speed as a factor of the system clock speed. The 5-bit value allows for a division of up to 31 such that a *clk_div* value of 1 will run the SPI bus at the same speed as the system clock.
   

After configuration of the SPI device, a typical transaction might look as follows:

	.transact:
		mov r0, #255
		st $f100, r0	; write 0xff to TX buffer
		mov r0, #1
		st $f102, r0	; perform transaction by writing 1 to $f10X2
	.loop:
		eq r0, #0
		bzf .transaction_done
		ld r0, $f103	; see if SPI is busy
		b .loop
	.transaction_done:
		ld r0, $f101	; read RX buffer

###### Interrupts
Address | Operation | Description
:--- | :--- | :---
*$f200* | LOAD | Pending bits (bit *n* = IRQ *n*)
*$f200* | STORE | Write-1-to-clear pending bits
*$f201* | LOAD/STORE | Mask (1 = enabled)

*TMR0* / *TMR1* load an 8-bit countdown (immediate or register). The value decrements after every retired instruction, the *TMR* instruction itself included (so *TMR0 #1* fires as it retires, and *TMR0 #3* as the second instruction after it retires). While parked in *WAI* it keeps decrementing, once every 3 CPU clocks. Crossing zero latches the matching timer IRQ. Writing 0 stops the timer without firing.

#### 3.4. Instruction Set Architecture
The **CUPC/8** instruction set contains of 38 8-bit instructions plus a handful of later additions (*HALT*, *CLI*, *STI*, *WAI*, *TMR0*, *TMR1*, and *POP f*).
Each instruction consists of an 5-bit/6-bit operation code (*opcode*) followed by register bits and zero, one or two bytes as defined by the instruction *format*.

###### Register Format
Instructions of the **register** format act on registers only and are 8-bit in length. The 5 most significant bits 7..3 denote the operation, bit 2 should always be cleared, bits 1 and 0 are registers Rb and Ra respectively (bit cleared = **r0**, bit set = **r1**).

The CPU performs only a single *fetch* operation for instructions of this formations are the fastest to execute.

	 -----------------------------
	[   ins   |  0  |  Rb  |  Ra  ]
	 -----------------------------
	   {7..3}   {2}    {1}   {0}

###### Immediate Format
Instructions of the **immediate** format are used when operations are performed on immediate 8-bit values. The most significant 5 bits denote the operation. Bit 10 must always be set. Bit 9 is ignored. Bit 8 denotes register Ra (bit cleared = **r0**, bit set = **r1**). The final 8 bit value is the immediate value.

The CPU performs two *fetch* operation for instructions of this format.

	 --------------------------------    -------
	[    ins    |   1   |  ?  |  Ra  ]  [  IMM  ]
	 --------------------------------    -------
	   {15..11}   {10}    {9}    {8}      {7..0}

###### Memory Format
Instructions of the **memory** format are used to store and load values via the MMU. The 5 most significant bits denote the operation. The next bit is ignored. Bits 17 and 16 are the Rb and Ra registers respectively. The final 16 bits denote the address of the memory operation.

The CPU performs three *fetch* operation for instructions of this format. These, together with the **flow** format instructions, are the slowest instructions to execute.

	 -------------------------------------    ----------
	[    ins    |   ?   |   Rb   |   Ra   ]  [   ADDR   ]
	 -------------------------------------    ----------
	   {23..19}   {18}     {17}     {16}       {15..0}

###### Flow Format
Instructions of the **flow** format are used to modify program execution flow (such as by modification of the program counter). The most significant 5 bits denote the operation. The next 3 bits are ignored. The final 16 bit value holds the target address for the program flow change operation.

The CPU performs three *fetch* operation for instructions of this format. These, together with the **memory** format instructions, are the slowest to execute.

	 -----------------------    ----------
	[    ins    |     ?     ]  [   ADDR   ]
	 -----------------------    ----------
	   {23..19}   {18..16}        {15..0}

###### Instructions
Mneumonic | Opcode | Format | Syntax | Operation
:--- | :--- | :--- | :--- | :---
NOP|80|R|NOP
MOVr|88|R|MOV Ra, Rb|Ra <= Rb
MOVi|8c|I|MOV Ra, #imm|Ra <= imm
PUSHr|90|R|PUSH Rb|[SP] <= Rb; SP <= SP + 1
PUSHi|94|I|PUSH #imm|[SP] <= imm; SP <= SP + 1
POP|98|R|POP Ra|Ra <= [SP]; SP <= SP - 1 *(; PC <= PCH\|\|PCL on Ra = PCH; f <= [SP] on Ra = f)*
LD|a0|M|LD Ra, $addr|Ra <= [addr]
LDind|a4|M|LD Ra, $addr+Rb|Ra <= [addr + Rb]
ST|a8|M|ST $addr, Rb|[addr] <= Rb
STind|ac|M|ST $addr+Ra, Rb|[addr + Ra] <= Rb
LDD|70|M|LDD Ra, $addr|Ra <= [[addr]]
LDDind|74|M|LDD Ra, $addr+Rb|Ra <= [[addr] + Rb] (the pointer at addr, plus Rb: 16-bit sum)
STD|78|M|STD $addr, Rb|[[addr]] <= Rb
STDind|7c|M|STD $addr + Ra, Rb|[[addr] + Ra] <= Rb (the pointer at addr, plus Ra: 16-bit sum)
B|b0|F|B $addr|PC <= addr
BZF|b8|F|BZF $addr|if ZF: PC <= addr
EQr|00|R|EQ Ra, Rb|ZF <= Ra == Rb
EQi|04|I|EQ Ra, #imm|ZF <= Ra == imm
GTr|08|R|GT Ra, Rb|ZF <= Ra > Rb
GTi|0c|I|GT Ra, #imm|ZF <= Ra > imm
LTr|10|R|LT Ra, Rb|ZF <= Ra < Rb
LTi|14|I|LT Ra, #imm|ZF <= Ra < imm
ANDr|18|R|AND Ra, Rb|Ra <= Ra & Rb
ANDi|1c|I|AND Ra, #imm|Ra <= Ra & imm
ORr|20|R|OR Ra, Rb|Ra <= Ra \| Rb
ORi|24|I|OR Ra, #imm|Ra <= Ra \| imm
XORr|30|R|XOR Ra, Rb|Ra <= Ra ^ Rb
XORi|34|I|XOR Ra, #imm|Ra <= Ra ^ imm
NORr|38|R|NOR Ra, Rb|Ra <= ~(Ra \| Rb)
NORi|3c|I|NOR Ra, #imm|Ra <= ~(Ra \| imm)
ADDr|40|R|ADD Ra, Rb|Ra <= Ra + Rb
ADDi|44|I|ADD Ra, #imm|Ra <= Ra + imm
SUBr|48|R|SUB Ra, Rb|Ra <= Ra - Rb
SUBi|4c|I|SUB Ra, #imm|Ra <= Ra - imm
SHLr|60|R|SHL Ra, Rb|Ra <= Ra << Rb
SHLi|64|I|SHL Ra, #imm|Ra <= Ra << imm
SHRr|68|R|SHR Ra, Rb|Ra <= Ra >> Rb
SHRi|6c|I|SHR Ra, #imm|Ra <= Ra >> imm
CLI|c0|R|CLI|I <= 0
STI|c8|R|STI|I <= 1
WAI|f0|R|WAI|wait until an IRQ is accepted (NOP if I = 0)
HALT|f8|R|HALT|stop
TMR0|e0|R/I|TMR0 Rb / TMR0 #imm|timer0 <= value
TMR1|e8|R/I|TMR1 Rb / TMR1 #imm|timer1 <= value

The immediate form of an instruction is always its register opcode plus 4 (bit 2 set).

###### Special register operands
*PUSH* and *POP* also take **pch**, **pcl** and **f**. These use the low three bits of the opcode byte, which would otherwise hold bit 2 and the register bits:

Instruction | Byte | Operation
:--- | :--- | :---
PUSH pch|96|[SP] <= high byte of (address of this instruction + 5); SP <= SP + 1
PUSH pcl|97|[SP] <= low byte of (address of this instruction + 4); SP <= SP + 1
POP pcl|9f|SP <= SP - 1; pcl <= [SP]
POP pch|9e|SP <= SP - 1; PC <= [SP]\|\|pcl (the jump that returns)
POP f|9c|SP <= SP - 1; f <= [SP] (bit 0 **Z**, bit 1 **I**)

A call is `PUSH pch` / `PUSH pcl` / `B target`: both pushes name the address just after the *B*. A return is `POP pcl` / `POP pch`. *PUSH f* does not exist: its byte, 94, is *PUSHi*.
