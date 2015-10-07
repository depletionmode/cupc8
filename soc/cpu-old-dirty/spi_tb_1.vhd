LIBRARY ieee;
USE ieee.std_logic_1164.ALL;
USE ieee.numeric_std.ALL;

ENTITY spi_tb IS
END spi_tb;

ARCHITECTURE behavior OF spi_tb IS 
	signal		ss:		std_logic;
	signal		sck:		std_logic;
	signal		mosi:		std_logic := 'Z';
	signal		miso:		std_logic;
			
	signal		clk:			std_logic;
	signal		clk_div:		integer := 1;
	signal		cont:			std_logic := '1'; -- 1 - continue, 0 - last
	signal		cpol:			std_logic := '1';
	signal		cpha:			std_logic := '1';
	signal		tx_data:		std_logic_vector(7 downto 0);
	signal		rx_data:		std_logic_vector(7 downto 0);
	signal		n_rdy:		std_logic := '1';
	signal		n_transfer:	std_logic := '1';

   constant clk_period : time := 5 ns;

BEGIN

    -- Instantiate the Unit Under Test (UUT)
   uut: entity work.spi PORT MAP (
		ss, sck, mosi, miso,
		clk,
		clk_div, cont, cpol, cpha,
		tx_data, rx_data,
		n_rdy, n_transfer
        );

   -- Clock process definitions
   clk_process :process
   begin
        clk <= '0';
        wait for clk_period/2;
        clk <= '1';
        wait for clk_period/2;
   end process;
	
	rx_proc: process
	begin
		wait for clk_period*2;
		miso <= '0';
		wait for clk_period*2;
		miso <= '1';
		wait for clk_period*2;
		miso <= '0';
		wait for clk_period*2;
		miso <= '1';
		wait for clk_period*2;
		miso <= '0';
		wait for clk_period*2;
		miso <= '1';
		wait for clk_period*2;
		miso <= '0';
		wait for clk_period*2;
		miso <= '1';
		wait for clk_period*2;
		miso <= '0';
		wait for clk_period*2;
		miso <= '1';
		wait for clk_period*2;
		miso <= '0';
		wait for clk_period*2;
		miso <= '1';
		wait for clk_period*2;
		miso <= '0';
		wait for clk_period*2;
		miso <= '1';
		wait for clk_period*2;
		miso <= '0';
		wait for clk_period*2;
		miso <= '1';
		wait for clk_period*2;
		miso <= '0';
		wait for clk_period*2;
		miso <= '1';
		wait for clk_period*2;
		miso <= '0';
		wait for clk_period*2;
		miso <= '1';
		wait for clk_period*2;
		miso <= '0';
		wait for clk_period*2;
		miso <= '1';
		wait for clk_period*2;
		miso <= '0';
		wait for clk_period*2;
		miso <= '1';
		wait for clk_period*2;
		miso <= '0';
		wait for clk_period*2;
		miso <= '1';
		wait for clk_period*2;
		miso <= '0';
		wait for clk_period*2;
		miso <= '1';
		wait for clk_period*2;
		miso <= '0';
		wait for clk_period*2;
		miso <= '1';
		wait for clk_period*2;
		miso <= '0';
		wait for clk_period*2;
		miso <= '1';
		wait for clk_period*2;
		miso <= '0';
		wait for clk_period*2;
		miso <= '1';
		wait for clk_period*2;
		miso <= '0';
		wait for clk_period*2;
		miso <= '1';
		wait for clk_period*2;
		miso <= '0';
		wait for clk_period*2;
		miso <= '1';
		wait for clk_period*2;
		miso <= '0';
		wait for clk_period*2;
		miso <= '1';
		wait for clk_period*2;
		miso <= '0';
		wait for clk_period*2;
		miso <= '1';
		wait for clk_period*2;
		miso <= '0';
		wait for clk_period*2;
		miso <= '1';
		wait for clk_period*2;
		miso <= '0';
		wait for clk_period*2;
		miso <= '1';
		wait for clk_period*2;
		miso <= '0';
		wait for clk_period*2;
		miso <= '1';
		wait for clk_period*2;
		miso <= '0';
		wait for clk_period*2;
		miso <= '1';
	end process;
    
   -- Stimulus process
   stim_proc: process
   begin        
      wait for clk_period;
		-- configure
		clk_div <= 1;
		cont <= '0';
		cpol <= '0';
		cpha <= '1';
      wait for clk_period;
		-- send
		tx_data <= "10101010";
      wait for clk_period;
		n_transfer <= '0';
      wait for clk_period * 20;
		n_transfer <= '1';
		tx_data <= "00001111";
		wait for clk_period;
		n_transfer <= '0';
      wait for clk_period * 20;
		n_transfer <= '1';
      wait;
   end process;

END;