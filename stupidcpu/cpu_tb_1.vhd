LIBRARY ieee;
USE ieee.std_logic_1164.ALL;
USE ieee.numeric_std.ALL;

ENTITY cpu_tb IS
END;

ARCHITECTURE behavior OF cpu_tb IS 

   signal clk: std_logic := '0';
   constant clk_period : time := 10 ns;
	
	signal n_srst: std_logic := '1';

BEGIN

    -- Instantiate the Unit Under Test (UUT)
   uut: entity work.cpu PORT MAP (
			n_srst => n_srst,
         clk => clk
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
			n_srst <= '0'; wait for clk_period;
			n_srst <= '1';
      wait;
   end process;

END;