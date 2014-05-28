library ieee;
use ieee.std_logic_1164.all;
use ieee.numeric_std.all;

-- spi
-- clk devided by clk_div * 2
-- todo: pll, support for cpha = 0 (currently defaults to cpha = 1)

entity spi is
	port(
			ss:		out std_logic;
			sck:		out std_logic;
			mosi:		out std_logic := 'Z';
			miso:		in std_logic;
			
			clk:			in std_logic;
			clk_div:		in integer := 1;
			cont:			in std_logic := '1'; -- 1 - continue, 0 - last
			cpol:			in std_logic := '1';
			cpha:			in std_logic := '1';
			data:			inout std_logic_vector(7 downto 0);
			n_rdy:		out std_logic := '1';
			n_transfer:	in std_logic := '1'
		);
end entity;


architecture behavioural of spi is
variable bit_current: integer range 0 to 32 := 0;
variable n_done: std_logic := '1';
variable clk_counter: integer := 0;
signal buffer_tx, buffer_rx:	std_logic_vector(7 downto 0);
signal clk_internal: std_logic;
begin

process(clk)
begin
sck <= clk_internal;
end process;

process(clk_internal)
begin
if rising_edge(clk) then
	if clk_div = 0 then
		clk_internal <= clk;
	else
		if clk_counter < clk_div then
			if clk_counter = clk_div - 1 then
				clk_internal <= not clk_internal;
				clk_counter := 0;
			else
				clk_counter := clk_counter + 1;
			end if;
		end if;
	end if;
end if;
end process;

process(clk_internal)
begin
if n_transfer = '0' then
	n_done := '1';
	n_rdy <= '1';
	ss <= '0';
	buffer_tx <= data;
end if;

if n_done = '1' then
	if bit_current <= 31 then
		if cpol = '1' then
			if falling_edge(clk_internal) then
				mosi <= buffer_tx(bit_current);
				buffer_rx(bit_current) <= miso;
			end if;
		else
			if rising_edge(clk_internal) then
				mosi <= buffer_tx(bit_current);
				buffer_rx(bit_current) <= miso;
			end if;
		end if;
		bit_current := bit_current + 1;
	else
		n_done := '0';
		n_rdy <= '0';
		if cont = '0' then
			ss <= '1';
		data <= buffer_rx;
		end if;
	end if;
else
	mosi <= 'Z';
end if;
end process;
end architecture;