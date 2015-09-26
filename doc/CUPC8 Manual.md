# CUPC/8 MANUAL

## Introduction

> The _**C**ompletely **U**seless and **P**ointless **C**omputer / **8**_ bit.

**CUPC/8** is a simple 8-bit microcomputer designed and built by myself *(David Kaplan)* for fun over the years 2014-2016. The design is pretty dirty and 'evolved' as I added features necessary to achive the goal of a fully working, custom-designed 8-bit machine that could connect to the Internet.
The full hardware and software stacks have been designed and coded from the ground up (with the exception of certain 3rd-party open source pieces of software whch I ported over to the CUPC/8 ISA). This document serves as a manual detailing all aspects of the computer for anyone that may, however unlikely, be interested in my work in the future.

The entire project is open-sourced under a Creative Commons Attribution-NonCommercial 4.0 International license (with the exception of 3rd-party software where other licenses may apply).

## System Overview
#### Central Processing Unit SoC
The **CUPC/8** microcomputer is made up of a Central Processing Unit (a simple SoC really) implemented in VHDL and running on an FPGA. The CPU has an 8-bit data bus and a 16-bit address bus and runs a custom Instruction Set Architecture (ISA). Coupled with the CPU is a Memory Management Unit (MMU) which is responsible for memory mapping external interfaces. The last component of the CPU SoC is some Serial Peripheral Interface (SPI) logic which is used to provide an interface with external peripherals. Other than a memory-mapped 8-bit output only register hardwired to LEDs on the PCB, peripherals can only connect to the microprocessor over the SPI bus.

#### Memory
As the CPU sports a 16-bit address bus, the maximum amount of RAM that can be addressed (without bank switching) is 64KB. This is provided by a external SRAM chip.
This RAM chip is loaded on poweron from an external ROM chip which provides the initial code to be executed by the CPU. This is necessary due to the fact that there is no code within the FPGA SoC itself and the CPU can therefore not know how to load any code directly from ROM over the SPI bus. The current memory board design has a microcontroller on board which is responsible for copying ROM into RAM on poweron. Furthermore this microcontroller can interface to another external computer and allows for RAM and ROM to be written over UART.

#### Display
Display is piped over the SPI bus. Theoretically any display that works over SPI can be used (provided that a driver is writted for it). In reality, **CUPC/8** neither has sufficient bandwidth over its SPI bus nor enough memory to drive large displays with many colours. The display chosen reflects these limitations.

#### Input
*[TODO]*

#### Software
The software stack consists of a monolithic kernel which provides drivers for the SPI peripherals and filesystem, handles interrupts, etc. It also provides a limited set of fixed-vector 'libc-like' functions and graphic routines that can be used by applications. There is no separation between kernel- and user-space (it's more of a convention) and any application has full access to the entire memory space at any time. Ideally applications would take care not to overwrite kernel regions but there is nothing stopping them from doing so.

In addition to drivers and system functions, the kernel provides a 'terminal' interface which accepts a number of commands. A limited subset of BASIC is provided which allows BASIC programs to be executed directly from the terminal (in a non-interactive fashion).

There is no compiler available for the CUPC/8 ISA. Development tools are cross-platform and consist of an assembler and a simulator which provides 1-to-1 simulation of the full computer (including display and input). The simulator can be executed natively or compiled to JavaScript (using emscripten) and run through a web browser.

## Central Processing Unit

#### Registers

The **CUPC/8** has two 8-bit General Purpose Reigsters (GPRs), **r0** and **r1**. These are available for use by arithmetic operations and *LOAD*/*STORE* operations.

A status register exists which provides the internal logic with flags that are set due to operations. The only flag currenty is the **Z** (*zero*) flag which is set during comparison operations (*EQ*/*GT*/*LT*) and allows the CPU to perform decisions based on the **Z** flag value (for example, *BZF* - which branches if the flag is not set).

Two internal 16-bit address registers are provided for program flow; the **pc** (program counter) and **sp** (stack pointer) registers. The **pc** register holds the address of the next instruction awaiting execution. The **sp** register points to the address of the next free chunk of the stack memory region. Neither of these two registers can be acted upon directly and are modified through program flow and stack operations only.

There are two special 8-bit registers, **pcl** and **pch** (the 'low' and 'high' program counter registers). These registers can be acted upon through the use of stack operations (i.e. *PUSH*/*POP*) only. The **pch** register is special in that upon receiving a value though a stack *POP* operation, the 8-bit values of the **pcl** and **pch** registers are copied into the **pc** register such that _**pc** := **pch**||**pcl**_ and program flow jumps immediately to the new **pc** address. This is used to return from functions (as there is currently no dedicated *RET* instruction).

