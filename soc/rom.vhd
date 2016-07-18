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
	type rom_type is array (0 to 127) of std_logic_vector(7 downto 0);
	-- rom code
	constant rom : rom_type :=
	-- rom bootloader
	-- loads 256 bytes to address $1000 and jumps into that vector
	(
--ROMCODE
x"b0", x"03", x"e0", x"8c", x"f9", x"a8", x"0f", x"f1", x"8c", x"03", x"a8", x"00", x"f1", x"aa", x"02", x"f1", 
x"a1", x"03", x"f1", x"05", x"00", x"b8", x"10", x"e0", x"8c", x"00", x"a8", x"00", x"f1", x"a1", x"03", x"f1", 
x"05", x"00", x"b8", x"1d", x"e0", x"a1", x"03", x"f1", x"05", x"00", x"b8", x"25", x"e0", x"8c", x"ff", x"a8", 
x"00", x"f1", x"a0", x"03", x"f1", x"04", x"00", x"b8", x"32", x"e0", x"a0", x"01", x"f1", x"04", x"00", x"b8", 
x"2d", x"e0", x"04", x"ff", x"b8", x"2d", x"e0", x"a8", x"00", x"10", x"8d", x"01", x"8c", x"00", x"aa", x"00", 
x"f1", x"a0", x"03", x"f1", x"04", x"00", x"b8", x"51", x"e0", x"a0", x"01", x"f1", x"92", x"90", x"8a", x"99", 
x"ae", x"00", x"10", x"99", x"45", x"01", x"aa", x"00", x"f0", x"15", x"37", x"b8", x"4c", x"e0", x"8c", x"f8", 
x"a8", x"0f", x"f1", x"a8", x"00", x"f0", x"a0", x"02", x"10", x"a8", x"00", x"f0", x"b0", x"7c", x"e0", x"00"
--ROMCODE




				 );
				
begin
addr_int <= address(11 downto 0);
data <= dataout;

mem_read: process(addr_int) begin
	dataout <= rom(conv_integer(addr_int));
end process;
end architecture behavioural;
