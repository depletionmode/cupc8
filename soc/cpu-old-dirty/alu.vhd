library ieee;
use ieee.std_logic_1164.all;
use ieee.numeric_std.all;

entity alu is
    port(
            n_en:		in std_logic;
				op:		in std_logic_vector(3 downto 0);
				a, b:		in unsigned(7 downto 0);
				r:			out unsigned(7 downto 0);
				zf:		out unsigned(0 downto 0)
         );
end alu;

architecture behavioural of alu is
signal ra, rb: unsigned(7 downto 0);
signal rres: unsigned(7 downto 0);
signal z: unsigned(0 downto 0) := "0";
begin

ra <= a;
rb <= b;
r <= rres;
zf <= z;

--- OPERATIONS
-- 0000 EQ
-- 0001 GT
-- 0010 LT
-- 0011 AND
-- 0100 OR
-- 0101 NOT
-- 0110 XOR
-- 0111 NOR
-- 1000 ADD
-- 1001 SUB
-- 1010 INC
-- 1011 DEC
-- 1100 SHL
-- 1101 SHR

process(n_en)
begin
	if(n_en = '0') then
		
		--z <= 	'1' when op = ("0000" and ra = rb) or (op = "0001" and ra > rb) or (op = "0010" and ra > rb) else
		--		(others=>'0');
				
		--rres <= 	(ra and rb) when op = "0011" else
		--			(ra or rb) when op = "0100" else
		--			(ra not rb) when op = "0101" else
		--			(ra xor rb) when op = "0110" else
		--			(ra nor rb) when op = "0111" else
		--			(ra + rb) when op = "1000" else
		--			(ra - rb) when op = "1001" else
		--			(ra + 1) when op = "1010" else
		--			(ra - 1) when op = "1011" else
		--			(others=>rres);
		
		case op is
			when "0000" =>
				if (ra = rb) then
					z <= "1";
				else
					z <= "0";
				end if;
			when "0001" =>
				if (ra > rb) then
					z <= "1";
				else
					z <= "0";
				end if;
			when "0010" =>
				if (ra < rb) then
					z <= "1";
				else
					z <= "0";
				end if;
			when "0011" =>
				rres <= ra and rb;
			when "0100" =>
				rres <= ra or rb;
			when "0101" =>
				rres <= not ra;
			when "0110" =>
				rres <= ra xor rb;
			when "0111" =>
				rres <= ra nor rb;
			when "1000" =>
				rres <= ra + rb;
			when "1001" =>
				rres <= ra - rb;
			when "1010" =>
				rres <= ra + 1;
			when "1011" =>
				rres <= ra - 1;
			when "1100" =>
				rres <= shift_left(ra, to_integer(rb));
			when "1101" =>
				rres <= shift_right(ra, to_integer(rb));
			when others => NULL;
		end case;
	end if;
end process;
end architecture;