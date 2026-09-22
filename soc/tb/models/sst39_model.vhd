-- SST39VF040 / SST39VF010 behavioural model (ROM-001..003, BRG-002).
--
-- Reads: tAA = tCE = 70 ns, tOE = 35 ns; data is 'X' until valid.
-- Writes are latched on the rising edge of /WE (or /CE), and must hold
-- tWP ≥ 40 ns and tDS ≥ 40 ns. Command sequences (A14..A0 decoded):
--   program:      5555/AA 2AAA/55 5555/A0 addr/data           busy T_BP
--   sector erase: 5555/AA 2AAA/55 5555/80 5555/AA 2AAA/55 SA/30   busy T_SE (4 KB)
--   chip erase:   5555/AA 2AAA/55 5555/80 5555/AA 2AAA/55 5555/10 busy T_SCE
--   software ID:  5555/AA 2AAA/55 5555/90 → reads: addr 0 = $BF, addr 1 = device ID
--   ID exit:      F0 (single cycle) or 5555/AA 2AAA/55 5555/F0
-- While busy, reads return DQ7 = not(data7) (program) or 0 (erase) and DQ6
-- toggling on each read. Programming can only clear bits (NOR flash).
-- Busy times are generics so tests can shorten them.

library ieee;
use ieee.std_logic_1164.all;
use ieee.numeric_std.all;

entity sst39_model is
	generic(
		DEVICE_ID:	std_logic_vector(7 downto 0) := x"D7";	-- VF040 = D7, VF010 = D5
		ABITS:		natural := 19;							-- VF040 = 19, VF010 = 17
		T_AA:		time := 70 ns;
		T_OE:		time := 35 ns;
		T_WP:		time := 40 ns;
		T_DS:		time := 40 ns;
		T_BP:		time := 20 us;
		T_SE:		time := 25 ms;
		T_SCE:		time := 100 ms;
		PATTERN:	boolean := false		-- start filled with rom_pattern() instead of erased
	);
	port(
		a:		in std_logic_vector(18 downto 0);	-- A18..A17 ignored on the VF010
		d:		inout std_logic_vector(7 downto 0);
		n_ce:	in std_logic;
		n_oe:	in std_logic;
		n_we:	in std_logic;
		violations: out natural := 0
	);
end entity;

architecture behav of sst39_model is
	-- a pattern that differs between banks and offsets (tests compute the same)
	function rom_pattern(i: natural) return std_logic_vector is
	begin
		return std_logic_vector(to_unsigned((i * 7 + i / 2048 * 13 + i / 256) mod 256, 8));
	end function;

	type mem_t is array(0 to 2 ** ABITS - 1) of std_logic_vector(7 downto 0);
	signal viol: natural := 0;
begin
	violations <= viol;

	process(a, d, n_ce, n_oe, n_we)
		variable mem: mem_t := (others => x"FF");
		variable t_addr, t_ce, when_oe, t_we_fall, t_d, busy_until: time := 0 ns;
		variable ready_at: time;
		variable step: natural := 0;		-- position in a command sequence
		variable erase_armed, id_mode: boolean := false;
		variable busy_kind: natural := 0;	-- 1 program, 2 erase
		variable busy_d7: std_logic := '0';
		variable toggle: std_logic := '0';
		variable v: natural := 0;
		variable wa: natural;
		variable wd: std_logic_vector(7 downto 0);
		variable low15: std_logic_vector(14 downto 0);
		variable rv: std_logic_vector(7 downto 0);
		variable ai: natural;
		variable loaded: boolean := false;
	begin
		if not loaded then
			loaded := true;
			if PATTERN then
				for i in mem'range loop mem(i) := rom_pattern(i); end loop;
			end if;
		end if;
		if a'event then
			t_addr := now;
			if n_ce = '0' and n_we = '0' then
				report "SST39: address changed while /WE low" severity error;
				v := v + 1;
			end if;
		end if;
		if n_ce'event and n_ce = '0' then t_ce := now; end if;
		if n_oe'event and n_oe = '0' then when_oe := now; end if;
		if d'event then t_d := now; end if;
		if n_we'event and n_we = '0' then t_we_fall := now; end if;

		-- a bus write cycle ends on /WE rising (or /CE rising with /WE low)
		if (n_we'event and n_we = '1' and n_we'last_value = '0' and n_ce = '0') or
		   (n_ce'event and n_ce = '1' and n_we = '0') then
			if now - t_we_fall < T_WP then
				report "SST39: /WE pulse " & time'image(now - t_we_fall) & " < tWP" severity error;
				v := v + 1;
			end if;
			if now - t_d < T_DS then
				report "SST39: data setup " & time'image(now - t_d) & " < tDS" severity error;
				v := v + 1;
			end if;
			if is_x(a) or is_x(d) then
				report "SST39: write cycle with X address or data" severity error;
				v := v + 1;
				step := 0;
			elsif now < busy_until then
				null;							-- writes while busy are ignored
			else
				wa := to_integer(unsigned(a(ABITS - 1 downto 0)));
				wd := d;
				low15 := a(14 downto 0);
				if wd = x"F0" and step /= 2 then
					id_mode := false;			-- single-cycle exit
					step := 0;
				else
					case step is
						when 0 =>
							if low15 = "101" & x"555" and wd = x"AA" then step := 1; else step := 0; end if;
						when 1 =>
							if low15 = "010" & x"AAA" and wd = x"55" then step := 2; else step := 0; end if;
						when 2 =>
							step := 0;
							if low15 = "101" & x"555" then
								case wd is
									when x"A0" => step := 3;
									when x"80" => erase_armed := true;
									when x"90" => id_mode := true;
									when x"F0" => id_mode := false;
									when x"10" | x"30" =>
										if erase_armed then
											erase_armed := false;
											if wd = x"10" then
												for i in mem'range loop mem(i) := x"FF"; end loop;
												busy_until := now + T_SCE;
												busy_kind := 2;
											end if;
										end if;
									when others => null;
								end case;
							elsif erase_armed and wd = x"30" then
								-- sector erase: 4 KB sector containing the address
								erase_armed := false;
								for i in 0 to 4095 loop
									mem((wa / 4096) * 4096 + i) := x"FF";
								end loop;
								busy_until := now + T_SE;
								busy_kind := 2;
							end if;
						when 3 =>
							mem(wa) := mem(wa) and wd;		-- NOR: program clears bits only
							busy_d7 := not wd(7);
							busy_until := now + T_BP;
							busy_kind := 1;
							step := 0;
						when others => step := 0;
					end case;
				end if;
			end if;
		end if;

		-- read path
		if n_ce = '0' and n_oe = '0' and n_we = '1' then
			if now < busy_until then
				-- status polling: DQ7 and DQ6 (toggles on each /OE falling edge)
				if n_oe'event or n_ce'event then toggle := not toggle; end if;
				if busy_kind = 1 then rv := busy_d7 & toggle & "000000";
				else rv := '0' & toggle & "000000";
				end if;
			elsif is_x(a) then
				rv := (others => 'X');
			else
				ai := to_integer(unsigned(a(ABITS - 1 downto 0)));
				if id_mode and ai mod 2 = 0 then rv := x"BF";
				elsif id_mode then rv := DEVICE_ID;
				else rv := mem(ai);
				end if;
			end if;
			ready_at := maximum(maximum(t_addr + T_AA, t_ce + T_AA), when_oe + T_OE);
			if now >= ready_at then
				d <= transport rv;
			else
				d <= transport (others => 'X');
				d <= transport rv after ready_at - now;
			end if;
		else
			d <= transport (others => 'Z');
		end if;
		viol <= v;
	end process;
end architecture;
