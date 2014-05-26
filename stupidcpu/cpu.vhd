library ieee;
use ieee.std_logic_1164.all;
use ieee.numeric_std.all;

entity cpu is
	port(
			clk: 			in std_logic;
			srst:			in std_logic;
			halt:			out std_logic -- high on catastrophic failure
			
			-- mmu
			mem_addr:	out std_logic_vector(15 downto 0);
			mem_data:	inout std_logic_vector(7 downto 0);
			mem_wr:		out std_logic;
			mem_rd:		out std_logic;
			
			-- alu
			alu_en:		out std_logic;
			alu_ra:		out unsigned(7 downto 0);
			alu_rb:		out unsigned(7 downto 0);
			alu_res:		in unsigned(7 downto 0);
			zf:			in bit;
		);
end entity;

-- instructions
-- 1 bit - alu  indicator
-- 4 bit - instruction
-- 1 bit - immediate indicator
-- 1 bit - src register
-- 1 bit - dst register

architecture behavioural of cpu is
signal r0, r1:	unsigned(7 downto 0);
signal pc:	unsigned(15 downto 0);
signal ins: unsigned(7 downto 0);
type stages is (fetch, decode, execute, writeback, reset);
signal stage, stage_next: stages;
begin

addr_bus <= pc;

process(stage)
begin
case stage is
	when fetch =>
		ins <= bus_data;
		mem_rd <= '0';
		stage <= decode;
	when decode =>
		mem_rd <= '1'
		case ins(7) is
			when '0' =>
				-- alu op
				ra <= r0 when ins(1) = '0' else r1;
				rb <= r0 when ins(0) = '0' else r1;
			end case;
		stage <= execute;
	when execute =>
		stage <= writeback;
	when writeback =>
		stage <= fetch;
	when reset =>
		pc <= x"100";
	when others =>
		stage <= reset;
end process;

process(clk, srst)
begin
-- todo reset vector
if(rising_edge(clk)) then
-- fetch
-- -- ins <= get from sram @ pc
-- decode

-- execute
-- write back
end if;
end process;

end architecture;