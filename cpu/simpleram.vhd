
library IEEE;
use IEEE.STD_LOGIC_1164.all;
use ieee.std_logic_unsigned.all;

entity simpleram is
  port (
    en   : in  std_logic;
    we      : in  std_logic;
    address : in  std_logic_vector(15 downto 0);
    data  : inout  std_logic_vector(7 downto 0)
  );
end entity simpleram;

architecture RTL of simpleram is
   type ram_type is array (integer range <>) of std_logic_vector(7 downto 0);
   signal ram : ram_type(0 to 2**16);
	signal dataout : std_logic_vector(7 downto 0) := x"00";
begin

data <= dataout when (en='1' and we='0') else (others=>'Z');

mem_write: process(address, data, en, we) begin
	if (en='1' and we='1') then
		ram(conv_integer(address(14 downto 0)))  <= data;
	end if;
end process;

mem_read: process(address, en, we, ram, dataout) begin
	if (en='1' and we='0') then
		dataout <= ram(conv_integer(address(14 downto 0)));
	end if;
end process;

end architecture RTL;