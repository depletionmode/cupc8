LIBRARY ieee;
USE ieee.std_logic_1164.ALL;
USE ieee.numeric_std.ALL;

ENTITY tb IS
END tb;

ARCHITECTURE behavior OF tb IS 

   signal clk: std_logic := '0';
   signal a,b,r: unsigned(7 downto 0) := (others => '0');
   signal op: std_logic_vector(3 downto 0) := (others => '0');
	signal zf: bit := '0';
   constant clk_period : time := 10 ns;

BEGIN

    -- Instantiate the Unit Under Test (UUT)
   uut: entity work.alu PORT MAP (
          n_en => clk,
          a => a,
          b => b,
          op => op,
          r => r,
			 zf => zf
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
      wait for clk_period*1;
        a <= "00000000"; --18 in decimal
        b <= "00000000"; --10 in decimal
        op <= "0000";  wait for clk_period;
        a <= "00010010"; --18 in decimal
        b <= "00001010"; --10 in decimal
        op <= "0000";  wait for clk_period;
        op <= "0001";  wait for clk_period;
        op <= "0010";  wait for clk_period;
        op <= "0011";  wait for clk_period;
        op <= "0100";  wait for clk_period;
        op <= "0101";  wait for clk_period;
        op <= "1001";  wait for clk_period;
        op <= "1010";  wait for clk_period;
        op <= "1011";  wait for clk_period;
        op <= "1100";  wait for clk_period;
        op <= "1101";  wait for clk_period;
        op <= "1110";  wait for clk_period;
        op <= "1111";  wait for clk_period;
        a <= "11111111";
        op <= "1110";  wait for clk_period;
        a <= "00000000";
        op <= "1111";  wait for clk_period;
      wait;
   end process;

END;