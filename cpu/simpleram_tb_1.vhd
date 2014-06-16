LIBRARY ieee;
USE ieee.std_logic_1164.ALL;
USE ieee.numeric_std.ALL;

ENTITY simpleram_tb IS
END;

ARCHITECTURE behavior OF simpleram_tb IS 

   signal clk: std_logic := '0';
   constant clk_period : time := 10 ns;
	
    signal en   	 :   std_logic := '0';
    signal we      :   std_logic := '0';
    signal address :   std_logic_vector(15 downto 0) := x"0000";
    signal data    :   std_logic_vector(7 downto 0) := (others=>'Z');

BEGIN

    -- Instantiate the Unit Under Test (UUT)
   uut: entity work.simpleram PORT MAP (
			en => en,
			we => we,
			address => address,
			data => data
        );

   -- Clock process definitions
   clk_process :process
   begin
        clk <= '0';
        wait for clk_period/2;
        clk <= '1';
        wait for clk_period/2;
   end process;
    
   -- Stimulus process
   stim_proc: process
   begin        
      wait for clk_period/4;
			we <= '1';
			en <= '1';
			address <= x"0001";
			data <= x"aa"; wait for clk_period;
			address <= x"1001";
			data <= x"bb"; wait for clk_period;
			en <= '0';
			data <= (others=>'Z');
			we <= '0';wait for clk_period;
			en <= '1';
			address <= x"0001"; wait for clk_period;
			address <= x"1001"; wait for clk_period;
			en <= '0'; wait for clk_period;
      wait;
   end process;

END;