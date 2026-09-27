-- The main board's logic for the whole-machine emulator (test/emu/machine.mjs):
-- the CPU card's cpu.vhd and the chipset's chipset.vhd, joined by the CPU
-- bus as on the boards. Synthesised with GHDL and compiled with Verilator
-- (tools/emu_build.sh); memory and everything off the board are models in
-- soc/emu/core.cpp and in the card emulators.

library ieee;
use ieee.std_logic_1164.all;
use ieee.numeric_std.all;

entity machine_core is
	port(
		clk:			in std_logic;
		n_por:			in std_logic;
		pwr_hi:			in std_logic;
		cpu_cdone:		in std_logic;
		-- Physical CPU-socket contacts, packed source-bit indices from KiCad.
		cpu_a_map:		in std_logic_vector(63 downto 0);
		cpu_d_map:		in std_logic_vector(23 downto 0);
		cpu_d_inv_map:	in std_logic_vector(23 downto 0);
		cpu_a_connected:	in std_logic_vector(15 downto 0);
		cpu_d_connected:	in std_logic_vector(7 downto 0);
		cpu_clk_connected:	in std_logic;
		cpu_rst_connected:	in std_logic;
		chipset_clk_connected:	in std_logic;

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
	signal cpu_din, cs_din, cpu_dout, cs_dout: std_logic_vector(7 downto 0);
	signal a_chip: std_logic_vector(15 downto 0);
	signal cpu_doe, cs_doe, rw, n_stb, n_rdy, sync, halted, waiting, n_rst: std_logic;
	signal irq: std_logic_vector(3 downto 0);
	signal cpu_clk: std_logic;
	signal chipset_clk: std_logic;
	signal cpu_rst_at_pad: std_logic;
	signal tmr_exp: std_logic_vector(1 downto 0);
	signal fl: std_logic_vector(1 downto 0);
begin
	cpu_clk <= clk when cpu_clk_connected = '1' else '0';
	-- An open clock branch leaves the chipset input undefined in hardware.
	-- Hold it low here to expose the missing digital route.
	chipset_clk <= clk when chipset_clk_connected = '1' else '0';
	-- An open FPGA reset pad has undefined voltage. Holding it low is a
	-- deterministic digital counterexample, not a prediction of that voltage.
	cpu_rst_at_pad <= n_rst when cpu_rst_connected = '1' else '0';
	-- Contact order comes from both KiCad connector netlists. The data bus
	-- has separate views for each receiver, preserving driver enable rules.
	address_wires: for i in 0 to 15 generate
		-- An open series-channel bit has undefined voltage on real copper.
		-- Hold it high here solely for a deterministic wiring counterexample.
		a_chip(i) <= a(to_integer(unsigned(cpu_a_map(4*i+3 downto 4*i))))
			when cpu_a_connected(i) = '1' else '1';
	end generate;
	data_wires: for i in 0 to 7 generate
		cs_din(i) <= cpu_dout(to_integer(unsigned(cpu_d_map(3*i+2 downto 3*i))))
			when cpu_doe = '1' and cpu_d_connected(i) = '1' else
			'1' when cpu_doe = '1' else cs_dout(i);
		cpu_din(i) <= cpu_dout(i) when cpu_doe = '1' else
			cs_dout(to_integer(unsigned(cpu_d_inv_map(3*i+2 downto 3*i))))
			when cpu_d_connected(to_integer(unsigned(cpu_d_inv_map(3*i+2 downto 3*i)))) = '1' else '1';
	end generate;

	cpu0: entity work.cpu port map(
		clk => cpu_clk, n_rst => cpu_rst_at_pad, a => a, d_in => cpu_din, d_out => cpu_dout, d_oe => cpu_doe,
		rw => rw, n_stb => n_stb, n_rdy => n_rdy, sync => sync, irq => irq, tmr_exp => tmr_exp,
		halted => halted, waiting => waiting,
		dbg_pc => dbg_pc, dbg_sp => dbg_sp, dbg_r0 => dbg_r0, dbg_r1 => dbg_r1, dbg_f => fl);

	cs0: entity work.chipset port map(
		clk => chipset_clk, n_por => n_por,
		cpu_a => a_chip, cpu_d_in => cs_din, cpu_d_out => cs_dout, cpu_d_oe => cs_doe, cpu_rw => rw,
		cpu_n_stb => n_stb, cpu_n_rdy => n_rdy, cpu_sync => sync, cpu_irq => irq,
		cpu_tmr_exp => tmr_exp, cpu_halted => halted, cpu_waiting => waiting, cpu_n_rst => n_rst,
		cpu_cdone => cpu_cdone,
		mem_a => mem_a, mem_d_in => mem_d_in, mem_d_out => mem_d_out, mem_d_oe => mem_d_oe,
		mem_n_oe => mem_n_oe, mem_n_we => mem_n_we, mem_n_ce_ram => mem_n_ce_ram, mem_n_ce_rom => mem_n_ce_rom,
		spi_sck => spi_sck, spi_mosi => spi_mosi, spi_miso => spi_miso, spi_n_cs => spi_n_cs,
		slot_n_irq => slot_n_irq, gpo => gpo, pwr_hi => pwr_hi,
		br_sck => br_sck, br_mosi => br_mosi, br_miso => br_miso, br_n_cs => br_n_cs);

	cpu_n_rst <= cpu_rst_at_pad;
	cpu_halted <= halted;
end architecture;
