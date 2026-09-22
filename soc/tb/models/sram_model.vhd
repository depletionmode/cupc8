-- IS62WV5128EBLL-45 behavioural model with timing checks (MMU-002).
-- Datasheet (45 ns grade): tAA = 45, tACE = 45, tDOE = 20, tWP = 35,
-- tSD (data setup to /WE high) = 25, tHD = 0, tAW = 35.
-- Reads drive 'X' until the data is valid, so a controller that samples too
-- early reads X and the test fails. Timing violations are reported as errors
-- and counted in `violations`.

library ieee;
use ieee.std_logic_1164.all;
use ieee.numeric_std.all;

entity sram_model is
	generic(
		T_AA:	time := 45 ns;
		T_OE:	time := 20 ns;
		T_WP:	time := 35 ns;
		T_DS:	time := 25 ns;
		ABITS:	natural := 19
	);
	port(
		a:		in std_logic_vector(ABITS - 1 downto 0);
		d:		inout std_logic_vector(7 downto 0);
		n_ce:	in std_logic;
		n_oe:	in std_logic;
		n_we:	in std_logic;
		violations: out natural := 0
	);
end entity;

architecture behav of sram_model is
	type mem_t is array(0 to 2 ** ABITS - 1) of std_logic_vector(7 downto 0);
	signal viol: natural := 0;
begin
	violations <= viol;

	process(a, d, n_ce, n_oe, n_we)
		variable mem: mem_t := (others => x"00");
		variable t_addr, t_ce, when_oe, t_we_fall, t_d: time := 0 ns;
		variable ready_at: time;
		variable v: natural := 0;
	begin
		if a'event then
			t_addr := now;
			if n_ce = '0' and n_we = '0' then
				report "SRAM: address changed while /WE low" severity error;
				v := v + 1;
			end if;
		end if;
		if n_ce'event and n_ce = '0' then t_ce := now; end if;
		if n_oe'event and n_oe = '0' then when_oe := now; end if;
		if d'event then t_d := now; end if;
		if n_we'event and n_we = '0' then t_we_fall := now; end if;

		-- write completes on /WE rising (or /CE rising while /WE is low)
		if (n_we'event and n_we = '1' and n_we'last_value = '0' and n_ce = '0') or
		   (n_ce'event and n_ce = '1' and n_we = '0') then
			if now - t_we_fall < T_WP then
				report "SRAM: /WE pulse " & time'image(now - t_we_fall) & " < tWP" severity error;
				v := v + 1;
			end if;
			if now - t_d < T_DS then
				report "SRAM: data setup " & time'image(now - t_d) & " < tSD" severity error;
				v := v + 1;
			end if;
			if is_x(a) or is_x(d) then
				report "SRAM: write with X address or data" severity error;
				v := v + 1;
			else
				mem(to_integer(unsigned(a))) := d;
			end if;
		end if;

		-- read path
		if n_ce = '0' and n_oe = '0' and n_we = '1' then
			ready_at := maximum(maximum(t_addr + T_AA, t_ce + T_AA), when_oe + T_OE);
			if is_x(a) then
				d <= (others => 'X');
			elsif now >= ready_at then
				d <= mem(to_integer(unsigned(a)));
			else
				-- transport: keep the X now and the data later (inertial would drop the X)
				d <= transport (others => 'X');
				d <= transport mem(to_integer(unsigned(a))) after ready_at - now;
			end if;
		else
			d <= (others => 'Z');
		end if;
		viol <= v;
	end process;
end architecture;
