// The main board for the whole-machine emulator, as a Node addon: the
// Verilated CPU + chipset netlist (machine_core.vhd), the SRAM, and the
// SST39VF040 ROM chip (fw/test/sysmodels.c, the same model as the sysctl
// tests). test/emu/machine.mjs steps it in lockstep with the card emulators.
//
//   core.init(romImage)         a 512 KB ROM image (the chip's contents)
//   core.run(clocks, inputs)    run up to `clocks` 12 MHz clocks; stops after the
//                               first clock whose watched outputs changed;
//                               returns the clocks run
//   core.outputs()              the pins the cards see (bit layout below)
//   core.ns() / core.rom() / core.ram() / core.state()
//
// inputs:  bit 0 SPI MISO, 1-6 SLOT_nIRQ[5:0], 7 BR_SCK, 8 BR_MOSI, 9 BR_nCS,
//          10 PWR_HI, 11 CPU_CDONE, 12 nPOR
// outputs: bit 0 SPI SCK, 1 MOSI, 2-8 SPI_nCS[6:0], 9 BR_MISO, 10 CPU_nRST,
//          11 halted, 16-23 GPO

#include <node_api.h>

#include <cstdint>
#include <cstring>

#include "Vmachine_core.h"
#include "verilated.h"

extern "C" {
#include "sysmodels.h"
}

static Vmachine_core *top;
static sst39_t rom;
static uint8_t ram[1 << 19];
static uint64_t clocks;
static int last_we = 1;
static uint8_t last_din;
static int reading;                       // 1 RAM, 2 ROM: a read cycle in progress
static uint32_t read_addr;
static uint8_t read_data;

static const double NS_PER_CLOCK = 1000.0 / 12.0;

static uint32_t outputs()
{
	return (uint32_t)top->spi_sck | top->spi_mosi << 1 | (uint32_t)top->spi_n_cs << 2 | top->br_miso << 9 |
	       top->cpu_n_rst << 10 | top->cpu_halted << 11 | (uint32_t)top->gpo << 16;
}

// the memory bus: the chips answer combinationally, and latch writes on /WE's rising edge
static void memory()
{
	uint32_t a = top->mem_a & ((1u << 19) - 1);
	uint64_t us = (uint64_t)(clocks * NS_PER_CLOCK / 1000.0);
	// one read per cycle (when /OE and /CE go low, or the address moves):
	// the SST39's toggle bits flip once per read, as on the chip
	int now_reading = !top->mem_n_oe ? (!top->mem_n_ce_ram ? 1 : !top->mem_n_ce_rom ? 2 : 0) : 0;
	if (now_reading && (now_reading != reading || a != read_addr))
		read_data = now_reading == 1 ? ram[a & 0xFFFF] : sst39_read(&rom, a, us);
	if (now_reading == 1)
		read_data = ram[a & 0xFFFF];          // RAM has no read side effects
	reading = now_reading;
	read_addr = a;
	uint8_t din = now_reading ? read_data : 0xFF;
	if (last_we == 0 && top->mem_n_we == 1) {             // /WE rose: the write happens
		if (!top->mem_n_ce_ram)
			ram[a & 0xFFFF] = last_din;
		else if (!top->mem_n_ce_rom)
			sst39_write(&rom, a, last_din, us);
	}
	last_we = top->mem_n_we;
	last_din = top->mem_d_out;
	top->mem_d_in = din;
}

static void clock_once()
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

static void apply(uint32_t in)
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

// ------------------------------------------------------------------ N-API

#define CALL(e) do { if ((e) != napi_ok) { napi_throw_error(env, nullptr, #e); return nullptr; } } while (0)

static napi_value js_init(napi_env env, napi_callback_info info)
{
	size_t argc = 1;
	napi_value argv[1];
	CALL(napi_get_cb_info(env, info, &argc, argv, nullptr, nullptr));
	void *data;
	size_t len;
	CALL(napi_get_buffer_info(env, argv[0], &data, &len));
	delete top;
	top = new Vmachine_core;
	sst39_init(&rom);
	memcpy(rom.mem, data, len < sizeof rom.mem ? len : sizeof rom.mem);
	for (size_t i = 0; i < sizeof ram; i++)
		ram[i] = (uint8_t)(i * 13 + 5);                    // SRAM powers up with junk
	clocks = 0;
	last_we = 1;
	reading = 0;
	apply(1 | 0x3F << 1 | 1 << 9 | 1 << 11);             // nPOR low: the supervisor holds reset
	top->clk = 0;
	top->eval();
	return nullptr;
}

static napi_value js_run(napi_env env, napi_callback_info info)
{
	size_t argc = 2;
	napi_value argv[2];
	CALL(napi_get_cb_info(env, info, &argc, argv, nullptr, nullptr));
	uint32_t max, in;
	CALL(napi_get_value_uint32(env, argv[0], &max));
	CALL(napi_get_value_uint32(env, argv[1], &in));
	apply(in);
	uint32_t watch = outputs() & 0x3FF, n = 0;
	while (n < max) {
		clock_once();
		n++;
		if ((outputs() & 0x3FF) != watch)
			break;
	}
	napi_value r;
	CALL(napi_create_uint32(env, n, &r));
	return r;
}

static napi_value js_outputs(napi_env env, napi_callback_info)
{
	napi_value r;
	CALL(napi_create_uint32(env, outputs(), &r));
	return r;
}

static napi_value js_ns(napi_env env, napi_callback_info)
{
	napi_value r;
	CALL(napi_create_double(env, clocks * NS_PER_CLOCK, &r));
	return r;
}

static napi_value js_rom(napi_env env, napi_callback_info)
{
	napi_value r;
	CALL(napi_create_external_buffer(env, sizeof rom.mem, rom.mem, nullptr, nullptr, &r));
	return r;
}

static napi_value js_ram(napi_env env, napi_callback_info)
{
	napi_value r;
	CALL(napi_create_external_buffer(env, 65536, ram, nullptr, nullptr, &r));
	return r;
}

static napi_value js_state(napi_env env, napi_callback_info)
{
	napi_value o, v;
	CALL(napi_create_object(env, &o));
	const struct { const char *k; uint32_t v; } f[] = {
		{"pc", top->dbg_pc}, {"sp", top->dbg_sp}, {"r0", top->dbg_r0}, {"r1", top->dbg_r1},
		{"halted", top->cpu_halted}, {"nrst", top->cpu_n_rst}, {"gpo", top->gpo},
	};
	for (auto &e : f) {
		CALL(napi_create_uint32(env, e.v, &v));
		CALL(napi_set_named_property(env, o, e.k, v));
	}
	return o;
}

static napi_value init_module(napi_env env, napi_value exports)
{
	const struct { const char *name; napi_callback fn; } fns[] = {
		{"init", js_init}, {"run", js_run}, {"outputs", js_outputs}, {"ns", js_ns},
		{"rom", js_rom}, {"ram", js_ram}, {"state", js_state},
	};
	for (auto &f : fns) {
		napi_value v;
		CALL(napi_create_function(env, f.name, NAPI_AUTO_LENGTH, f.fn, nullptr, &v));
		CALL(napi_set_named_property(env, exports, f.name, v));
	}
	return exports;
}

NAPI_MODULE(NODE_GYP_MODULE_NAME, init_module)
