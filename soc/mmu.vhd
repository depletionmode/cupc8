library ieee;
use ieee.std_logic_1164.all;
use ieee.numeric_std.all;

entity mmu is
	port(
			clk:		in std_logic;
			
			addr:		in std_logic_vector(15 downto 0);
			data:		inout std_logic_vector(7 downto 0);
			n_we:		in std_logic;
			
			spi_ss:			out std_logic_vector(3 downto 0);
			spi_sck:			out std_logic;
			spi_mosi:		out std_logic;
			spi_miso:		in std_logic;
			
			i2c_tx_data	: out std_logic_vector(7 downto 0);
			i2c_rx_data : in std_logic_vector(7 downto 0);

			i2c_go		: out std_logic;
			i2c_stop	: out std_logic;

			gpo:		out std_logic_vector(7 downto 0) := x"00";
			
			ram_addr:		out std_logic_vector(15 downto 0);
			ram_data:		inout std_logic_vector(7 downto 0);
			ram_n_we:		out std_logic
		);
end entity;

architecture behavioural of mmu is
signal	data_out: std_logic_vector(7 downto 0) := x"00";

signal gpo_int: std_logic_vector(7 downto 0) := x"00";

component rom is
  port (
    address : in  std_logic_vector;
    data  : inout  std_logic_vector
  );
end component;
signal rom_addr:  std_logic_vector(15 downto 0);
signal rom_data: std_logic_vector(7 downto 0);

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

-- spi output mux
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
signal	mux_x0:		std_logic_vector(9 downto 0);
signal	mux_x1:		std_logic_vector(9 downto 0);
signal	mux_x2:		std_logic_vector(9 downto 0);
signal	mux_x3:		std_logic_vector(9 downto 0);
signal	mux_out:		std_logic_vector(9 downto 0);
signal 	mux_s:		std_logic_vector(1 downto 0);

begin
--mux0: mux4x10 port map(mux_x0, mux_x1, mux_x2, mux_x3, mux_out, mux_s);
spi0: spi port map(spi_ss(0), mux_x0(9), spi_mosi, spi_miso, clk, spi_clk_div(0), spi_cont(0), spi_cpol(0), spi_cpha(0), spi_tx_data, mux_x0(7 downto 0), mux_x0(8), spi_transfer(0));
spi1: spi port map(spi_ss(1), mux_x1(9), spi_mosi, spi_miso, clk, spi_clk_div(1), spi_cont(1), spi_cpol(1), spi_cpha(1), spi_tx_data, mux_x1(7 downto 0), mux_x1(8), spi_transfer(1));
spi2: spi port map(spi_ss(2), mux_x2(9), spi_mosi, spi_miso, clk, spi_clk_div(2), spi_cont(2), spi_cpol(2), spi_cpha(2), spi_tx_data, mux_x2(7 downto 0), mux_x2(8), spi_transfer(2));
spi3: spi port map(spi_ss(3), mux_x3(9), spi_mosi, spi_miso, clk, spi_clk_div(3), spi_cont(3), spi_cpol(3), spi_cpha(3), spi_tx_data, mux_x3(7 downto 0), mux_x3(8), spi_transfer(3));
spi_sck <= mux_out(9);

rom0: rom port map(rom_addr, rom_data);

ram_addr <= addr;
ram_n_we <= n_we;

rom_addr <= addr;

process(clk, ram_data, data, addr)
begin
   if falling_edge(clk) then
		if n_we = '1' then
			-- read
			--ram_n_we <= '1';
			ram_data <= (others=>'Z');
			case addr(15 downto 12) is
				when x"e" => -- on-fpga rom read
				   data <= rom_data;
				when x"f" => -- i/o
					case addr(11 downto 8) is
						when x"2" => -- i2c
							case addr(3 downto 0) is
								when x"f" => -- read
									i2c_stop <= '0';
									i2c_go <= '1';
									data <= i2c_rx_data;
								when others => NULL;
							end case;
						when others => NULL;
					end case;
				when others => data <= ram_data; -- read from ram
			end case;
		else
			--ram_n_we <= '0';
			-- write
			data <= (others=>'Z');
			case addr(15 downto 12) is
				when x"f" => -- i/o
					case addr(11 downto 8) is
						when x"0" => -- gpo
							gpo <= data;
						when x"2" => -- i2c
							i2c_tx_data <= data;
							case addr(3 downto 0) is
								when x"0" => -- start transaction by providing device address
									i2c_stop <= '0';
									i2c_go <= '1';
								when x"1" => -- end transaction
									i2c_go <= '0';
									i2c_stop <= '1';
								when x"f" => -- write
									i2c_go <= '1';
									i2c_stop <= '0';
								when others => NULL;
							end case;
						when others => NULL;
					end case;
				when others =>
					ram_data <= data;
			end case;
		end if;
	end if;
