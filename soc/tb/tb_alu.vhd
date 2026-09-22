-- ALU-001: exhaustive ALU test. Every op code (all 32 values of opcode bits
-- 7..3) × every a × every b, against a reference written directly from the
-- manual's instruction table.

library ieee;
use ieee.std_logic_1164.all;
use ieee.numeric_std.all;

entity tb_alu is
end entity;

architecture sim of tb_alu is
	signal op: std_logic_vector(4 downto 0);
	signal a, b, r: unsigned(7 downto 0);
	signal z, wr, wz: std_logic;
begin
	dut: entity work.alu port map(op => op, a => a, b => b, r => r, z => z,
								  writes_r => wr, writes_z => wz);

	process
		variable er: integer;		-- expected result, -1 = no register write
		variable ez: integer;		-- expected Z, -1 = Z untouched
		variable ia, ib: integer;
		variable errors: natural := 0;
	begin
		for o in 0 to 31 loop
			for x in 0 to 255 loop
				for y in 0 to 255 loop
					op <= std_logic_vector(to_unsigned(o, 5));
					a <= to_unsigned(x, 8);
					b <= to_unsigned(y, 8);
					wait for 1 ns;
					ia := x; ib := y; er := -1; ez := -1;
					case o * 8 is								-- opcode base, per the manual
						when 16#00# => ez := 1 when ia = ib else 0;	-- EQ
						when 16#08# => ez := 1 when ia > ib else 0;	-- GT
						when 16#10# => ez := 1 when ia < ib else 0;	-- LT
						when 16#18# => er := to_integer(to_unsigned(ia, 8) and to_unsigned(ib, 8));
						when 16#20# => er := to_integer(to_unsigned(ia, 8) or to_unsigned(ib, 8));
						when 16#30# => er := to_integer(to_unsigned(ia, 8) xor to_unsigned(ib, 8));
						when 16#38# => er := to_integer(not (to_unsigned(ia, 8) or to_unsigned(ib, 8)));
						when 16#40# => er := (ia + ib) mod 256;
						when 16#48# => er := (ia - ib + 256) mod 256;
						when 16#60# => er := (ia * 2 ** ib) mod 256 when ib < 8 else 0;
						when 16#68# => er := ia / 2 ** ib when ib < 8 else 0;
						when others => null;
					end case;
					if (er >= 0) /= (wr = '1') or (ez >= 0) /= (wz = '1') or
					   (er >= 0 and to_integer(r) /= er) or
					   (ez >= 0 and (z = '1') /= (ez = 1)) then
						errors := errors + 1;
						if errors <= 20 then
							report "op $" & to_hstring(to_unsigned(o * 8, 8)) & " a=" & integer'image(x) &
								   " b=" & integer'image(y) & ": r=" & integer'image(to_integer(r)) &
								   " z=" & std_logic'image(z) & " wr=" & std_logic'image(wr) &
								   " wz=" & std_logic'image(wz) & ", expected r=" & integer'image(er) &
								   " z=" & integer'image(ez) severity error;
						end if;
					end if;
				end loop;
			end loop;
		end loop;
		assert errors = 0 report integer'image(errors) & " ALU mismatches" severity failure;
		report "ALU-001: 2097152 cases, 0 mismatches";
		std.env.finish;
	end process;
end architecture;
