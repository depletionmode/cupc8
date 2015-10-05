
library IEEE;
use IEEE.STD_LOGIC_1164.all;
use ieee.std_logic_unsigned.all;

entity rom is
  port (
    address : in  std_logic_vector(15 downto 0);
    data  : inout  std_logic_vector(7 downto 0)
  );
end entity rom;

architecture behavioural of rom is
	signal dataout : std_logic_vector(7 downto 0);
	signal addr_int : std_logic_vector(11 downto 0);
	type rom_type is array (0 to 9) of std_logic_vector(7 downto 0);
	-- rom code
	constant rom : rom_type :=
            (x"8c", x"00", x"44", x"01", x"a8", x"00", x"f0", x"b0", x"02", x"e0");
begin

addr_int <= address(11 downto 0);
data <= dataout;

mem_read: process(addr_int) begin
	dataout <= rom(conv_integer(addr_int));
end process;
end architecture behavioural;