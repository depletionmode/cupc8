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
-- $XXX0	: tx_data
-- $XXX1 : rx_data
-- $XXX2 : transact
-- #XXX3 : ready
-- $XXXf : config 00000000
--                |   ||||
--                 --- || - continuous
--                  |  | -- cpol
--                  |   --- cpha
--                   ------ clk_div

entity mmu is
	port(
			clk:		in std_logic;
			
			addr:		in std_logic_vector(15 downto 0);
			data:		inout std_logic_vector(7 downto 0);
			n_en:		in std_logic;
			n_wr:		in std_logic;
			
			spi_ss:			out std_logic_vector(3 downto 0);
			spi_sck:			out std_logic;
			spi_mosi:		out std_logic;
			spi_miso:		in std_logic
		);
end entity;
architecture behavioural of mmu is
-- simple internal ram for testing/stack?
signal	ram_en:			std_logic;-- := '1';
signal	ram_we:			std_logic;
signal 	ram_addr:		std_logic_vector(15 downto 0);
signal	ram_data:		std_logic_vector(7 downto 0);
component simpleram is
  port (
    en   	: in  std_logic;
    we      : in  std_logic;
    address : in  std_logic_vector;
    data  : inout  std_logic_vector
  );
end component;

-- spi output mux
signal	mux_x0:		std_logic_vector(9 downto 0);
signal	mux_x1:		std_logic_vector(9 downto 0);
signal	mux_x2:		std_logic_vector(9 downto 0);
signal	mux_x3:		std_logic_vector(9 downto 0);
signal	mux_out:		std_logic_vector(9 downto 0);
signal 	mux_s:		std_logic_vector(1 downto 0);
component mux4x10
	port(
			x0:		in std_logic_vector(9 downto 0);
			x1:		in std_logic_vector(9 downto 0);
			x2:		in std_logic_vector(9 downto 0);
			x3:		in std_logic_vector(9 downto 0);
			f:			out std_logic_vector(9 downto 0);
			sel:		std_logic_vector(1 downto 0)
		);
end component;

signal			data_out: std_logic_vector(7 downto 0);

-- spi
type int_array is array(0 to 3) of integer;
--signal			spi_clk:			std_logic;
signal			spi_clk_div:	int_array;
signal			spi_cont:		std_logic_vector(3 downto 0);
signal			spi_cpol:		std_logic_vector(3 downto 0);
signal			spi_cpha:		std_logic_vector(3 downto 0);
signal			spi_tx_data:	std_logic_vector(7 downto 0);
--signal			spi_rx_data:	std_logic_vector(7 downto 0);
--signal			spi_rdy:			std_logic;
signal			spi_transfer:	std_logic_vector(3 downto 0);
shared variable spi_device: integer;
component spi
	port(
			ss:		out std_logic;
			sck:		out std_logic;
			mosi:		out std_logic;
			miso:		in std_logic;
			
			clk:			in std_logic;
			clk_div:		in integer;
			cont:			in std_logic;
			cpol:			in std_logic;
			cpha:			in std_logic;
			tx_data:		in std_logic_vector(7 downto 0);
			rx_data:		out std_logic_vector(7 downto 0);
			n_rdy:		out std_logic;
			n_transfer:	in std_logic
		);
