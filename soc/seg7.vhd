library ieee;
use ieee.std_logic_1164.all;

entity seg7 is
    port(
            i_dig:  in std_logic_vector(3 downto 0);
            o_dig:  out std_logic_vector(6 downto 0)
        );
end seg7;

architecture led_segment of seg7 is
begin
    process(i_dig)
    begin
        case i_dig is
            when "0000" => o_dig <= "1000000";
            when "0001" => o_dig <= "1111001";
            when "0010" => o_dig <= "0100100";
            when "0011" => o_dig <= "0110000";
            when "0100" => o_dig <= "0011001";
            when "0101" => o_dig <= "0010010";
            when "0110" => o_dig <= "0000010";
            when "0111" => o_dig <= "1111000";
            when "1000" => o_dig <= "0000000";
            when "1001" => o_dig <= "0011000";
            when "1010" => o_dig <= "0001000";
            when "1011" => o_dig <= "0000011";
            when "1100" => o_dig <= "1000110";
            when "1101" => o_dig <= "0100001";
            when "1110" => o_dig <= "0000110";
            when "1111" => o_dig <= "0001110";
				when others => o_dig <= "1111111";
        end case;
    end process;
end architecture led_segment;
