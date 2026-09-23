-- The main board's logic for the whole-machine emulator (test/emu/machine.mjs):
-- the CPU card's cpu.vhd and the chipset's chipset.vhd, joined by the CPU
-- bus as on the boards. Synthesised with GHDL and compiled with Verilator
-- (tools/emu_build.sh); memory and everything off the board are models in
-- soc/emu/core.cpp and in the card emulators.

library ieee;
use ieee.std_logic_1164.all;

entity machine_core is
	port(
		clk:			in std_logic;
		n_por:			in std_logic;
		pwr_hi:			in std_logic;
		cpu_cdone:		in std_logic;

		mem_a:			out std_logic_vector(18 downto 0);
		mem_d_in:		in std_logic_vector(7 downto 0);
		mem_d_out:		out std_logic_vector(7 downto 0);
		mem_d_oe:		out std_logic;
		mem_n_oe:		out std_logic;
		mem_n_we:		out std_logic;
		mem_n_ce_ram:	out std_logic;
		mem_n_ce_rom:	out std_logic;

		spi_sck:		out std_logic;
		spi_mosi:		out std_logic;
		spi_miso:		in std_logic;
		spi_n_cs:		out std_logic_vector(6 downto 0);
		slot_n_irq:		in std_logic_vector(5 downto 0);
		gpo:			out std_logic_vector(7 downto 0);

		br_sck:			in std_logic;
		br_mosi:		in std_logic;
		br_miso:		out std_logic;
		br_n_cs:		in std_logic;

		cpu_n_rst:		out std_logic;
		cpu_halted:		out std_logic;
		dbg_pc:			out std_logic_vector(15 downto 0);
		dbg_sp:			out std_logic_vector(15 downto 0);
		dbg_r0:			out std_logic_vector(7 downto 0);
		dbg_r1:			out std_logic_vector(7 downto 0)
	);
end entity;

architecture rtl of machine_core is
	signal a: std_logic_vector(15 downto 0);
	signal d, cpu_dout, cs_dout: std_logic_vector(7 downto 0);
	signal cpu_doe, cs_doe, rw, n_stb, n_rdy, sync, halted, waiting, n_rst: std_logic;
	signal irq: std_logic_vector(3 downto 0);
	signal tmr_exp: std_logic_vector(1 downto 0);
	signal fl: std_logic_vector(1 downto 0);
begin
	-- the CPU bus's data lines: whoever has D enabled (never both: BUS-001)
	d <= cpu_dout when cpu_doe = '1' else cs_dout;

	cpu0: entity work.cpu port map(
		clk => clk, n_rst => n_rst, a => a, d_in => d, d_out => cpu_dout, d_oe => cpu_doe,
		rw => rw, n_stb => n_stb, n_rdy => n_rdy, sync => sync, irq => irq, tmr_exp => tmr_exp,
		halted => halted, waiting => waiting,
		dbg_pc => dbg_pc, dbg_sp => dbg_sp, dbg_r0 => dbg_r0, dbg_r1 => dbg_r1, dbg_f => fl);

	cs0: entity work.chipset port map(
		clk => clk, n_por => n_por,
		cpu_a => a, cpu_d_in => d, cpu_d_out => cs_dout, cpu_d_oe => cs_doe, cpu_rw => rw,
		cpu_n_stb => n_stb, cpu_n_rdy => n_rdy, cpu_sync => sync, cpu_irq => irq,
		cpu_tmr_exp => tmr_exp, cpu_halted => halted, cpu_waiting => waiting, cpu_n_rst => n_rst,
		cpu_cdone => cpu_cdone,
		mem_a => mem_a, mem_d_in => mem_d_in, mem_d_out => mem_d_out, mem_d_oe => mem_d_oe,
		mem_n_oe => mem_n_oe, mem_n_we => mem_n_we, mem_n_ce_ram => mem_n_ce_ram, mem_n_ce_rom => mem_n_ce_rom,
		spi_sck => spi_sck, spi_mosi => spi_mosi, spi_miso => spi_miso, spi_n_cs => spi_n_cs,
		slot_n_irq => slot_n_irq, gpo => gpo, pwr_hi => pwr_hi,
		br_sck => br_sck, br_mosi => br_mosi, br_miso => br_miso, br_n_cs => br_n_cs);

	cpu_n_rst <= n_rst;
	cpu_halted <= halted;
end architecture;
