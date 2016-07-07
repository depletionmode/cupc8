library ieee;
use ieee.std_logic_1164.all;
use ieee.numeric_std.all;

entity mmu is
	port(
			clk:		in std_logic;
			
			addr:		in std_logic_vector(15 downto 0);
			data:		inout std_logic_vector(7 downto 0);
			n_we:		in std_logic;
			
			spi_ss_n:		out std_logic_vector(3 downto 0);
			spi_sclk:		out std_logic;
			spi_mosi:		out std_logic;
			spi_miso:		in std_logic;

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
		clock   : IN     STD_LOGIC;                             --system clock
		reset_n : IN     STD_LOGIC;                             --asynchronous reset
		enable  : IN     STD_LOGIC;                             --initiate transaction
		cpol    : IN     STD_LOGIC;                             --spi clock polarity
		cpha    : IN     STD_LOGIC;                             --spi clock phase
		cont    : IN     STD_LOGIC;                             --continuous mode command
		clk_div : IN     INTEGER;                               --system clock cycles per 1/2 period of sclk
		addr    : IN     INTEGER;                               --address of slave
		tx_data : IN     STD_LOGIC_VECTOR(8-1 DOWNTO 0);        --data to transmit
		miso    : IN     STD_LOGIC;                             --master in, slave out
		sclk    : BUFFER STD_LOGIC;                             --spi clock
		ss_n    : BUFFER STD_LOGIC_VECTOR(4-1 DOWNTO 0);        --slave select
		mosi    : OUT    STD_LOGIC;                             --master out, slave in
		busy    : OUT    STD_LOGIC;                             --busy / data ready signal
		rx_data : OUT    STD_LOGIC_VECTOR(8-1 DOWNTO 0)         --data received
		);
end component;

type int_array is array(0 to 3) of integer;
signal spi_reset_n:		std_logic := '1';
signal spi_enable:		std_logic;
signal spi_cpol:			std_logic := '1';
signal spi_cpha:			std_logic := '1';
signal spi_cont:			std_logic := '0';
signal spi_clk_div:		integer := 25;
signal spi_addr:			integer;
signal spi_tx_data:		std_logic_vector(7 downto 0);
--signal spi_miso:			std_logic;
--signal spi_sclk:			std_logic;
--signal spi_ss_n:			std_logic_vector(3 downto 0);
--signal spi_mosi:			std_logic;
signal spi_busy:			std_logic;
signal spi_rx_data:		std_logic_vector(7 downto 0);

begin
spi0: spi port map(clk, spi_reset_n, spi_enable, spi_cpol, spi_cpha, spi_cont, spi_clk_div, spi_addr, spi_tx_data, spi_miso, spi_sclk, spi_ss_n, spi_mosi, spi_busy, spi_rx_data);
rom0: rom port map(rom_addr, rom_data);

ram_addr <= addr;
ram_n_we <= n_we;

rom_addr <= addr;

-- spi enable signal for once clock cycle only
process (clk)
variable clk_count: integer range 0 to 50000000 := 0;
begin
   if (rising_edge(clk)) then
		if (spi_enable = '1') then
			--spi_enable <= '0';
		end if;
	end if;
end process;

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
						when x"1" => -- spi
							spi_addr <= to_integer(unsigned(addr(7 downto 4)));	-- device selection
							case addr(3 downto 0) is
								when x"1" =>
									data_out <= spi_rx_data;
								when x"3" => 
									data_out <= "0000000" & not spi_busy; -- '1' when done
								when x"f" =>
									data_out <= "00000000"; -- todo implement config read
								when others => data_out <= "00000000";
							end case;
						when others => data_out <= "00000000";
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
						when x"1" => -- spi
							spi_addr <= to_integer(unsigned(addr(7 downto 4)));
							case addr(3 downto 0) is
								when x"0" =>
									spi_tx_data <= data;
								when x"2" =>
									spi_enable <= '1';
								when x"f" =>
									spi_clk_div <= to_integer(unsigned(data(7 downto 3)));
									spi_cont <= data(0);
									spi_cpol <= data(1);
									spi_cpha <= data(2);
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
