library ieee;
use ieee.std_logic_1164.all;
use ieee.numeric_std.all;

-- spi
-- clk devided by clk_div * 2
-- todo: pll, support for cpha = 1 (currently defaults to cpha = 0)
-- bug: clk_div = 0 is borked
-- bug: cpol = 0 is borked

entity spi is
	port(
			ss:		out std_logic := 'Z';
			sck:		out std_logic;
			mosi:		out std_logic;
			miso:		in std_logic;
			
			clk:			in std_logic;
			clk_div:		in integer := 1;
			cont:			in std_logic := '1'; -- 1 - continue, 0 - last
			cpol:			in std_logic := '1';
			cpha:			in std_logic := '1';
			tx_data:		in std_logic_vector(7 downto 0);
			rx_data:		out std_logic_vector(7 downto 0);
			n_rdy:		out std_logic := '0';
			n_transfer:	in std_logic := '1'
		);
end entity;

architecture behavioural of spi is
signal buffer_tx, buffer_rx:	std_logic_vector(7 downto 0);
signal clk_internal: std_logic := '1';

-- variables
signal n_done: std_logic := '0';
signal bit_current: integer range 0 to 32 := 0;
signal detect_transfer: std_ulogic_vector (1 downto 0) := "00";
signal detect_clk: std_ulogic_vector (1 downto 0) := "00";
begin

sck <= clk when (clk_div = 0) else clk_internal;
--mosi <= buffer_tx(bit_current) when (n_transfer = '0') else 'Z';
--buffer_rx(bit_current) <= miso;

process(clk, clk_internal)
variable clk_counter: integer := 0;
begin
if rising_edge(clk) then
	if clk_counter < clk_div then
		if clk_counter = clk_div - 1 then
			clk_internal <= not clk_internal;
			clk_counter := 0;
		else
			clk_counter := clk_counter + 1;
		end if;
	end if;
end if;
end process;

process(clk, clk_internal, n_transfer)
begin
if rising_edge(clk) then
	detect_transfer(1) <= detect_transfer(0);
	detect_transfer(0) <= n_transfer;
	
	if detect_transfer = "10" then -- falling edge
		bit_current <= 0;
		n_done <= '1';
		n_rdy <= '1';
		ss <= '0';
		buffer_tx <= tx_data;
	end if;
end if;


if rising_edge(clk) then
	detect_clk(1) <= detect_clk(0);
	detect_clk(0) <= clk_internal;
	
	if n_done = '1' then
		if bit_current <= 7 then
			if cpol = '1' then
				if detect_clk = "10" then -- falling edge
					mosi <= buffer_tx(bit_current);
					buffer_rx(bit_current) <= miso;
					bit_current <= bit_current + 1;
				end if;
			else
				if detect_clk = "01" then -- rising edge
					mosi <= buffer_tx(bit_current);
					buffer_rx(bit_current) <= miso;
					bit_current <= bit_current + 1;
				end if;
			end if;
		else
			n_done <= '0';
			n_rdy <= '0';
			if cont = '0' then
				ss <= '1';
			rx_data <= buffer_rx;
			bit_current <= 0;
			end if;
		end if;
	else
		mosi <= 'Z';
	end if;
end if;
end process;
end architecture;