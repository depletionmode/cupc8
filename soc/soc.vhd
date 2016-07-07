library ieee;
use ieee.std_logic_1164.all;
use ieee.numeric_std.all;

entity soc is
	port(				
			but:			in std_logic;
			clk: 			in std_logic;
			n_hrst:		in std_logic;
			halt:			out std_logic; -- high on catastrophic failure
			
			spi_ss_n:	out std_logic_vector(3 downto 0);
			spi_sclk:	out std_logic;
			spi_mosi:	out std_logic;
			spi_miso:	in std_logic;
			
			gpo:			out std_logic_vector(7 downto 0);
			
			ram_addr:	out std_logic_vector(15 downto 0);
			ram_data:	inout std_logic_vector(7 downto 0);
			ram_n_we:	out std_logic;

			-- testing signals
			seg7_o:		out std_logic_vector(6 downto 0);
			test_spi_ready: out std_logic;
			test_spi_busy: out std_logic
		);
end entity;

architecture behavioural of soc is
component cpu
	port(
			clk: 			in std_logic;
			n_hrst:		in std_logic;
			halt:			out std_logic;
			
			mem_addr:	out std_logic_vector(15 downto 0);
			mem_data:	inout std_logic_vector(7 downto 0);
			mem_n_we:	out std_logic;
			
			-- testing
			seg7_val:	out std_logic_vector(3 downto 0)
		);
end component;
		
signal 	mem_addr:	std_logic_vector(15 downto 0);
signal 	mem_data:	std_logic_vector(7 downto 0);
signal 	mem_n_we:	std_logic := '1';
component mmu
	port(
			clk:		in std_logic;
			
			addr:		in std_logic_vector(15 downto 0);
			data:		inout std_logic_vector(7 downto 0);
			n_we:		in std_logic;
			
			spi_ss_n:		out std_logic_vector(3 downto 0);
			spi_sclk:		out std_logic;
			spi_mosi:		out std_logic;
			spi_miso:		in std_logic;
			
			gpo:		out std_logic_vector(7 downto 0);
			
			ram_addr:		out std_logic_vector(15 downto 0);
			ram_data:		inout std_logic_vector(7 downto 0);
			ram_n_we:		out std_logic;
			
			test_spi_ready: out std_logic;
			test_spi_busy: out std_logic
		);
end component;
		
-- testing
signal but_de: std_logic;
component debounce
	port(
			 clk:        in std_logic;
			 in_n:       in std_logic;
			 out_n:  	out std_logic
	    );
end component;

-- testing
signal	seg7_val:	std_logic_vector(3 downto 0);
component seg7
  port (
			 i_dig:  in std_logic_vector(3 downto 0);
			 o_dig:  out std_logic_vector(6 downto 0)
		  );
end component;

-- testing
signal slow_clk: std_logic := '0';

begin
cpu0: cpu port map(slow_clk, n_hrst, halt, mem_addr, mem_data, mem_n_we, seg7_val);
mmu0: mmu port map(slow_clk, mem_addr, mem_data, mem_n_we, spi_ss_n, spi_sclk, spi_mosi, spi_miso,gpo, ram_addr, ram_data, ram_n_we, test_spi_ready, test_spi_busy);

-- testing
seg0: seg7 port map (seg7_val, seg7_o);
debounce0: debounce port map(clk, but, but_de);

-- testing: slow down clock
process (clk)
variable clk_delay: integer range 0 to 50000000 := 0;
begin
   if (rising_edge(clk)) then
		if (clk_delay < 2000) then
			clk_delay := clk_delay + 1;
			slow_clk <= '0';
		else
			clk_delay := 0;
			slow_clk <= '1';
		end if;
	end if;
end process;
end behavioural;
