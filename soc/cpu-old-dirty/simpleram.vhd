
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
   signal ram : ram_type(0 to 2**2);
	signal dataout : std_logic_vector(7 downto 0) := x"00";
	signal addr_int : std_logic_vector(1 downto 0);
begin

addr_int <= address(1 downto 0);
data <= dataout when (en='1' and we='0') else (others=>'Z');

mem_write: process(data, en, we, addr_int) begin
	if (en='1' and we='1') then
		ram(conv_integer(addr_int)) <= data;
	end if;
end process;

mem_read: process(en, we, ram, addr_int) begin
	if (en='1' and we='0') then
		dataout <= ram(conv_integer(addr_int));
	end if;
end process;

end architecture RTL;