library ieee;
use ieee.std_logic_1164.all;
use ieee.numeric_std.all;

entity cpu is
	port(
			clk: 		in std_logic;
			srst:		in std_logic;
			
			halt:		out std_logic -- high on catastrophic failure
		);
end entity;

architecture behavioural of cpu is
signal r0, r1, r2, r3:	unsigned(7 downto 0);
signal pc:	unsigned(15 downto 0);
signal ins: unsigned(7 downto 0);
begin

process(clk, srst)
begin
-- todo reset vector
if(rising_edge(clk)) then
-- fetch
ins <= get mem from pc
-- decode
-- execute
-- write back
end if;
end process;

end architecture;