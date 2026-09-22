-- Main board integration testbench: the real CPU (cpu.vhd) and the real
-- chipset (chipset.vhd) with the SRAM and SST39 timing models.
--
-- Prints the lockstep trace (same format as tools/simtrace.nim) by watching
-- the CPU bus, so tools/lockstep.py can diff whole-system runs against
-- sim.nim. With NOISE, a bridge BFM hammers SRAM $d000-$dfff with reads and
-- writes throughout the run (BRG-003): the CPU trace must not change.
--
-- The SRAM is loaded with IMAGE at $1000; the ROM with ROM_IMAGE (normally
-- just `b $1000` at ROM 0, which the CPU fetches at reset through the fixed
-- window at $e000).

library ieee;
use ieee.std_logic_1164.all;
use ieee.numeric_std.all;
use std.textio.all;

entity tb_mainboard is
	generic(
		IMAGE:		string := "image.hex";
		IMAGE_LEN:	natural := 0;
		ROM_IMAGE:	string := "rom.hex";
		NOISE:		boolean := false;
		MAX_CYCLES:	natural := 40_000_000
	);
end entity;

architecture sim of tb_mainboard is
	constant T: time := 83.333 ns;
	signal clk: std_logic := '0';
	signal done: boolean := false;
	signal n_por: std_logic := '0';

	-- CPU bus
	signal a: std_logic_vector(15 downto 0);
	signal d: std_logic_vector(7 downto 0);					-- the shared data bus
	signal cpu_dout, cs_dout: std_logic_vector(7 downto 0);
	signal cpu_doe, cs_doe, rw, n_stb, n_rdy, sync, halted, waiting, n_rst: std_logic;
	signal irq: std_logic_vector(3 downto 0);
	signal tmr_exp: std_logic_vector(1 downto 0);
	signal pc, sp: std_logic_vector(15 downto 0);
	signal r0, r1: std_logic_vector(7 downto 0);
	signal fl: std_logic_vector(1 downto 0);

	-- memory bus
	signal mem_a, ram_a: std_logic_vector(18 downto 0);
	signal mem_d, mem_dout: std_logic_vector(7 downto 0);
	signal mem_doe, mem_n_oe, mem_n_we, n_ce_ram, n_ce_rom: std_logic;
	signal ram_viol, rom_viol: natural;

	signal spi_sck, spi_mosi: std_logic;
	signal spi_n_cs: std_logic_vector(6 downto 0);
	signal gpo: std_logic_vector(7 downto 0);
	signal br_sck, br_mosi: std_logic := '0';
	signal br_n_cs: std_logic := '1';
	signal br_miso: std_logic;
	signal noise_errors: natural := 0;

	function hx(v: std_logic_vector) return string is
		constant digits: string(1 to 16) := "0123456789abcdef";
		constant vv: std_logic_vector(v'length - 1 downto 0) := v;
		variable r: string(1 to v'length / 4);
		variable nib: std_logic_vector(3 downto 0);
	begin
		for i in r'range loop
			nib := vv(v'length - 1 - (i - 1) * 4 downto v'length - i * 4);
			if is_x(nib) then r(i) := 'x'; else r(i) := digits(to_integer(unsigned(nib)) + 1); end if;
		end loop;
		return r;
	end function;

	procedure emit(s: string) is
		variable l: line;
	begin
		write(l, s);
		writeline(output, l);
	end procedure;
begin
	clk <= not clk after T / 2 when not done;
	n_por <= '1' after 5 * T;

	cpu0: entity work.cpu port map(
		clk => clk, n_rst => n_rst, a => a, d_in => d, d_out => cpu_dout, d_oe => cpu_doe,
		rw => rw, n_stb => n_stb, n_rdy => n_rdy, sync => sync, irq => irq, tmr_exp => tmr_exp,
		halted => halted, waiting => waiting,
		dbg_pc => pc, dbg_sp => sp, dbg_r0 => r0, dbg_r1 => r1, dbg_f => fl);

	cs0: entity work.chipset port map(
		clk => clk, n_por => n_por,
		cpu_a => a, cpu_d_in => d, cpu_d_out => cs_dout, cpu_d_oe => cs_doe, cpu_rw => rw,
		cpu_n_stb => n_stb, cpu_n_rdy => n_rdy, cpu_sync => sync, cpu_irq => irq,
		cpu_tmr_exp => tmr_exp, cpu_halted => halted, cpu_waiting => waiting, cpu_n_rst => n_rst,
		cpu_present => '1', cpu_card_id => "10",
		mem_a => mem_a, mem_d_in => mem_d, mem_d_out => mem_dout, mem_d_oe => mem_doe,
		mem_n_oe => mem_n_oe, mem_n_we => mem_n_we, mem_n_ce_ram => n_ce_ram, mem_n_ce_rom => n_ce_rom,
		spi_sck => spi_sck, spi_mosi => spi_mosi, spi_miso => 'H', spi_n_cs => spi_n_cs,
		slot_n_irq => "111111", gpo => gpo,
		br_sck => br_sck, br_mosi => br_mosi, br_miso => br_miso, br_n_cs => br_n_cs);

	-- the CPU bus data lines, driven by whichever side has D enabled
	d <= cpu_dout when cpu_doe = '1' else (others => 'Z');
	d <= cs_dout when cs_doe = '1' else (others => 'Z');

	mem_d <= mem_dout when mem_doe = '1' else (others => 'Z');
	ram_a <= "000" & mem_a(15 downto 0);
	ram: entity work.sram_model generic map(INIT_FILE => IMAGE, INIT_BASE => 16#1000#)
		port map(a => ram_a, d => mem_d, n_ce => n_ce_ram, n_oe => mem_n_oe, n_we => mem_n_we,
				 violations => ram_viol);
	rom: entity work.sst39_model generic map(INIT_FILE => ROM_IMAGE)
		port map(a => mem_a, d => mem_d, n_ce => n_ce_rom, n_oe => mem_n_oe, n_we => mem_n_we,
				 violations => rom_viol);

	-- observe the CPU bus: lockstep trace + protocol monitor (BUS-002)
	observe: process(clk)
		variable busy, started: boolean := false;
		variable c_a: std_logic_vector(15 downto 0);
		variable c_rw, c_sync: std_logic;
		variable c_d: std_logic_vector(7 downto 0);
		variable cycles: natural := 0;
	begin
		if rising_edge(clk) and not done then
			cycles := cycles + 1;
			assert not (cpu_doe = '1' and cs_doe = '1')
				report "BUS: CPU and chipset both drive D" severity failure;
			if n_rdy = '0' then
				-- completion edge
				assert busy report "BUS: /RDY without a cycle" severity failure;
				busy := false;
				if c_rw = '0' and started then
					emit("W " & hx(c_a) & " " & hx(c_d));
				end if;
				if c_sync = '1' and started and d(7 downto 3) = "11111" then
					emit("E halt");
					done <= true;
				end if;
				assert c_rw = '0' or not is_x(d) report "BUS: read data is X" severity failure;
			elsif busy then
				assert n_stb = '0' and a = c_a and rw = c_rw and (rw = '1' or d = c_d)
					report "BUS: request changed before /RDY" severity failure;
			elsif n_stb = '0' and n_rst = '1' then
				busy := true;
				c_a := a; c_rw := rw; c_d := d; c_sync := sync;
				if sync = '1' then
					if pc = x"1000" then started := true; end if;
					if started then
						emit("S " & hx(pc) & " " & hx(r0) & " " & hx(r1) & " " & hx("00" & fl) & " " & hx(sp));
						if to_integer(unsigned(a)) >= 16#1000# + IMAGE_LEN then
							emit("E end");
							done <= true;
						end if;
					end if;
				end if;
			end if;
			if cycles >= MAX_CYCLES then
				emit("E limit");
				done <= true;
			end if;
			if done then
				assert ram_viol = 0 and rom_viol = 0 report "memory timing violations" severity failure;
				assert noise_errors = 0 report "bridge noise read back wrong data" severity failure;
			end if;
		end if;
	end process;

	-- BRG-003: bridge traffic to $d000-$dfff while the CPU runs
	bridge_noise: process
		variable lfsr: unsigned(15 downto 0) := x"ace1";
		variable addr, len: natural;
		variable r: std_logic_vector(7 downto 0);
		type shadow_t is array(0 to 4095) of std_logic_vector(7 downto 0);
		variable shadow: shadow_t := (others => x"00");
		variable written: std_logic_vector(0 to 4095) := (others => '0');

		procedure xfer(tx: std_logic_vector(7 downto 0); rx: out std_logic_vector(7 downto 0)) is
			variable v: std_logic_vector(7 downto 0);
		begin
			for i in 7 downto 0 loop
				br_mosi <= tx(i); wait for 500 ns;
				br_sck <= '1'; v(i) := br_miso; wait for 500 ns;
				br_sck <= '0';
			end loop;
			rx := v;
		end procedure;
		procedure rnd is
		begin
			lfsr := lfsr(14 downto 0) & (lfsr(15) xor lfsr(13) xor lfsr(12) xor lfsr(10));
		end procedure;
	begin
		if not NOISE then wait; end if;
		wait for 2 us;
		while not done loop
			rnd; addr := to_integer(lfsr(11 downto 0));
			rnd; len := to_integer(lfsr(3 downto 0)) + 1;
			if addr + len > 4096 then addr := 4096 - len; end if;
			br_n_cs <= '0'; wait for 2 us;
			if lfsr(4) = '1' then
				xfer(x"01", r); xfer(std_logic_vector(to_unsigned((16#d000# + addr) mod 256, 8)), r);
				xfer(x"d" & std_logic_vector(to_unsigned(addr / 256, 4)), r);
				xfer(std_logic_vector(to_unsigned(len - 1, 8)), r);
				for i in 0 to len - 1 loop
					rnd;
					shadow(addr + i) := std_logic_vector(lfsr(7 downto 0));
					written(addr + i) := '1';
					xfer(std_logic_vector(lfsr(7 downto 0)), r);
				end loop;
			else
				xfer(x"02", r); xfer(std_logic_vector(to_unsigned((16#d000# + addr) mod 256, 8)), r);
				xfer(x"d" & std_logic_vector(to_unsigned(addr / 256, 4)), r);
				xfer(std_logic_vector(to_unsigned(len - 1, 8)), r);
				xfer(x"00", r);			-- dummy
				for i in 0 to len - 1 loop
					xfer(x"00", r);
					if written(addr + i) = '1' and r /= shadow(addr + i) then
						noise_errors <= noise_errors + 1;
						report "bridge read $" & hx(std_logic_vector(to_unsigned(16#d000# + addr + i, 16))) &
							   " = $" & hx(r) & ", wrote $" & hx(shadow(addr + i)) severity error;
					end if;
				end loop;
			end if;
			wait for 1 us;
			br_n_cs <= '1';
			wait for 3 us;
		end loop;
		wait;
	end process;
end architecture;
