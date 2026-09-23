-- The main board's chipset FPGA (iCE40HX4K-TQ144): chipset.vhd on its pins.
-- Port names are the pin names in hw/pins.yaml (build/hw/chipset.pcf binds
-- them); the two data buses are the only bidirectional pins.

library ieee;
use ieee.std_logic_1164.all;

entity chipset_top is
	port(
		CLK12:			in std_logic;
		nPOR:			in std_logic;
		PWR_HI:			in std_logic;
		CPU_A:			in std_logic_vector(15 downto 0);
		CPU_D:			inout std_logic_vector(7 downto 0);
		CPU_RW:			in std_logic;
		CPU_nSTB:		in std_logic;
		CPU_nRDY:		out std_logic;
		CPU_SYNC:		in std_logic;
		CPU_IRQ:		out std_logic_vector(3 downto 0);
		CPU_TMR_EXP:	in std_logic_vector(1 downto 0);
		CPU_HALTED:		in std_logic;
		CPU_WAITING:	in std_logic;
		CPU_nRST:		out std_logic;
		CPU_CDONE:		in std_logic;
		MEM_A:			out std_logic_vector(18 downto 0);
		MEM_D:			inout std_logic_vector(7 downto 0);
		MEM_nOE:		out std_logic;
		MEM_nWE:		out std_logic;
		MEM_nCE_RAM:	out std_logic;
		MEM_nCE_ROM:	out std_logic;
		SPI_SCK:		out std_logic;
		SPI_MOSI:		out std_logic;
		SPI_MISO:		in std_logic;
		SPI_nCS:		out std_logic_vector(6 downto 0);
		SLOT_nIRQ:		in std_logic_vector(5 downto 0);
		GPO:			out std_logic_vector(7 downto 0);
		BR_SCK:			in std_logic;
		BR_MOSI:		in std_logic;
		BR_MISO:		out std_logic;
		BR_nCS:			in std_logic
	);
end entity;

architecture rtl of chipset_top is
	signal cpu_d_out, mem_d_out: std_logic_vector(7 downto 0);
	signal cpu_d_oe, mem_d_oe: std_logic;
begin
	CPU_D <= cpu_d_out when cpu_d_oe = '1' else (others => 'Z');
	MEM_D <= mem_d_out when mem_d_oe = '1' else (others => 'Z');

	core: entity work.chipset port map(
		clk => CLK12, n_por => nPOR,
		cpu_a => CPU_A, cpu_d_in => CPU_D, cpu_d_out => cpu_d_out, cpu_d_oe => cpu_d_oe,
		cpu_rw => CPU_RW, cpu_n_stb => CPU_nSTB, cpu_n_rdy => CPU_nRDY, cpu_sync => CPU_SYNC,
		cpu_irq => CPU_IRQ, cpu_tmr_exp => CPU_TMR_EXP, cpu_halted => CPU_HALTED,
		cpu_waiting => CPU_WAITING, cpu_n_rst => CPU_nRST, cpu_cdone => CPU_CDONE,
		mem_a => MEM_A, mem_d_in => MEM_D, mem_d_out => mem_d_out, mem_d_oe => mem_d_oe,
		mem_n_oe => MEM_nOE, mem_n_we => MEM_nWE, mem_n_ce_ram => MEM_nCE_RAM, mem_n_ce_rom => MEM_nCE_ROM,
		spi_sck => SPI_SCK, spi_mosi => SPI_MOSI, spi_miso => SPI_MISO, spi_n_cs => SPI_nCS,
		slot_n_irq => SLOT_nIRQ, gpo => GPO, pwr_hi => PWR_HI,
		br_sck => BR_SCK, br_mosi => BR_MOSI, br_miso => BR_MISO, br_n_cs => BR_nCS);
end architecture;
