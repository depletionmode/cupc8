-- The CPU card's FPGA (iCE40HX4K-TQ144): cpu.vhd on its pins. Port names are
-- the pin names in hw/pins.yaml (build/hw/cpucard.pcf binds them).

library ieee;
use ieee.std_logic_1164.all;

entity cpucard_top is
	port(
		CPU_CLK:		in std_logic;
		CPU_nRST:		in std_logic;
		CPU_A:			out std_logic_vector(15 downto 0);
		CPU_D:			inout std_logic_vector(7 downto 0);
		CPU_RW:			out std_logic;
		CPU_nSTB:		out std_logic;
		CPU_nRDY:		in std_logic;
		CPU_SYNC:		out std_logic;
		CPU_IRQ:		in std_logic_vector(3 downto 0);
		CPU_TMR_EXP:	out std_logic_vector(1 downto 0);
		CPU_HALTED:		out std_logic;
		CPU_WAITING:	out std_logic
	);
end entity;

architecture rtl of cpucard_top is
	signal d_out: std_logic_vector(7 downto 0);
	signal d_oe: std_logic;
begin
	CPU_D <= d_out when d_oe = '1' else (others => 'Z');

	core: entity work.cpu port map(
		clk => CPU_CLK, n_rst => CPU_nRST, a => CPU_A, d_in => CPU_D, d_out => d_out, d_oe => d_oe,
		rw => CPU_RW, n_stb => CPU_nSTB, n_rdy => CPU_nRDY, sync => CPU_SYNC, irq => CPU_IRQ,
		tmr_exp => CPU_TMR_EXP, halted => CPU_HALTED, waiting => CPU_WAITING,
		dbg_pc => open, dbg_sp => open, dbg_r0 => open, dbg_r1 => open, dbg_f => open);
end architecture;
