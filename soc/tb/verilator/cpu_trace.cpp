// Verilator harness for the synthesised CPU netlist (tests CPU-002, SYN-001).
//
// Same chipset model and trace format as soc/tb/tb_cpu_trace.vhd, so the
// output diffs directly against tools/simtrace.nim:
//   cpu_trace <image.bin> <waits> <seed> [max_cycles]
// waits < 0: random 0..15 wait states per bus cycle from seed.
//
// Per clock edge: read the CPU's pre-edge outputs, compute the chipset's
// response, clock the CPU on the old inputs, then apply the new inputs.

#include "Vcpu.h"
#include "verilated.h"
#include <cstdio>
#include <cstdlib>
#include <cstdint>
#include <vector>

int main(int argc, char **argv) {
	Verilated::commandArgs(argc, argv);
	if (argc < 4) {
		fprintf(stderr, "usage: cpu_trace <image.bin> <waits> <seed> [max_cycles]\n");
		return 2;
	}
	const int waits = atoi(argv[2]);
	const unsigned seed = (unsigned)atoi(argv[3]);
	const uint64_t max_cycles = argc > 4 ? strtoull(argv[4], nullptr, 10) : 20000000ull;

	std::vector<uint8_t> mem(65536, 0);
	FILE *f = fopen(argv[1], "rb");
	if (!f) { perror(argv[1]); return 2; }
	size_t n = fread(&mem[0x1000], 1, 65536 - 0x1000, f);
	fclose(f);
	const unsigned image_end = 0x1000 + (unsigned)n;
	mem[0xe000] = 0xb0; mem[0xe001] = 0x00; mem[0xe002] = 0x10;	// b $1000

	Vcpu cpu;
	cpu.clk = 0; cpu.n_rst = 0; cpu.n_rdy = 1; cpu.d_in = 0; cpu.irq = 0;
	cpu.eval();

	uint16_t lfsr = (uint16_t)(seed % 65535 + 1);
	unsigned pending = 0, mask = 0;
	bool busy = false, started = false;
	unsigned cyc_a = 0, cyc_d = 0; int cyc_rw = 1, count = 0;
	unsigned rdy = 1;

	for (uint64_t cycle = 1;; cycle++) {
		// pre-edge view of the CPU
		unsigned p = pending, new_mask = mask, new_rdy = 1, new_din = 0;
		bool done = false;

		if (rdy == 0) {								// cycle completes at this edge
			busy = false;
			if (cyc_rw == 0) {
				if (started) printf("W %04x %02x\n", cyc_a, cyc_d);
				if (cyc_a == 0xf200) p &= ~cyc_d & 0xf;
				else if (cyc_a == 0xf201) new_mask = cyc_d & 0xf;
				mem[cyc_a] = (uint8_t)cyc_d;
			}
		} else if (!busy && cpu.n_stb == 0 && cpu.n_rst) {	// new cycle
			busy = true;
			cyc_a = cpu.a; cyc_rw = cpu.rw; cyc_d = cpu.d_out;
			if ((cpu.rw == 0) != (cpu.d_oe == 1)) {
				printf("E protocol D driven wrongly for rw=%d\n", cpu.rw);
				return 1;
			}
			if (waits >= 0) count = waits;
			else {
				unsigned bit = ((lfsr >> 15) ^ (lfsr >> 13) ^ (lfsr >> 12) ^ (lfsr >> 10)) & 1;
				lfsr = (uint16_t)((lfsr << 1) | bit);
				count = lfsr & 0xf;
			}
			if (cpu.sync) {
				if (cpu.dbg_pc == 0x1000) started = true;
				if (started) {
					printf("S %04x %02x %02x %x %04x\n", cpu.dbg_pc, cpu.dbg_r0, cpu.dbg_r1,
						   cpu.dbg_f, cpu.dbg_sp);
					if (cyc_a >= image_end) { printf("E end\n"); done = true; }
					else if ((mem[cyc_a] & 0xf8) == 0xf8) { printf("E halt\n"); done = true; }
				}
			}
		} else if (busy) {
			if (cpu.n_stb != 0 || cpu.a != cyc_a || (int)cpu.rw != cyc_rw) {
				printf("E protocol request changed before /RDY\n");
				return 1;
			}
		}

		if (busy && rdy == 1) {
			if (count <= 0) {
				new_rdy = 0;
				if (cyc_rw == 1)
					new_din = cyc_a == 0xf200 ? p : cyc_a == 0xf201 ? mask : mem[cyc_a];
			} else {
				count--;
			}
		}
		if (cpu.tmr_exp & 1) p |= 2;
		if (cpu.tmr_exp & 2) p |= 4;

		// clock the CPU on the old inputs
		cpu.clk = 1;
		cpu.eval();

		// apply the chipset's new outputs
		pending = p; mask = new_mask; rdy = new_rdy;
		cpu.n_rdy = new_rdy;
		cpu.d_in = new_din;
		cpu.irq = pending & mask;
		if (cycle == 5) cpu.n_rst = 1;
		cpu.clk = 0;
		cpu.eval();

		if (done) break;
		if (cycle >= max_cycles) { printf("E limit\n"); break; }
	}
	return 0;
}
