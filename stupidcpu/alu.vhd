library ieee;
use ieee.std_logic_1164.all;
use ieee.numeric_std.all;

entity alu is
    port(
            clk:		in std_logic;
				op:		in std_logic_vector(3 downto 0);
				a, b:		in unsigned(7 downto 0);
				r:			out unsigned(7 downto 0);
				zf, cf:	out bit
         );
end alu;

architecture behavioural of alu is
signal ra, rb: unsigned(7 downto 0);
signal rres: unsigned(7 downto 0);
signal c, z: bit;
begin

ra <= a;
rb <= b;
r <= rres(7 downto 0);
zf <= z;
cf <= c;

--- OPERATIONS
-- 0000 EQ
-- 0001 AND
-- 0010 OR
-- 0011 NOT
-- 0100 XOR
-- 0101 NOR
--
-- 1001 ADD
-- 1010 SUB
-- 1011 MOD
-- 1100 DIV
-- 1101 MUL
-- 1110 INC
-- 1111 DEC
---

process(clk)
begin
	if(rising_edge(clk)) then
		z <= '0';
		c <= '0';
		case op is
			when "0000" =>
				if (ra = rb) then
					z <= '1';
				else
					z <= '0';
				end if;
			when "0001" =>
				rres <= ra and rb;
			when "0010" =>
				rres <= ra or rb;
			when "0011" =>
				rres <= not ra;
			when "0100" =>
				rres <= ra xor rb;
			when "0101" =>
				rres <= ra nor rb;
			when "1001" =>
				rres <= ra + rb;
			when "1010" =>
				rres <= ra - rb;
			when "1011" => -- BORKED!!
				rres <= ra mod rb;
			when "1100" =>
				rres <= ra / rb;
			--when "1101" => -- todo
				--rres <= ra * rb;
			when "1110" =>
				rres <= ra + 1;
			when "1111" =>
				rres <= ra - 1;
			when others => NULL;
		end case;
	end if;
end process;
end architecture;