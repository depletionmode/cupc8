-- SPI-001/SPI-002: SPI master modes, dividers, data both ways, chip selects.
-- The slave model is written from the SPI mode definitions, independently of
-- spi_master.vhd.

library ieee;
use ieee.std_logic_1164.all;
use ieee.numeric_std.all;

entity tb_spi_master is
end entity;

architecture sim of tb_spi_master is
	constant T: time := 10 ns;
	signal clk: std_logic := '0';
	signal rst, start, cpol, cpha, busy, done, sck, mosi, miso: std_logic := '0';
	signal dev: unsigned(2 downto 0) := "000";
	signal tx, rx: std_logic_vector(7 downto 0) := x"00";
	signal div: unsigned(4 downto 0) := "00001";
	signal hold, n_cs: std_logic_vector(7 downto 0) := x"00";
	signal finished: boolean := false;

	-- slave model state
	signal s_out: std_logic_vector(7 downto 0) := x"00";	-- byte the slave sends
	signal s_got: std_logic_vector(7 downto 0);				-- byte the slave received
	signal s_edges: natural := 0;
	signal errors: natural := 0;
begin
	clk <= not clk after T / 2 when not finished;

	dut: entity work.spi_master port map(
		clk => clk, rst => rst, start => start, dev => dev, tx => tx, cpol => cpol, cpha => cpha,
		div => div, hold => hold, busy => busy, done => done, rx => rx, sck => sck,
		mosi => mosi, miso => miso, n_cs => n_cs);

	-- SPI slave on whichever device is selected (all share MOSI/MISO/SCK)
	slave: process(sck, n_cs)
		variable sel: boolean;
		variable outsh, insh: std_logic_vector(7 downto 0);
		variable leading: boolean;
		variable nbits: natural;
	begin
		sel := n_cs /= x"ff";
		if n_cs'event and sel and n_cs'last_value = x"ff" then
			-- selected: CPHA=0 presents bit 7 now
			outsh := s_out; nbits := 0; s_edges <= 0;
			if cpha = '0' then miso <= outsh(7); outsh := outsh(6 downto 0) & '0'; end if;
		end if;
		if sck'event and sel then
			s_edges <= s_edges + 1;
			leading := sck /= cpol;
			if leading = (cpha = '0') then
				insh := insh(6 downto 0) & mosi;			-- sample
				nbits := nbits + 1;
				if nbits = 8 then s_got <= insh; end if;
			else
				miso <= outsh(7);							-- shift out
				outsh := outsh(6 downto 0) & '0';
			end if;
		end if;
		if not sel then miso <= 'Z'; end if;
	end process;

	stim: process
		type bytes_t is array(natural range <>) of std_logic_vector(7 downto 0);
		constant patterns: bytes_t := (x"00", x"ff", x"a5", x"5a", x"01", x"80", x"3c");
		variable t0, t1: time;
		variable last_sck: std_logic;

		procedure check(cond: boolean; msg: string) is
		begin
			if not cond then
				errors <= errors + 1;
				report msg severity error;
			end if;
		end procedure;
	begin
		rst <= '1';
		wait until rising_edge(clk);
		rst <= '0';
		for mode in 0 to 3 loop
			for d in 0 to 31 loop
				for p in patterns'range loop
					cpol <= to_unsigned(mode, 2)(1);
					cpha <= to_unsigned(mode, 2)(0);
					div <= to_unsigned(d, 5);
					dev <= to_unsigned((mode * 3 + p) mod 8, 3);
					tx <= patterns(p);
					s_out <= patterns((p + 3) mod patterns'length);
					wait until rising_edge(clk);
					wait until rising_edge(clk);			-- SCK follows a CPOL change one clock later
					check(sck = cpol, "idle SCK not at CPOL");
					start <= '1';
					wait until rising_edge(clk);
					start <= '0';
					-- SCK half-period check on the first two edges
					wait on sck;
					t0 := now;
					wait on sck;
					t1 := now;
					check(t1 - t0 = T * maximum(d, 1),
						  "mode " & integer'image(mode) & " div " & integer'image(d) &
						  ": half period " & time'image(t1 - t0));
					check(n_cs = not std_logic_vector(shift_left(to_unsigned(1, 8),
								  to_integer(to_unsigned((mode * 3 + p) mod 8, 3)))),
						  "wrong CS during transfer");
					wait until done = '1';
					wait until rising_edge(clk);
					check(rx = patterns((p + 3) mod patterns'length),
						  "mode " & integer'image(mode) & " div " & integer'image(d) &
						  ": master got " & to_hstring(rx));
					check(s_got = patterns(p),
						  "mode " & integer'image(mode) & " div " & integer'image(d) &
						  ": slave got " & to_hstring(s_got));
					check(s_edges = 16, "expected 16 SCK edges, saw " & integer'image(s_edges));
					check(n_cs = x"ff", "CS still low after the transfer");
					check(sck = cpol, "SCK not back at CPOL");
				end loop;
			end loop;
		end loop;

		-- SPI_CS framing: hold keeps a device selected across bytes, and busy
		-- selects only the device being shifted
		cpol <= '0'; cpha <= '0'; div <= to_unsigned(2, 5);
		hold <= x"04";
		wait until rising_edge(clk);
		check(n_cs = x"fb", "SPI_CS hold did not select dev 2");
		dev <= to_unsigned(2, 3); tx <= x"c3"; start <= '1';
		wait until rising_edge(clk);
		start <= '0';
		wait until done = '1';
		wait until rising_edge(clk);
		check(n_cs = x"fb", "dev 2 deselected between bytes despite SPI_CS");
		hold <= x"00";
		wait until rising_edge(clk);
		wait for 1 ns;
		check(n_cs = x"ff", "CS stayed low after SPI_CS cleared");
		hold <= x"30";			-- not one-hot: the lowest set bit wins
		wait for 1 ns;
		check(n_cs = x"ef", "non-one-hot SPI_CS must select only the lowest device");

		assert errors = 0 report integer'image(errors) & " SPI errors" severity failure;
		report "SPI-001/002: 4 modes x 32 dividers x 7 patterns, 0 errors";
		finished <= true;
		std.env.finish;
	end process;
end architecture;