#### Memory layout

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
The kernel is responsible for setting up the IVT to handle interrupts that may occur from external sources (such as peripherals). *[TODO]*

###### Stack Region
The stack is an 8-bit stack which can be accessed by *PUSH*/*POP* operations. The architecture does not support addressing off the stack pointer (there is no way to access something like _[**sp** + $10]_ for example) or block allocation of stack regions (there are no base/frame pointers). *Warning: Overflowing the stack is completely possible and the CPU will not care - so **don't do this!***

###### Program Region
This is where the code goes. The CPU will start executing from *$1000* and the **CUPC/8** kernel places a jump to the kernel initialization function vector at this address.

###### Input/Output Region
The MMU is responsible for mapping peripherals to the memory space. Currently this region is used for the General Purpose Output (GPO) pins (8-bit mapped to *$f000*) and the SPI bus (mapped at *$f1XX*).


#### Input/Output
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


#### Instruction Set
The **CUPC/8** instruction set contains of 38 8-bit instructions.
Each instruction consists of an 5-bit/6-bit operation code (*opcode*) followed by register bits and zero, one or two bytes as defined by the instruction *format*.

###### Register Format
Instructions of the **Register** format act on registers only and are 8-bit in length. The 5 most significant bits 7..3 denote the operation, bit 2 should always be cleared, bits 1 and 0 are registers Rb and Ra respectively (bit cleared = r0, bit set = r1).

	 -----------------------------
	[   ins   |  0  |  Rb  |  Ra  ]
	 -----------------------------
	   {7..3}   {2}    {1}   {0}

###### Immediate Format
Instructions of the **Immediate** format are used when operations are performed on immediate 8-bit values.

Mneumonic | Opcode | Format | Syntax | Operation
:--- | :--- | :--- | :--- | :---
NOP|80|R|NOP
MOVr|88|R|MOV Ra, Rb|Ra <= Rb
MOVi|8c|I|MOV Ra, #imm|Ra <= imm
PUSHr|90|R|PUSH Rb|[SP] <= Rb; SP <= SP + 1
PUSHi|94|I|PUSH #imm|[SP] <= imm; SP <= SP + 1
POP|98|R|POP Ra|Ra <= [SP]; SP <= SP - 1 *(; PC <= PCH\|\|PCL on Ra = PCH)*
LD|a0|M|LD Ra, $addr|Ra <= [addr]
LDind|a4|M|LD Ra, $addr+Rb|Ra <= [addr + Rb]
ST|a8|M|ST $addr, Rb|[addr] <= Rb
STind|ac|M|ST $addr+Ra, Rb|[addr + Ra] <= Rb
LDD|70|M|LDD Ra, $addr|Ra <= [[addr]]
LDDind|74|M|LDD Ra, $addr+Rb|Ra <= [[addr + Rb]]
STD|78|M|STD $addr, Rb|[[addr]] <= Rb
STDind|7c|M|STD $addr + Ra, Rb|[[addr + Ra]] <= Rb
B|b0|F|B $addr|PC <= addr
BZF|b8|F|BZF $addr|if ZF: PC <= addr
EQr|00|R|EQ Ra, Rb|ZF <= Ra == Rb
EQi|04|I|EQ Ra, #imm|ZF <= Ra == imm
GTr|08|R|GT Ra, Rb|ZF <= Ra > Rb
GTi|0c|I|GT Ra, #imm|ZF <= Ra > imm
LTr|10|R|LT Ra, Rb|ZF <= Ra < Rb
LTi|14|I|LR Ra, #imm|ZF <= Ra < imm
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
SUBi|6c|I|SUB Ra, #imm|Ra <= Ra - imm
SHLr|60|R|SHL Ra, Rb|Ra <= Ra << Rb
SHLi|64|I|SHL Ra, #imm|Ra <= Ra << imm
SHRr|68|R|SHR Ra, Rb|Ra <= Ra >> Rb
SHRi|6c|I|SHR Ra, #imm|Ra <= Ra >> imm