end process;

--ram_en <= not n_en;
--ram_addr <= addr;
--ram_n_we <= '1' when (n_en = '0' and n_we = '0') else '0';
--ram_data <= data when (n_en = '0' and n_we = '0') else (others=>'Z');
--gpo <= addr(7 downto 0);
--
--read : process(n_en, n_we, addr, ram_data) begin
--	if n_we = '1' and n_en='0' then
--		case addr(15 downto 12) is
--			when x"1" => -- fake stuff!!!
--				case addr(11 downto 0) is
--					-- branch tight loop
----					when x"000" => data_out <= x"b0"; -- B $0x1000
----					when x"001" => data_out <= x"00";
----					when x"002" => data_out <= x"10";
--
--					-- stack test
----					when x"000" => data_out <= x"b0";
----					when x"001" => data_out <= x"03";
----					when x"002" => data_out <= x"10";
----					when x"003" => data_out <= x"94";
----					when x"004" => data_out <= x"ff";
----					when x"005" => data_out <= x"98";
----					when x"006" => data_out <= x"94";
----					when x"007" => data_out <= x"0a";
----					when x"008" => data_out <= x"99";
----					when x"009" => data_out <= x"8c";
----					when x"00a" => data_out <= x"60";
----					when x"00b" => data_out <= x"8d";
----					when x"00c" => data_out <= x"0f";
----					when x"00d" => data_out <= x"90";
----					when x"00e" => data_out <= x"92";
----					when x"00f" => data_out <= x"80";
----					when x"010" => data_out <= x"98";
----					when x"011" => data_out <= x"99";
--					
--					-- branch not equal loop
----					when x"000" => data_out <= x"8c"; -- MOV R0, #3
----					when x"001" => data_out <= x"03";
----					when x"002" => data_out <= x"8d"; -- MOV R1, #3
----					when x"003" => data_out <= x"03";
----					when x"004" => data_out <= x"00"; -- EQ R0, R1
----					when x"005" => data_out <= x"b8"; -- BNE $0x1000
----					when x"006" => data_out <= x"00";
----					when x"007" => data_out <= x"10";					
--					
--					-- some ALU tests
----					when x"000" => data_out <= x"b0";
----					when x"001" => data_out <= x"03";
----					when x"002" => data_out <= x"10";
----					when x"003" => data_out <= x"8c";
----					when x"004" => data_out <= x"14";
----					when x"005" => data_out <= x"8d";
----					when x"006" => data_out <= x"1e";
----					when x"007" => data_out <= x"32";
----					when x"008" => data_out <= x"31";
----					when x"009" => data_out <= x"30";
----					when x"00a" => data_out <= x"33";
----					when x"00b" => data_out <= x"44";
----					when x"00c" => data_out <= x"01";
----					when x"00d" => data_out <= x"45";
----					when x"00e" => data_out <= x"02";
----					when x"00f" => data_out <= x"42";
--					
--					-- mem test
----					when x"000" => data_out <= x"b0";
----					when x"001" => data_out <= x"03";
----					when x"002" => data_out <= x"10";
----					when x"003" => data_out <= x"8c";
----					when x"004" => data_out <= x"aa";
----					when x"005" => data_out <= x"a8";
----					when x"006" => data_out <= x"00";
----					when x"007" => data_out <= x"20";
----					when x"008" => data_out <= x"30";
----					when x"009" => data_out <= x"a0";
----					when x"00a" => data_out <= x"00";
----					when x"00b" => data_out <= x"20";
--
--					-- pc push test
----					when x"000" => data_out <= x"b0";
----					when x"001" => data_out <= x"05";
----					when x"002" => data_out <= x"10";
----					when x"003" => data_out <= x"9e";
----					when x"004" => data_out <= x"9f";
----					when x"005" => data_out <= x"96";
----					when x"006" => data_out <= x"97";
----					when x"007" => data_out <= x"b0";
----					when x"008" => data_out <= x"03";
----					when x"009" => data_out <= x"10";
----					when x"00a" => data_out <= x"8c";
----					when x"00b" => data_out <= x"ff";
--					
--					-- spi test
----					when x"000" => data_out <= x"b0";
----					when x"001" => data_out <= x"03";
----					when x"002" => data_out <= x"10";
----					when x"003" => data_out <= x"30";
----					when x"004" => data_out <= x"33";
----					when x"005" => data_out <= x"8c";
----					when x"006" => data_out <= x"0c";
----					when x"007" => data_out <= x"a8";
----					when x"008" => data_out <= x"0f";
----					when x"009" => data_out <= x"f1";
----					when x"00a" => data_out <= x"8c";
----					when x"00b" => data_out <= x"c7";
----					when x"00c" => data_out <= x"a8";
----					when x"00d" => data_out <= x"00";
----					when x"00e" => data_out <= x"f1";
----					when x"00f" => data_out <= x"8d";
----					when x"010" => data_out <= x"01";
----					when x"011" => data_out <= x"a8";
----					when x"012" => data_out <= x"02";
----					when x"013" => data_out <= x"f1";
----					when x"014" => data_out <= x"45";
----					when x"015" => data_out <= x"01";
----					when x"016" => data_out <= x"a0";
----					when x"017" => data_out <= x"03";
----					when x"018" => data_out <= x"f1";
----					when x"019" => data_out <= x"04";
----					when x"01a" => data_out <= x"01";
----					when x"01b" => data_out <= x"b8";
----					when x"01c" => data_out <= x"14";
----					when x"01d" => data_out <= x"10";
----					when x"01e" => data_out <= x"8c";
----					when x"01f" => data_out <= x"ff";
--					
--					-- gpo test
--					when x"000" => data_out <= x"80";
--					when x"001" => data_out <= x"8c";
--					when x"002" => data_out <= x"aa";
--					when x"003" => data_out <= x"a8";
--					when x"004" => data_out <= x"00";
--					when x"005" => data_out <= x"f0";
--										
--					when others =>	data_out <= "10000000"; -- nops
--				end case;
--			
--			when x"f" => -- i/o
--				case addr(11 downto 8) is
--					when x"1" => -- spi
--						spi_device := to_integer(unsigned(addr(7 downto 4)));
--						case addr(3 downto 0) is
--							when x"1" =>
--								data_out <= mux_out(7 downto 0);
--								--spi_transfer(spi_device) <= '1';
--							when x"3" => 
--								data_out <= "0000000" & not mux_out(8); -- '1' when done
--							when x"f" => data_out <= "00000000"; -- todo implement config read
--							when others => data_out <= "00000000";
--						end case;
--					when others => data_out <= "00000000";
--				end case;
--			when others => data_out <= x"ff";--ram_data; -- read from ram
--		end case;
--	end if;
--end process;
--
--gpo_int <= gpo_int when n_we = '1' or n_en ='1';
--gpo <= gpo_int;
--write : process(n_en, n_we) 
--variable set: bit :='0';
--begin
--
--	if n_we = '0' and n_en='0' then
--		case addr(15 downto 12) is
--			when x"f" => -- i/o
--				case addr(11 downto 8) is
--					when x"0" => -- gpo
--						--if set ='0' then
--							--gpo_int <= x"0f";
--							gpo_int <= data;
--							--set := '1';
--						--end if;
----					when x"1" => -- spi
----						spi_device := to_integer(unsigned(addr(7 downto 4)));
----						case addr(3 downto 0) is
----							when x"0" =>
----								spi_tx_data <= data;
----								spi_transfer(spi_device) <= '1';
----							when x"2" =>
----								mux_s <= std_logic_vector(to_unsigned(spi_device, mux_s'length)); 
----								spi_transfer(spi_device) <= '0'; -- active low
----							when x"f" =>
----								spi_clk_div(spi_device) <= to_integer(unsigned(data(7 downto 3)));
----								spi_cont(spi_device) <= data(0);
----								spi_cpol(spi_device) <= data(1);
----								spi_cpha(spi_device) <= data(2);
----							when others => NULL;
----						end case;
--					when others =>
--						gpo_int <= gpo_int;
--				end case;
--			when others =>
--				gpo_int <=  gpo_int;
--		end case;
--	end if;
--end process;

end architecture;
