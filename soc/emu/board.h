// The main board of the whole-machine emulator: the Verilated CPU + chipset
// netlist (machine_core.vhd), the SRAM, and the SST39VF040 ROM chip
// (fw/test/sysmodels.c, the same model as the sysctl tests). Shared by the
// Node addon test/emu/machine.mjs uses (soc/emu/core.cpp) and the native
// whole-machine emulator (emu/machine/).
//
// inputs:  bit 0 SPI MISO, 1-6 SLOT_nIRQ[5:0], 7 BR_SCK, 8 BR_MOSI, 9 BR_nCS,
//          10 PWR_HI, 11 CPU_CDONE, 12 nPOR
// outputs: bit 0 SPI SCK, 1 MOSI, 2-8 SPI_nCS[6:0], 9 BR_MISO, 10 CPU_nRST,
//          11 halted, 16-23 GPO
#pragma once

#include <cstddef>
#include <cstdint>
#include <cstring>

#include "Vmachine_core.h"
#include "verilated.h"

extern "C" {
#include "sysmodels.h"
}

struct MainBoard {
	static constexpr double NS_PER_CLOCK = 1000.0 / 12.0;

	Vmachine_core *top = nullptr;
	sst39_t rom;
	uint8_t ram[1 << 19];
	uint64_t clocks = 0;
	int last_we = 1;
	uint8_t last_din = 0;
	int reading = 0;                      // 1 RAM, 2 ROM: a read cycle in progress
	uint32_t read_addr = 0;
	uint8_t read_data = 0;

	MainBoard() = default;
	MainBoard(const MainBoard &) = delete;
	MainBoard &operator=(const MainBoard &) = delete;
	~MainBoard() { delete top; }

	// a 512 KB ROM image (the chip's contents); nPOR held low
	void init(const void *data, size_t len)
	{
		delete top;
		top = new Vmachine_core;
		sst39_init(&rom);
		memcpy(rom.mem, data, len < sizeof rom.mem ? len : sizeof rom.mem);
		for (size_t i = 0; i < sizeof ram; i++)
			ram[i] = (uint8_t)(i * 13 + 5);                // SRAM powers up with junk
		clocks = 0;
		last_we = 1;
		reading = 0;
		apply(1 | 0x3F << 1 | 1 << 9 | 1 << 11);         // nPOR low: the supervisor holds reset
		top->clk = 0;
		top->eval();
	}

	uint32_t outputs() const
	{
		return (uint32_t)top->spi_sck | top->spi_mosi << 1 | (uint32_t)top->spi_n_cs << 2 | top->br_miso << 9 |
		       top->cpu_n_rst << 10 | top->cpu_halted << 11 | (uint32_t)top->gpo << 16;
	}

	double ns() const { return clocks * NS_PER_CLOCK; }

	// the memory bus: the chips answer combinationally, and latch writes on /WE's rising edge
	void memory()
	{
		uint32_t a = top->mem_a & ((1u << 19) - 1);
		uint64_t us = (uint64_t)(clocks * NS_PER_CLOCK / 1000.0);
		// one read per cycle (when /OE and /CE go low, or the address moves):
		// the SST39's toggle bits flip once per read, as on the chip
		int now_reading = !top->mem_n_oe ? (!top->mem_n_ce_ram ? 1 : !top->mem_n_ce_rom ? 2 : 0) : 0;
		if (now_reading && (now_reading != reading || a != read_addr))
			read_data = now_reading == 1 ? ram[a & 0xFFFF] : sst39_read(&rom, a, us);
		if (now_reading == 1)
			read_data = ram[a & 0xFFFF];      // RAM has no read side effects
		reading = now_reading;
		read_addr = a;
		uint8_t din = now_reading ? read_data : 0xFF;
		if (last_we == 0 && top->mem_n_we == 1) {         // /WE rose: the write happens
			if (!top->mem_n_ce_ram)
				ram[a & 0xFFFF] = last_din;
			else if (!top->mem_n_ce_rom)
				sst39_write(&rom, a, last_din, us);
		}
		last_we = top->mem_n_we;
		last_din = top->mem_d_out;
		top->mem_d_in = din;
	}

	void clock_once()
	{
		top->clk = 1;
		top->eval();
		memory();
		top->eval();
		top->clk = 0;
		top->eval();
		memory();
		top->eval();
		clocks++;
	}

	void apply(uint32_t in)
	{
		top->spi_miso = in & 1;
		top->slot_n_irq = (in >> 1) & 0x3F;
		top->br_sck = (in >> 7) & 1;
		top->br_mosi = (in >> 8) & 1;
		top->br_n_cs = (in >> 9) & 1;
		top->pwr_hi = (in >> 10) & 1;
		top->cpu_cdone = (in >> 11) & 1;
		top->n_por = (in >> 12) & 1;
	}

	// run up to `max` 12 MHz clocks with `in` on the input pins; stops after
	// the first clock whose watched outputs changed; returns the clocks run.
	// onClock() is called after every clock (the native machine publishes
	// its progress to the card threads there).
	template <class F>
	uint32_t run(uint32_t max, uint32_t in, F &&onClock)
	{
		apply(in);
		uint32_t watch = outputs() & 0x3FF, n = 0;
		while (n < max) {
			clock_once();
			n++;
			onClock();
			if ((outputs() & 0x3FF) != watch)
				break;
		}
		return n;
	}
	uint32_t run(uint32_t max, uint32_t in)
	{
		return run(max, in, [] {});
	}
};
