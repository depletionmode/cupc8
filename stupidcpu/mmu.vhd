library ieee;
use ieee.std_logic_1164.all;
use ieee.numeric_std.all;

-- mmu
-- $0000	= $00ff	: interrupt vector table
-- $0100 			: stack
-- $1000 			: reset vector
-- $f000 - $ffff	: i/o

-- ivt
-- 2-byte vector address entries
-- $XX00				: cpu interrupt
-- $XX02				: timer 0
-- $XX04				: timer 1
-- $XX06				: i/o 0
-- $XX08				: i/o 1

-- i/o
-- $f100 - $f10f	: spi 0 (master)
-- $f110 - $f11f	: spi 1 (master)
-- $f120 - $f12f	: spi 2 (master)
-- $f130 - $f13f	: spi 3 (master)

-- spi
-- $XX00		: is bus busy
-- $XX01		: spi enable
-- $XX02		: data out (write clears has data been sent and transmits data)
-- $XX03		: has data been sent
-- $XX04		: data in (read clears is data waiting)
-- $XX05		: is data waiting

entity mmu is
	port(
			addr:		in std_logic_vector(15 downto 0);
			data:		inout std_logic_vector(7 downto 0);
			n_en:		in std_logic;
			n_wr:		in std_logic
		);
end entity;

architecture behavioural of mmu is
begin
process(n_en)
begin
	if(n_en = '0') then
		case n_wr is
			when '1' => -- read
				-- fake stuff!!!
				case addr is
					when x"1001" => data <= "10001100"; -- MOV R0, #1
					when x"1002" => data <= "00000001";
					when x"1003" => data <= "10001101"; -- MOV R1, #3
					when x"1004" => data <= "00000011";
					when x"1005" => data <= "01000100"; -- ADD R0, #1
					when x"1006" => data <= "00000001";
					when x"1007" => data <= "01000101"; -- ADD R1, #1
					when x"1008" => data <= "00000001";
					when x"1009" => data <= "01000001"; -- ADD R1, R0
					when x"100a" => data <= "01000010"; -- ADD R0, R1
					when others =>	data <= "10000000";
				end case; -- end fake stuff!!!
			when '0' => -- write
				NULL;
			when others => NULL;
		end case;
	end if;
end process;
end architecture;