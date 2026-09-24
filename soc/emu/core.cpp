// The main board for the whole-machine emulator, as a Node addon: the
// Verilated CPU + chipset netlist (machine_core.vhd), the SRAM, and the
// SST39VF040 ROM chip (fw/test/sysmodels.c, the same model as the sysctl
// tests), all in board.h (shared with the native machine, emu/machine/).
// test/emu/machine.mjs steps it in lockstep with the card emulators.
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

#include "board.h"

static MainBoard *board;

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
	if (!board)
		board = new MainBoard;
	board->init(data, len);
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
	uint32_t n = board->run(max, in);
	napi_value r;
	CALL(napi_create_uint32(env, n, &r));
	return r;
}

static napi_value js_outputs(napi_env env, napi_callback_info)
{
	napi_value r;
	CALL(napi_create_uint32(env, board->outputs(), &r));
	return r;
}

static napi_value js_ns(napi_env env, napi_callback_info)
{
	napi_value r;
	CALL(napi_create_double(env, board->ns(), &r));
	return r;
}

static napi_value js_rom(napi_env env, napi_callback_info)
{
	napi_value r;
	CALL(napi_create_external_buffer(env, sizeof board->rom.mem, board->rom.mem, nullptr, nullptr, &r));
	return r;
}

static napi_value js_ram(napi_env env, napi_callback_info)
{
	napi_value r;
	CALL(napi_create_external_buffer(env, 65536, board->ram, nullptr, nullptr, &r));
	return r;
}

static napi_value js_state(napi_env env, napi_callback_info)
{
	napi_value o, v;
	CALL(napi_create_object(env, &o));
	Vmachine_core *top = board->top;
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
