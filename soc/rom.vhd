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
	type rom_type is array (0 to 69) of std_logic_vector(7 downto 0);
	-- rom code
	constant rom : rom_type :=
            --(x"8d", x"01", x"30", x"42", x"a8", x"00", x"f0", x"b0", x"03", x"e0");
            (x"8c", x"00", x"a8", x"00", x"f0", x"8c", x"ff", x"a8", x"00", x"f0",
			 x"8c", x"a0",				-- mov r0, #0xa0	; device address - write
			 x"a8", x"00", x"f2",		-- st $f200, r0		; start transaction
			 x"8c", x"00",				-- mov r0, #0
			 x"a8", x"0f", x"f2",		-- st $f20f, r0		; write address high
			 x"a8", x"0f", x"f2",		-- st $f20f, r0		; write address low
			 x"8c", x"aa",				-- mov r0, #0xaa
			 x"a8", x"0f", x"f2",		-- st $f20f, r0		; write data
			 x"a8", x"01", x"f2",		-- st $f200, r0		; end transaction
			 x"8c", x"a0",				-- mov r0, #0xa0	; device address - write
			 x"a8", x"00", x"f2",		-- st $f200, r0		; start transaction
			 x"8c", x"00",				-- mov r0, #0
			 x"a8", x"0f", x"f2",		-- st $f20f, r0		; write address high
			 x"a8", x"0f", x"f2",		-- st $f20f, r0		; write address low
			 x"8c", x"a1",				-- mov r0, #0xa1	; device address - read
			 x"a8", x"00", x"f2",		-- st $f200, r0		; start transaction
			 x"8c", x"03",				-- mov r0, #3
			 x"a0", x"0f", x"f2",		-- ld r0, $f20f		; read data
			 x"90",						-- push r0
			 x"a8", x"01", x"f2",		-- st $f200, r0		; end transaction
             x"8c", x"00", x"a8", x"00", x"f0", x"98", x"a8", x"00", x"f0",
			 x"b0", x"3a", x"e0");
				
begin
addr_int <= address(11 downto 0);
data <= dataout;

mem_read: process(addr_int) begin
	dataout <= rom(conv_integer(addr_int));
end process;
end architecture behavioural;
