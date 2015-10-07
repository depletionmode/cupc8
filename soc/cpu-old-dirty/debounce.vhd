library ieee;
use ieee.std_logic_1164.all;

entity DEBOUNCE is
    port (
            clk:        in std_logic;
            in_n:       in std_logic;
            out_n:      out std_logic
          );
end DEBOUNCE;

architecture behavioural of DEBOUNCE is
begin
    process(clk)
        variable cnt : integer := 0;
    begin
        if (falling_edge(clk)) then
            if (in_n = '0') then
                out_n <= '1';
                cnt := 100000;
            else
                if (cnt = 1) then
                    out_n <= '0';
                else
                    out_n <= '1';
                end if;
                if (cnt > 0) then
                    cnt := cnt - 1;
                end if;
            end if;
        end if;
    end process;
end architecture behavioural;