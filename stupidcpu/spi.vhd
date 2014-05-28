library ieee;
use ieee.std_logic_1164.all;
use ieee.numeric_std.all;

-- spi
-- support for continuous transmission through mode set
-- data shifted out on rising edge and in on falling edge of sck
entity spi is
	port(
			ss:		out std_logic;
			sck:		out std_logic;
			mosi:		out std_logic;
			miso:		in std_logic;
			
			clk:			in std_logic;
			mode:			in std_logic := '1'; -- 0 - continue, 1 - last
			data:			inout std_logic_vector(7 downto 0);
			n_rdy:		out std_logic := '1';
			n_transfer:	in std_logic := '1'
		);
end entity;

-- todo: pll

architecture behavioural of spi is
variable bit_current: integer range 0 to 32 := 0;
variable n_done: std_logic := '1';
begin
process(clk, sck)
begin
sclk <= clk;

if rising_edge(n_transfer) then
	n_done := '1';
	n_rdy <= '1';
	ss <= '0';
end if;

if n_done = '1' then
	if bit_current <= 31 then
		if rising_edge(sck) then
			mosi <= data(bit_current);
		else
			data(bit_current) <= miso;
		end if;
		bit_current := bit_current + 1;
	else
		n_done := '0';
		n_rdy <= '0';
		if mode = '1' then
			ss <= '1';
		end if;
	end if;
end if;
end process;
end architecture;