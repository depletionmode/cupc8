library ieee;
use ieee.std_logic_1164.all;
use ieee.numeric_std.all;

entity spi is
	port(
			cs:		out std_logic;
			clk:		out std_logic;
			mosi:		out std_logic;
			miso:		in std_logic;
		);
end entity;

architecture behavioural of spi is
begin
process(clk)
begin
if(rising_edge(clk)) then
	if(cs='0') then
		-- do spi
	else
		mosi <= 'Z';
	end if;
end if;
end process;
end architecture;