end component;	
begin
--mux0: mux4x10 port map(mux_x0, mux_x1, mux_x2, mux_x3, mux_out, mux_s);
spi0: spi port map(spi_ss(0), mux_x0(9), spi_mosi, spi_miso, clk, spi_clk_div(0), spi_cont(0), spi_cpol(0), spi_cpha(0), spi_tx_data, mux_x0(7 downto 0), mux_x0(8), spi_transfer(0));
spi1: spi port map(spi_ss(1), mux_x1(9), spi_mosi, spi_miso, clk, spi_clk_div(1), spi_cont(1), spi_cpol(1), spi_cpha(1), spi_tx_data, mux_x1(7 downto 0), mux_x1(8), spi_transfer(1));
spi2: spi port map(spi_ss(2), mux_x2(9), spi_mosi, spi_miso, clk, spi_clk_div(2), spi_cont(2), spi_cpol(2), spi_cpha(2), spi_tx_data, mux_x2(7 downto 0), mux_x2(8), spi_transfer(2));
spi3: spi port map(spi_ss(3), mux_x3(9), spi_mosi, spi_miso, clk, spi_clk_div(3), spi_cont(3), spi_cpol(3), spi_cpha(3), spi_tx_data, mux_x3(7 downto 0), mux_x3(8), spi_transfer(3));

ram0: simpleram port map(ram_en, ram_we, ram_addr, ram_data);

spi_sck <= mux_out(9);

data <= data_out when (n_en = '0' and n_wr = '1') else (others=>'Z');

ram_en <= not n_en;
ram_addr <= addr;
ram_we <= '1' when (n_en = '0' and n_wr = '0') else '0';
ram_data <= data when (n_en = '0' and n_wr = '0') else (others=>'Z');

read : process(n_en, n_wr, addr, ram_data) begin
	if n_wr = '1' and n_en='0' then
		case addr(15 downto 12) is
			when x"1" => -- fake stuff!!!
				case addr(11 downto 0) is
					
					-- branch tight loop
--					when x"000" => data_out <= x"b0"; -- B $0x1000
--					when x"001" => data_out <= x"00";
--					when x"002" => data_out <= x"10";

					-- stack test
--					when x"000" => data_out <= x"b0";
--					when x"001" => data_out <= x"03";
--					when x"002" => data_out <= x"10";
--					when x"003" => data_out <= x"94";
--					when x"004" => data_out <= x"ff";
--					when x"005" => data_out <= x"98";
--					when x"006" => data_out <= x"94";
--					when x"007" => data_out <= x"0a";
--					when x"008" => data_out <= x"99";
--					when x"009" => data_out <= x"8c";
--					when x"00a" => data_out <= x"60";
--					when x"00b" => data_out <= x"8d";
--					when x"00c" => data_out <= x"0f";
--					when x"00d" => data_out <= x"90";
--					when x"00e" => data_out <= x"92";
--					when x"00f" => data_out <= x"80";
--					when x"010" => data_out <= x"98";
--					when x"011" => data_out <= x"99";
					
					-- branch not equal loop
--					when x"000" => data_out <= x"8c"; -- MOV R0, #3
--					when x"001" => data_out <= x"03";
--					when x"002" => data_out <= x"8d"; -- MOV R1, #3
--					when x"003" => data_out <= x"03";
--					when x"004" => data_out <= x"00"; -- EQ R0, R1
--					when x"005" => data_out <= x"b8"; -- BNE $0x1000
--					when x"006" => data_out <= x"00";
--					when x"007" => data_out <= x"10";					
					
					-- some ALU tests
--					when x"000" => data_out <= x"b0";
--					when x"001" => data_out <= x"03";
--					when x"002" => data_out <= x"10";
--					when x"003" => data_out <= x"8c";
--					when x"004" => data_out <= x"14";
--					when x"005" => data_out <= x"8d";
--					when x"006" => data_out <= x"1e";
--					when x"007" => data_out <= x"32";
--					when x"008" => data_out <= x"31";
--					when x"009" => data_out <= x"30";
--					when x"00a" => data_out <= x"33";
--					when x"00b" => data_out <= x"44";
--					when x"00c" => data_out <= x"01";
--					when x"00d" => data_out <= x"45";
--					when x"00e" => data_out <= x"02";
--					when x"00f" => data_out <= x"42";
					
					-- mem test
