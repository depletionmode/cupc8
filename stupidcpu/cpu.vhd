library ieee;
use ieee.std_logic_1164.all;
use ieee.numeric_std.all;

entity cpu is
	port(
			clk: 			in std_logic;
			srst:			in std_logic;
			halt:			out std_logic; -- high on catastrophic failure
			
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
			zf:			in bit
		);
end entity;

-- instructions
-- 1 bit - alu  indicator
-- 4 bit - instruction
-- 1 bit - immediate indicator
-- 1 bit - register 1
-- 1 bit - register 2 (ignored if imm)

architecture behavioural of cpu is
signal r0, r1:	unsigned(7 downto 0);
signal pc:	unsigned(15 downto 0);
signal ins: unsigned(7 downto 0);
variable imm_fetched: bit;
signal imm_value: unsigned(7 downto 0);
type stages is (fetch, decode, execute, writeback, reset, fetch_imm, fetch_addr1, fetch_addr2);
signal stage: stages <= 'reset';
begin

mem_addr <= to_stdlogicvector(unsigned(pc));

process(clk)
begin
case stage is
	when fetch =>
		ins <= mem_data;
		mem_rd <= '0';
		stage <= decode;
	when fetch_imm =>
		imm_value <= mem_data;
		mem_rd <= '0';
		imm_fetched <= '1';
		stage <= decode;
	when decode =>
		pc <= pc + 1;
		mem_rd <= '1';
		if(ins(5) = '1' and imm_fetched = '0') then
			-- fetch imm
			stage <= fetch_imm;
		else
			case ins(7) is
				when '0' =>
					-- alu op
					if(ins(0) = '0') then
						ra <= r0;
					else
						ra <= r1;
					end if;
					if(ins(5) = '1') then
						rb <= imm_value;
					else
						--rb <= r0 when ins(1) = '0' else r1;
						if(ins(1) = '0') then
							rb <= r0;
						else
							rb <= r1;
						end if;
					end if;
				when others => NULL;
			end case;
			stage <= execute;
		end if;
	when execute =>
		case ins(7) is
			when '0' =>
				alu_ra <= ra;
				alu_rb <= rb;
				alu_en <= '0';
			when others => NULL;
		end case;
		stage <= writeback;
	when writeback =>
		case ins(7) is
			when '0' =>
				alu_en <= '1';
				r0 <= alu_res;
			when others => NULL;
		end case;
		stage <= fetch;
	when reset =>
		pc <= x"100";
	when others =>
		stage <= reset;
	end case;
end process;

process( srst)
begin
	stage <= reset;
end process;

end architecture;