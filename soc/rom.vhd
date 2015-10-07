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
	type rom_type is array (0 to 71) of std_logic_vector(7 downto 0);
	-- rom code
	constant rom : rom_type :=
			-- ram test
            (x"8c", x"00", x"a8", x"00", x"f0", x"8c", x"ff", x"a8", x"00", x"f0",
			 x"8c", x"01",				-- mov r0, #1
			 x"a8", x"00", x"00",		-- st $0000, r0
			 x"8c", x"02",				-- mov r0, #2
			 x"a8", x"00", x"01",		-- st $0001, r0
			 x"8c", x"03",				-- mov r0, #3
			 x"a8", x"00", x"02",		-- st $0002, r0
			 x"8c", x"04",				-- mov r0, #4
			 x"a8", x"00", x"04",		-- st $0004, r0
			 x"8c", x"05",				-- mov r0, #5
			 x"a8", x"00", x"08",		-- st $0008, r0
			 x"30",						-- xor r0, r0
			 x"a8", x"00", x"f0",		-- st $f000, r0		; gpo
			 x"a0", x"00", x"08",		-- ld r0, $0008
			 x"a8", x"00", x"f0",		-- st $f000, r0		; gpo
			 x"a0", x"00", x"04",		-- ld r0, $0004
			 x"a8", x"00", x"f0",		-- st $f000, r0		; gpo
			 x"a0", x"00", x"02",		-- ld r0, $0002
			 x"a8", x"00", x"f0",		-- st $f000, r0		; gpo
			 x"a0", x"00", x"01",		-- ld r0, $0001
			 x"a8", x"00", x"f0",		-- st $f000, r0		; gpo
			 x"a0", x"00", x"00",		-- ld r0, $0000
			 x"a8", x"00", x"f0",		-- st $f000, r0		; gpo
			 x"b0", x"45", x"e0");

			-- i2c test
            --(x"8c", x"00", x"a8", x"00", x"f0", x"8c", x"ff", x"a8", x"00", x"f0",
			-- x"8c", x"a0",				-- mov r0, #0xa0	; device address - write
			-- x"a8", x"00", x"f2",		-- st $f200, r0		; start transaction
			-- x"8c", x"00",				-- mov r0, #0
			-- x"a8", x"0f", x"f2",		-- st $f20f, r0		; write address high
			-- x"a8", x"0f", x"f2",		-- st $f20f, r0		; write address low
			-- x"8c", x"aa",				-- mov r0, #0xaa
			-- x"a8", x"0f", x"f2",		-- st $f20f, r0		; write data
			-- x"a8", x"01", x"f2",		-- st $f200, r0		; end transaction
			-- x"8c", x"a0",				-- mov r0, #0xa0	; device address - write
			-- x"a8", x"00", x"f2",		-- st $f200, r0		; start transaction
			-- x"8c", x"00",				-- mov r0, #0
			-- x"a8", x"0f", x"f2",		-- st $f20f, r0		; write address high
			-- x"a8", x"0f", x"f2",		-- st $f20f, r0		; write address low
			-- x"8c", x"a1",				-- mov r0, #0xa1	; device address - read
			-- x"a8", x"00", x"f2",		-- st $f200, r0		; start transaction
			-- x"8c", x"03",				-- mov r0, #3
			-- x"a0", x"0f", x"f2",		-- ld r0, $f20f		; read data
			-- x"90",						-- push r0
			-- x"a8", x"01", x"f2",		-- st $f200, r0		; end transaction
            -- x"8c", x"00", x"a8", x"00", x"f0", x"98", x"a8", x"00", x"f0",
			-- x"b0", x"3a", x"e0");
				
begin
addr_int <= address(11 downto 0);
data <= dataout;

mem_read: process(addr_int) begin
	dataout <= rom(conv_integer(addr_int));
end process;
end architecture behavioural;