--					when x"000" => data_out <= x"b0";
--					when x"001" => data_out <= x"03";
--					when x"002" => data_out <= x"10";
--					when x"003" => data_out <= x"8c";
--					when x"004" => data_out <= x"aa";
--					when x"005" => data_out <= x"a8";
--					when x"006" => data_out <= x"00";
--					when x"007" => data_out <= x"20";
--					when x"008" => data_out <= x"30";
--					when x"009" => data_out <= x"a0";
--					when x"00a" => data_out <= x"00";
--					when x"00b" => data_out <= x"20";

					-- call test
					when x"000" => data_out <= x"b0";
					when x"001" => data_out <= x"07";
					when x"002" => data_out <= x"10";
					when x"003" => data_out <= x"80";
					when x"004" => data_out <= x"c0";
					when x"005" => data_out <= x"03";
					when x"006" => data_out <= x"10";
					when x"007" => data_out <= x"c0";
					when x"008" => data_out <= x"04";
					when x"009" => data_out <= x"10";
										
					when others =>	data_out <= "10000000";
				end case;
			
			when x"f" => -- i/o
				case addr(11 downto 8) is
					when x"1" => -- spi
						spi_device := to_integer(unsigned(addr(7 downto 4)));
						case addr(3 downto 0) is
							when x"1" =>
								data_out <= mux_out(7 downto 0);
								--spi_transfer(spi_device) <= '1';
							when x"3" =>
								data_out <= "0000000" & not mux_out(8); -- '1' when done
							when x"f" => NULL; -- todo implement config read
							when others => NULL;
						end case;
					when others => data_out <= "00000000";
				end case;
			when others => data_out <= ram_data; -- read from ram
		end case;
	end if;
end process;


write : process(n_en, n_wr, addr, data) begin
	if n_wr = '0' and n_en='0' then
		case addr(15 downto 12) is
			when x"f" => -- i/o
				case addr(11 downto 8) is
					when x"1" => -- spi
						spi_device := to_integer(unsigned(addr(7 downto 4)));
						case addr(3 downto 0) is
							when x"0" =>
								spi_tx_data <= data;
								spi_transfer(spi_device) <= '1';
							when x"2" =>
								mux_s <= std_logic_vector(to_unsigned(spi_device, mux_s'length)); 
								spi_transfer(spi_device) <= '0'; -- active low
							when x"f" =>
								spi_clk_div(spi_device) <= to_integer(unsigned(data(7 downto 3)));
								spi_cont(spi_device) <= data(0);
								spi_cpol(spi_device) <= data(1);
								spi_cpha(spi_device) <= data(2);
							when others => NULL;
						end case;
					when others => NULL;
				end case;
			when others => NULL;
		end case;
	end if;
end process;

end architecture;

--
--entity mmu is
--	port(
--			addr:		in std_logic_vector(15 downto 0);
--			data:		inout std_logic_vector(7 downto 0);
--			n_en:		in std_logic;
--			n_wr:		in std_logic
--		);
--end entity;
--
--
--architecture behavioural of mmu is
--begin
--process(n_en)
--begin
--	if(n_en = '0') then
--		case n_wr is
--			when '1' => -- read
--				-- fake stuff!!!
--				case addr is
--					when x"1001" => data <= "10001100"; -- MOV R0, #1
--					when x"1002" => data <= "00000001";
--					when x"1003" => data <= "10001101"; -- MOV R1, #3
--					when x"1004" => data <= "00000011";
--					when x"1005" => data <= "01000100"; -- ADD R0, #1
--					when x"1006" => data <= "00000001";
--					when x"1007" => data <= "01000101"; -- ADD R1, #1
--					when x"1008" => data <= "00000001";
--					when x"1009" => data <= "01000001"; -- ADD R1, R0
--					when x"100a" => data <= "01000010"; -- ADD R0, R1
--					when others =>	data <= "10000000"; -- NOP
--				end case; -- end fake stuff!!!
--			when '0' => -- write
--				NULL;
--			when others => NULL;
--		end case;
--	end if;
--end process;
--end architecture;
