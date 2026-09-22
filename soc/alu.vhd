-- CUPC/8 ALU (combinational). `op` is the instruction's opcode bits 7..3.
-- Semantics follow the manual's instruction table (and tools/sim.nim):
--   EQ/GT/LT set Z and leave the register alone; the others write Ra and
--   leave Z alone. Shifts by 8 or more give 0.

library ieee;
use ieee.std_logic_1164.all;
use ieee.numeric_std.all;

entity alu is
	port(
		op:			in std_logic_vector(4 downto 0);
		a, b:		in unsigned(7 downto 0);
		r:			out unsigned(7 downto 0);
		z:			out std_logic;
		writes_r:	out std_logic;		-- op writes its result to Ra
		writes_z:	out std_logic		-- op sets Z
	);
end entity;

architecture rtl of alu is
begin
	process(op, a, b)
		variable sh: natural;
	begin
		r <= a;
		z <= '0';
		writes_r <= '1';
		writes_z <= '0';
		if b > 7 then
			sh := 8;
		else
			sh := to_integer(b);
		end if;
		case op is
			when "00000" =>		-- EQ
				writes_r <= '0'; writes_z <= '1';
				if a = b then z <= '1'; end if;
			when "00001" =>		-- GT
				writes_r <= '0'; writes_z <= '1';
				if a > b then z <= '1'; end if;
			when "00010" =>		-- LT
				writes_r <= '0'; writes_z <= '1';
				if a < b then z <= '1'; end if;
			when "00011" => r <= a and b;				-- AND
			when "00100" => r <= a or b;				-- OR
			when "00110" => r <= a xor b;				-- XOR
			when "00111" => r <= not (a or b);			-- NOR
			when "01000" => r <= a + b;					-- ADD
			when "01001" => r <= a - b;					-- SUB
			when "01100" => r <= shift_left(a, sh);		-- SHL
			when "01101" => r <= shift_right(a, sh);	-- SHR
			when others => writes_r <= '0';				-- not an ALU op
		end case;
	end process;
end architecture;
