-- Chipset testbench (MMU, ROM, SPI, IRQ, BRG, DBG, XRAM, CLK tests).
--
-- A CPU-bus BFM stands in for the CPU card and a bridge BFM for sysctl; the
-- memory bus has the SRAM and SST39 timing models, and slot 4 (dev 3) has an
-- SPI slave. Generic ONLY selects one test section (the catalogue runs each
-- separately) or "all". Every section ends by checking the memory models
-- saw no timing violations.

library ieee;
use ieee.std_logic_1164.all;
use ieee.numeric_std.all;

entity tb_chipset is
	generic(
		ONLY:		string := "all";
		ROM_ID:		natural := 16#D7#;		-- device ID: $D7 = SST39VF040, $D5 = SST39VF010
		ROM_ABITS:	natural := 19							-- 17 = SST39VF010
	);
end entity;

architecture sim of tb_chipset is
	constant T: time := 83.333 ns;			-- 12 MHz
	signal clk: std_logic := '0';
	signal finished: boolean := false;
	signal n_por: std_logic := '0';

	-- CPU bus (BFM side)
	signal cpu_a: std_logic_vector(15 downto 0) := x"0000";
	signal cpu_dw, cpu_dr: std_logic_vector(7 downto 0) := x"00";
	signal cpu_d_oe, cpu_rw, cpu_n_stb, cpu_n_rdy, cpu_sync: std_logic := '1';
	signal cpu_irq: std_logic_vector(3 downto 0);
	signal cpu_tmr_exp: std_logic_vector(1 downto 0) := "00";
	signal cpu_n_rst: std_logic;

	-- memory bus
	signal mem_a: std_logic_vector(18 downto 0);
	signal mem_d, mem_d_out: std_logic_vector(7 downto 0);
	signal mem_d_oe, mem_n_oe, mem_n_we, mem_n_ce_ram, mem_n_ce_rom: std_logic;
	signal ram_a: std_logic_vector(18 downto 0);
	signal ram_viol, rom_viol: natural;
	signal last_ram_a: std_logic_vector(18 downto 0) := (others => '0');	-- SRAM address of the last RAM access

	-- SPI
	signal spi_sck, spi_mosi, spi_miso: std_logic;
	signal spi_n_cs: std_logic_vector(6 downto 0);
	signal slot_n_irq: std_logic_vector(5 downto 0) := (others => '1');
	signal gpo: std_logic_vector(7 downto 0);
	signal slave_got: std_logic_vector(7 downto 0) := x"00";
	signal cs3: std_logic;
	signal completions: natural := 0;		-- CPU cycles the chipset completed
	-- CPU BFM handshake: the test toggles b_go; the BFM toggles b_done when the
	-- chipset completes the cycle (and then releases /STB, as a CPU does)
	signal b_go, b_done: boolean := false;
	signal b_addr: std_logic_vector(15 downto 0) := x"0000";
	signal b_wdata, b_rdata: std_logic_vector(7 downto 0) := x"00";
	signal b_rw, b_sync: std_logic := '1';
	signal b_bad_oe: natural := 0;
	signal b_bad_rdy: natural := 0;				-- /RDY while /STB is high (never allowed)
	signal b_aborts: natural := 0;				-- cycles cut short by /CPU_RST

	-- bridge
	signal br_sck, br_mosi: std_logic := '0';
	signal br_n_cs: std_logic := '1';
	signal cpu_cdone: std_logic := '0';			-- the CPU card's FPGA configures later
	signal pwr_hi: std_logic := '0';			-- a default-current USB source
	signal br_miso: std_logic;

	function rom_pattern(i: natural) return std_logic_vector is
	begin
		return std_logic_vector(to_unsigned((i * 7 + i / 2048 * 13 + i / 256) mod 256, 8));
	end function;
	function ram_pattern(i: natural) return std_logic_vector is
	begin
		return std_logic_vector(to_unsigned((i + i / 256 * 3) mod 256, 8));
	end function;
begin
	clk <= not clk after T / 2 when not finished;

	dut: entity work.chipset port map(
		clk => clk, n_por => n_por,
		cpu_a => cpu_a, cpu_d_in => cpu_dw, cpu_d_out => cpu_dr, cpu_d_oe => cpu_d_oe,
		cpu_rw => cpu_rw, cpu_n_stb => cpu_n_stb, cpu_n_rdy => cpu_n_rdy, cpu_sync => cpu_sync,
		cpu_irq => cpu_irq, cpu_tmr_exp => cpu_tmr_exp, cpu_halted => '0', cpu_waiting => '0',
		cpu_n_rst => cpu_n_rst, cpu_cdone => cpu_cdone,
		mem_a => mem_a, mem_d_in => mem_d, mem_d_out => mem_d_out, mem_d_oe => mem_d_oe,
		mem_n_oe => mem_n_oe, mem_n_we => mem_n_we, mem_n_ce_ram => mem_n_ce_ram,
		mem_n_ce_rom => mem_n_ce_rom,
		spi_sck => spi_sck, spi_mosi => spi_mosi, spi_miso => spi_miso, spi_n_cs => spi_n_cs,
		slot_n_irq => slot_n_irq, gpo => gpo, pwr_hi => pwr_hi,
		br_sck => br_sck, br_mosi => br_mosi, br_miso => br_miso, br_n_cs => br_n_cs);

	mem_d <= mem_d_out when mem_d_oe = '1' else (others => 'Z');
	ram_a <= mem_a;			-- SRAM A16-A18 on MEM_A16-A18: banked RAM (extended-ram.md)
	ram_seen: process(clk)
	begin
		if rising_edge(clk) and mem_n_ce_ram = '0' then last_ram_a <= mem_a; end if;
	end process;

	ram: entity work.sram_model port map(a => ram_a, d => mem_d, n_ce => mem_n_ce_ram,
		n_oe => mem_n_oe, n_we => mem_n_we, violations => ram_viol);
	rom: entity work.sst39_model
		generic map(DEVICE_ID => std_logic_vector(to_unsigned(ROM_ID, 8)), ABITS => ROM_ABITS, T_BP => 5 us, T_SE => 40 us,
					T_SCE => 60 us, PATTERN => true)
		port map(a => mem_a, d => mem_d, n_ce => mem_n_ce_rom, n_oe => mem_n_oe, n_we => mem_n_we,
				 violations => rom_viol);

	-- SPI slave on dev 3 (mode 0): answers with the complement of the last byte it got
	spi_miso <= 'H';
	cs3 <= spi_n_cs(3);
	slave: process(spi_sck, cs3)
		variable outsh, insh: std_logic_vector(7 downto 0) := x"00";
		variable last: std_logic_vector(7 downto 0) := x"a5";
	begin
		if cs3'event and cs3 = '0' then
			outsh := not last;
			spi_miso <= outsh(7);
		elsif cs3'event and cs3 = '1' and cs3'last_value = '0' then
			last := insh;
			slave_got <= insh;
			spi_miso <= 'Z';
		elsif cs3 = '0' and spi_sck'event then
			if spi_sck = '1' then
				insh := insh(6 downto 0) & spi_mosi;
			else
				outsh := outsh(6 downto 0) & '0';
				spi_miso <= outsh(7);
			end if;
		end if;
	end process;

	-- count completed CPU cycles (/RDY is a one-clock pulse the BFM can miss),
	-- and catch a /RDY for a request the CPU is no longer making
	count_rdy: process(clk)
	begin
		if rising_edge(clk) and cpu_n_rdy = '0' then
			completions <= completions + 1;
			if cpu_n_stb = '1' then
				report "/RDY while /STB is high" severity error;
				b_bad_rdy <= b_bad_rdy + 1;
			end if;
		end if;
	end process;

	bfm: process
	begin
		wait on b_go;
		wait until falling_edge(clk);
		cpu_a <= b_addr; cpu_rw <= b_rw; cpu_dw <= b_wdata; cpu_sync <= b_sync; cpu_n_stb <= '0';
		loop
			wait until rising_edge(clk);
			if cpu_n_rst = '0' then
				-- like the card: reset is synchronous, the request is dropped
				b_aborts <= b_aborts + 1;
				exit;
			end if;
			if cpu_n_rdy = '0' then
				b_rdata <= cpu_dr;
				if b_rw = '1' and cpu_d_oe /= '1' then b_bad_oe <= b_bad_oe + 1; end if;
				exit;
			end if;
		end loop;
		wait until falling_edge(clk);
		cpu_n_stb <= '1'; cpu_rw <= '1'; cpu_sync <= '0';
		b_done <= not b_done;
	end process;

	stim: process
		variable errors: natural := 0;
		variable d, s: std_logic_vector(7 downto 0);
		variable ok: boolean;
		variable n, m: natural;
		type bytes_t is array(0 to 300) of std_logic_vector(7 downto 0);
		variable buf: bytes_t;

		function run(name: string) return boolean is
		begin
			return ONLY = "all" or ONLY = name;
		end function;

		procedure check(cond: boolean; msg: string) is
		begin
			if not cond then
				errors := errors + 1;
				report msg severity error;
			end if;
		end procedure;

		-------------------------------------------------------------- CPU BFM
		-- one bus cycle per doc/hardware/cpu-bus.md; returns ok=false on timeout
		procedure cycle(addr: std_logic_vector(15 downto 0); rw: std_logic;
						wdata: std_logic_vector(7 downto 0); rdata: out std_logic_vector(7 downto 0);
						ok: out boolean; is_sync: std_logic := '0'; timeout: natural := 100) is
			variable before: boolean;
		begin
			before := b_done;
			b_addr <= addr; b_rw <= rw; b_wdata <= wdata; b_sync <= is_sync;
			b_go <= not b_go;
			wait on b_done for timeout * T;
			ok := b_done /= before;
			rdata := b_rdata;
		end procedure;

		procedure wr(addr: natural; v: std_logic_vector(7 downto 0)) is
			variable dummy: std_logic_vector(7 downto 0);
			variable ok: boolean;
		begin
			cycle(std_logic_vector(to_unsigned(addr, 16)), '0', v, dummy, ok);
			check(ok, "CPU write timed out at $" & to_hstring(to_unsigned(addr, 16)));
		end procedure;

		procedure rd(addr: natural; v: out std_logic_vector(7 downto 0)) is
			variable ok: boolean;
		begin
			cycle(std_logic_vector(to_unsigned(addr, 16)), '1', x"00", v, ok);
			check(ok, "CPU read timed out at $" & to_hstring(to_unsigned(addr, 16)));
		end procedure;

		procedure expect(addr: natural; want: std_logic_vector(7 downto 0); what: string) is
			variable v: std_logic_vector(7 downto 0);
		begin
			rd(addr, v);
			check(v = want, what & ": $" & to_hstring(to_unsigned(addr, 16)) & " read $" &
				  to_hstring(v) & ", expected $" & to_hstring(want));
		end procedure;

		-------------------------------------------------------------- bridge BFM (1 MHz, mode 0)
		procedure br_begin is
		begin
			br_n_cs <= '0';
			wait for 2 us;
		end procedure;
		procedure br_end is
		begin
			wait for 1 us;
			br_n_cs <= '1';
			wait for 3 us;
		end procedure;
		procedure br_xfer(tx: std_logic_vector(7 downto 0); rx: out std_logic_vector(7 downto 0)) is
			variable r: std_logic_vector(7 downto 0);
		begin
			for i in 7 downto 0 loop
				br_mosi <= tx(i);
				wait for 500 ns;
				br_sck <= '1';
				r(i) := br_miso;
				wait for 500 ns;
				br_sck <= '0';
			end loop;
			rx := r;
		end procedure;
		procedure br_tx(tx: std_logic_vector(7 downto 0)) is
			variable r: std_logic_vector(7 downto 0);
		begin
			br_xfer(tx, r);
		end procedure;
		function b8(v: natural) return std_logic_vector is
		begin
			return std_logic_vector(to_unsigned(v mod 256, 8));
		end function;

		procedure br_ram_write(addr: natural; count: natural) is	-- writes buf(0..count-1)
		begin
			br_begin; br_tx(x"01"); br_tx(b8(addr)); br_tx(b8(addr / 256)); br_tx(b8(count - 1));
			for i in 0 to count - 1 loop br_tx(buf(i)); end loop;
			br_end;
		end procedure;
		procedure br_ram_write24(addr: natural; count: natural) is	-- RAM_WR24 of buf(0..count-1)
		begin
			br_begin; br_tx(x"09"); br_tx(b8(addr)); br_tx(b8(addr / 256)); br_tx(b8(addr / 65536));
			br_tx(b8(count - 1));
			for i in 0 to count - 1 loop br_tx(buf(i)); end loop;
			br_end;
		end procedure;
		procedure br_read(cmd: std_logic_vector(7 downto 0); addr: natural; count: natural) is
			variable r: std_logic_vector(7 downto 0);
		begin
			br_begin; br_tx(cmd); br_tx(b8(addr)); br_tx(b8(addr / 256));
			if cmd = x"03" or cmd = x"0a" then br_tx(b8(addr / 65536)); end if;
			br_tx(b8(count - 1));
			br_tx(x"00");								-- dummy
			for i in 0 to count - 1 loop br_xfer(x"00", r); buf(i) := r; end loop;
			br_end;
		end procedure;
		procedure rom_busw(addr: natural; v: std_logic_vector(7 downto 0)) is
		begin
			br_begin; br_tx(x"04"); br_tx(b8(addr)); br_tx(b8(addr / 256)); br_tx(b8(addr / 65536));
			br_tx(v); br_end;
		end procedure;
		procedure br_simple(cmd: std_logic_vector(7 downto 0); resp: out std_logic_vector(7 downto 0)) is
			variable r: std_logic_vector(7 downto 0);
		begin
			br_begin; br_tx(cmd); br_tx(x"00"); br_xfer(x"00", r); br_end;
			resp := r;
		end procedure;
		procedure cpu_ctl(v: std_logic_vector(7 downto 0)) is
		begin
			br_begin; br_tx(x"07"); br_tx(v); br_end;
		end procedure;
		procedure rom_wait_ready is		-- DQ6 stops toggling
			variable a1, a2: std_logic_vector(7 downto 0);
		begin
			for i in 1 to 200 loop
				br_read(x"03", 0, 2);
				exit when buf(0) = buf(1);
			end loop;
		end procedure;

		-- the millisecond counter, MS_COUNT0 first (it latches the rest)
		procedure ms_read(v: out natural) is
			variable b0, b1, b2, b3: std_logic_vector(7 downto 0);
		begin
			rd(16#f206#, b0); rd(16#f207#, b1); rd(16#f208#, b2); rd(16#f209#, b3);
			v := ((to_integer(unsigned(b3(6 downto 0))) * 256 + to_integer(unsigned(b2))) * 256 +
				  to_integer(unsigned(b1))) * 256 + to_integer(unsigned(b0));
		end procedure;

		-- wait for MS_COUNT0 to step: returns right after the read that saw it
		-- (the step came in the last few clocks)
		procedure ms_edge(v: out std_logic_vector(7 downto 0)) is
			variable a, b: std_logic_vector(7 downto 0);
		begin
			rd(16#f206#, a);
			for i in 1 to 20000 loop
				rd(16#f206#, b);
				exit when b /= a;
			end loop;
			check(b /= a, "MS_COUNT0 did not step in 20000 reads");
			v := b;
		end procedure;

		procedure models_clean(section: string) is
		begin
			check(ram_viol = 0 and rom_viol = 0,
				  section & ": memory timing violations (SRAM " & integer'image(ram_viol) &
				  ", ROM " & integer'image(rom_viol) & ")");
			report section & ": done, " & integer'image(errors) & " errors so far";
		end procedure;
	begin
		wait for 5 * T;
		n_por <= '1';
		-- no sysctl: the CPU waits for its card's CDONE, then 16 clocks more
		wait for 30 * T;
		check(cpu_n_rst = '0', "CPU released before the CPU card was configured");
		br_simple(x"05", d);
		check(d(7) = '1', "bridge status does not show /CPU_RST before CDONE: $" & to_hstring(d));
		cpu_cdone <= '1';
		wait for 10 * T;
		check(cpu_n_rst = '0', "CPU released without its start-up delay after CDONE");
		wait for 20 * T;
		check(cpu_n_rst = '1', "CPU still in reset 30 clocks after CDONE");
		br_simple(x"05", d);
		check(d(7) = '0', "bridge status still shows /CPU_RST: $" & to_hstring(d));

		---------------------------------------------------------------- RST-001
		if run("RST-001") then
			-- the CPU card being reconfigured drops CDONE: the CPU goes back to reset
			cpu_cdone <= '0';
			wait for 4 * T;
			check(cpu_n_rst = '0', "CDONE low did not reset the CPU");
			cpu_cdone <= '1';
			wait for 30 * T;
			check(cpu_n_rst = '1', "CPU not released after CDONE came back");
			-- a pulse shorter than the synchroniser still restarts the start-up delay
			cpu_cdone <= '0';
			wait for 3 * T;
			cpu_cdone <= '1';
			wait for 5 * T;
			check(cpu_n_rst = '0', "a CDONE glitch did not hold the CPU in reset");
			wait for 30 * T;
			check(cpu_n_rst = '1', "CPU not released after the glitch");
			-- $f203 bit 1 reports the USB-C source class (the kernel reads it)
			rd(16#f203#, d);
			check(d(1) = '0', "SYSCTL shows a 1.5 A source with PWR_HI low: $" & to_hstring(d));
			pwr_hi <= '1';
			wait for 4 * T;
			rd(16#f203#, d);
			check(d(1) = '1' and d(0) = '0', "SYSCTL with PWR_HI high: $" & to_hstring(d));
			pwr_hi <= '0';			-- back to the default source: later sections read $f203 whole
			wait for 4 * T;
			models_clean("RST-001");
		end if;

		---------------------------------------------------------------- RST-002
		if run("RST-002") then
			-- a CPU cycle, and the CPU card losing CDONE (so /CPU_RST) k clocks
			-- into it: the chipset must drop the cycle, never /RDY it after the
			-- card has let go (the race BUS-004 found; the monitor above
			-- counts any /RDY with /STB high)
			-- a RAM read (the memory controller) and an I/O read (answered at
			-- once), each started at every clock offset around the moment
			-- /CPU_RST asserts (about 3 clocks after CDONE falls, through the
			-- synchroniser): before it, on the very clock it asserts (the case
			-- the formal counterexample found), and after it
			n := b_aborts;
			for kind in 0 to 1 loop
				for d in 0 to 8 loop
					cpu_cdone <= '0';
					for i in 1 to d loop wait until rising_edge(clk); end loop;
					if kind = 0 then b_addr <= x"1000"; else b_addr <= x"f000"; end if;
					b_rw <= '1'; b_wdata <= x"00"; b_sync <= '0';
					b_go <= not b_go;
					wait on b_done for 100 * T;
					cpu_cdone <= '1';
					wait for 40 * T;
					check(cpu_n_rst = '1', "CPU not released after CDONE returned (d=" & integer'image(d) & ")");
				end loop;
			end loop;
			check(b_aborts > n, "no cycle was cut short by the reset: the race was not exercised");
			-- the machine still works afterwards
			wr(16#2000#, x"5a");
			expect(16#2000#, x"5a", "RAM after the resets");
			models_clean("RST-002");
		end if;

		---------------------------------------------------------------- MMU-001
		if run("MMU-001") then
			-- every RAM address below $e000, stride 7 (covers every address bit)
			n := 0;
			while n < 16#e000# loop
				wr(n, ram_pattern(n));
				n := n + 7;
			end loop;
			n := 0;
			while n < 16#e000# loop
				expect(n, ram_pattern(n), "RAM decode");
				n := n + 7;
			end loop;
			-- each address line individually
			for ab in 0 to 15 loop
				n := 2 ** ab;
				if n < 16#e000# then
					wr(n, b8(ab + 16#40#));
				end if;
			end loop;
			for ab in 0 to 15 loop
				n := 2 ** ab;
				if n < 16#e000# then
					expect(n, b8(ab + 16#40#), "RAM address line " & integer'image(ab));
				end if;
			end loop;
			-- I/O space never reaches the SRAM: GPO write, then check RAM $f000 via the bridge
			wr(16#f000#, x"3c");
			br_read(x"02", 16#f000#, 1);
			check(buf(0) = x"00", "a CPU I/O write reached SRAM $f000");
			-- unmapped I/O reads 0
			expect(16#f005#, x"00", "unmapped I/O");
			expect(16#f2ff#, x"00", "unmapped I/O");
			expect(16#f900#, x"00", "unmapped I/O");
			-- ROM_OFF gives $e000-$efff back as RAM
			wr(16#f203#, x"01");
			expect(16#f203#, x"01", "SYSCTL readback");
			wr(16#e123#, x"77"); wr(16#e923#, x"88");
			expect(16#e123#, x"77", "RAM at $e000 with ROM off");
			expect(16#e923#, x"88", "RAM at $e800 with ROM off");
			wr(16#f203#, x"00");
			models_clean("MMU-001");
		end if;

		---------------------------------------------------------------- MMU-003
		if run("MMU-003") then
			for v in 0 to 255 loop
				wr(16#f000#, b8(v));
				wait until rising_edge(clk);
				check(gpo = b8(v), "GPO pins");
				expect(16#f000#, b8(v), "GPO readback");
			end loop;
			br_simple(x"06", d);
			check(d = x"ff", "bridge GPO_RD");
			models_clean("MMU-003");
		end if;

		---------------------------------------------------------------- ROM-001 / ROM-003
		if run("ROM-001") or run("ROM-003") then
			for off in 0 to 2047 loop
				if off mod 5 = 0 or off < 16 or off > 2032 then
					expect(16#e000# + off, rom_pattern(off), "fixed window");
				end if;
			end loop;
			for bank in 0 to 255 loop
				wr(16#f204#, b8(bank));
				for k in 0 to 3 loop
					n := (bank * 37 + k * 511) mod 2048;
					expect(16#e800# + n,
						   rom_pattern((bank mod 2 ** (ROM_ABITS - 11)) * 2048 + n), "banked window");
				end loop;
			end loop;
			expect(16#f204#, x"ff", "ROM_BANK readback");
			-- CPU writes to the windows are ignored
			wr(16#e010#, x"00"); wr(16#f204#, x"03"); wr(16#e810#, x"00");
			expect(16#e010#, rom_pattern(16#10#), "CPU write changed ROM (fixed)");
			expect(16#e810#, rom_pattern(3 * 2048 + 16#10#), "CPU write changed ROM (banked)");
			-- the fixed window ignores ROM_BANK
			expect(16#e7ff#, rom_pattern(16#7ff#), "fixed window with bank set");
			models_clean("ROM-001");
		end if;

		---------------------------------------------------------------- SPI-003
		if run("SPI-003") then
			wr(16#f201#, x"08");						-- unmask IRQ3
			wr(16#f13f#, b8(2 * 8));					-- dev 3: div 2, mode 0
			wr(16#f134#, x"01");						-- SPI_CS hold on dev 3
			check(spi_n_cs = "1110111", "SPI_CS did not select dev 3");
			wr(16#f130#, x"3c");
			wr(16#f132#, x"01");						-- GO
			expect(16#f133#, x"00", "SPI_STAT busy right after GO");
			for i in 1 to 200 loop
				rd(16#f133#, d);
				exit when d = x"01";
			end loop;
			check(d = x"01", "SPI never finished");
			expect(16#f131#, x"5a", "SPI RX (slave sends not $a5)");
			check(cpu_irq(3) = '1', "IRQ3 not raised on SPI completion");
			expect(16#f200#, x"08", "IRQ_PEND after SPI");
			wr(16#f200#, x"08");
			check(cpu_irq = "0000", "IRQ3 not cleared by W1C");
			wr(16#f134#, x"00");
			wait until rising_edge(clk);
			check(slave_got = x"3c", "slave received $" & to_hstring(slave_got));
			check(spi_n_cs = "1111111", "CS still low after SPI_CS cleared");
			-- dev 7 exists as registers only; its RX is the pulled-up MISO
			wr(16#f17f#, b8(8)); wr(16#f170#, x"00"); wr(16#f172#, x"01");
			for i in 1 to 200 loop rd(16#f173#, d); exit when d = x"01"; end loop;
			expect(16#f171#, x"ff", "dev 7 RX");
			wr(16#f200#, x"0f");
			models_clean("SPI-003");
		end if;

		---------------------------------------------------------------- IRQ-001 / IRQ-002
		if run("IRQ-001") or run("IRQ-002") then
			wr(16#f200#, x"1f");
			expect(16#f200#, x"00", "pending after clear");
			-- timer expiry pulses latch bits 1/2
			wait until falling_edge(clk); cpu_tmr_exp <= "01";
			wait until falling_edge(clk); cpu_tmr_exp <= "00";
			expect(16#f200#, x"02", "timer 0 pending");
			check(cpu_irq = "0000", "masked IRQ reached the CPU");
			wr(16#f201#, x"06");
			expect(16#f201#, x"06", "mask readback");
			check(cpu_irq = "0010", "unmasked timer 0 IRQ");
			wait until falling_edge(clk); cpu_tmr_exp <= "10";
			wait until falling_edge(clk); cpu_tmr_exp <= "00";
			wait until rising_edge(clk); wait until rising_edge(clk);
			check(cpu_irq = "0110", "timer 1 IRQ");
			wr(16#f200#, x"02");						-- W1C only bit 1
			expect(16#f200#, x"04", "W1C cleared the wrong bits");
			wr(16#f200#, x"f4");						-- upper bits ignored
			expect(16#f200#, x"00", "W1C of bit 2");
			wr(16#f201#, x"ff");
			expect(16#f201#, x"1f", "mask bits 7:5 read 0");
			-- slot IRQs: $f202 is live; IRQ0 latches a new assertion on any line
			slot_n_irq <= "111011";						-- slot 3 (dev 2)
			wait for 5 * T;
			expect(16#f202#, x"04", "SLOT_IRQ live");
			expect(16#f200#, x"01", "IRQ0 on slot IRQ");
			wr(16#f200#, x"01");
			wait for 5 * T;
			expect(16#f200#, x"00", "a line still held does not re-interrupt");
			slot_n_irq <= "011011";						-- a second card while the first holds
			wait for 5 * T;
			expect(16#f202#, x"24", "SLOT_IRQ with two cards");
			expect(16#f200#, x"01", "a second card's IRQ is latched while the first holds");
			wr(16#f200#, x"01");
			slot_n_irq <= "111111";
			wait for 5 * T;
			expect(16#f202#, x"00", "SLOT_IRQ released");
			expect(16#f200#, x"00", "releasing does not latch");
			slot_n_irq <= "111110";
			wait for 5 * T;
			expect(16#f200#, x"01", "a new assertion after all released");
			slot_n_irq <= "111111";
			wr(16#f200#, x"1f");
			wr(16#f201#, x"00");
			models_clean("IRQ-001");
		end if;

		---------------------------------------------------------------- MMU-005
		if run("MMU-005") then
			-- RAM_BANK ($f205): reset 2, the identity map
			expect(16#f205#, x"02", "RAM_BANK after reset");
			wr(16#8123#, x"a7");
			check(last_ram_a = "000" & x"8123", "identity map: $8123 went to SRAM $" & to_hstring(last_ram_a));
			br_read(x"0a", 16#08123#, 1);
			check(buf(0) = x"a7", "identity map: SRAM $08123 holds $" & to_hstring(buf(0)));
			-- readback: 5 bits, bits 7:5 read 0
			for v in 0 to 255 loop
				wr(16#f205#, b8(v));
				expect(16#f205#, b8(v mod 32), "RAM_BANK readback of $" & to_hstring(b8(v)));
			end loop;
			-- every bank: each window address line, both window edges; the SRAM
			-- sees {bank, A[13:0]} on writes and reads
			for bank in 0 to 31 loop
				wr(16#f205#, b8(bank));
				for k in 0 to 15 loop
					if k < 14 then n := 2 ** k; elsif k = 14 then n := 0; else n := 16#3fff#; end if;
					wr(16#8000# + n, b8(bank * 7 + k * 3 + 1));
					check(to_integer(unsigned(last_ram_a)) = bank * 16384 + n,
						  "bank " & integer'image(bank) & ": write to $" & to_hstring(to_unsigned(16#8000# + n, 16)) &
						  " went to SRAM $" & to_hstring(last_ram_a));
				end loop;
			end loop;
			-- read back after every bank was written (so an alias would show)
			for bank in 0 to 31 loop
				wr(16#f205#, b8(bank));
				for k in 0 to 15 loop
					if k < 14 then n := 2 ** k; elsif k = 14 then n := 0; else n := 16#3fff#; end if;
					expect(16#8000# + n, b8(bank * 7 + k * 3 + 1), "bank " & integer'image(bank) & " readback");
					check(to_integer(unsigned(last_ram_a)) = bank * 16384 + n,
						  "bank " & integer'image(bank) & ": read went to SRAM $" & to_hstring(last_ram_a));
					br_read(x"0a", bank * 16384 + n, 1);
					check(buf(0) = b8(bank * 7 + k * 3 + 1), "bank " & integer'image(bank) &
						  ": RAM_RD24 of SRAM $" & to_hstring(to_unsigned(bank * 16384 + n, 20)) & " = $" & to_hstring(buf(0)));
				end loop;
			end loop;
			-- banks 0, 1 and 3 are the normal memory: the window aliases it
			wr(16#f205#, x"00");
			wr(16#0f81#, x"c3");
			expect(16#8f81#, x"c3", "bank 0 through the window is $0000-$3fff");
			wr(16#f205#, x"01");
			wr(16#b456#, x"3c");
			expect(16#7456#, x"3c", "bank 1 through the window is $4000-$7fff");
			wr(16#f205#, x"03");
			wr(16#8765#, x"69");
			expect(16#c765#, x"69", "bank 3 through the window is $c000-$ffff");
			-- ... including $f000-$ffff, which the CPU otherwise never reaches
			wr(16#b000#, x"96");
			check(last_ram_a = "000" & x"f000", "bank 3 $b000 went to SRAM $" & to_hstring(last_ram_a));
			br_read(x"02", 16#f000#, 1);
			check(buf(0) = x"96", "SRAM $0f000 through the window: $" & to_hstring(buf(0)));
			-- nothing outside the window moves: bank 9, the edges and the other ranges
			wr(16#f205#, x"09");
			for i in 0 to 5 loop
				case i is
					when 0 => n := 16#0000#; when 1 => n := 16#7fff#; when 2 => n := 16#c000#;
					when 3 => n := 16#dfff#; when 4 => n := 16#4000#; when others => n := 16#1234#;
				end case;
				wr(n, b8(i + 16#50#));
				check(to_integer(unsigned(last_ram_a)) = n, "bank 9: $" & to_hstring(to_unsigned(n, 16)) &
					  " went to SRAM $" & to_hstring(last_ram_a));
				expect(n, b8(i + 16#50#), "outside the window with bank 9");
			end loop;
			-- the ROM windows, ROM_OFF RAM and I/O ignore RAM_BANK
			expect(16#e000#, rom_pattern(0), "fixed ROM window with RAM_BANK 9");
			wr(16#f204#, x"05");
			expect(16#e8ff#, rom_pattern(5 * 2048 + 16#ff#), "banked ROM window with RAM_BANK 9");
			wr(16#f000#, x"81");
			check(gpo = x"81", "GPO with RAM_BANK 9");
			expect(16#f204#, x"05", "ROM_BANK with RAM_BANK 9");
			wr(16#f203#, x"01");
			wr(16#e456#, x"42");
			check(last_ram_a = "000" & x"e456", "ROM_OFF RAM $e456 went to SRAM $" & to_hstring(last_ram_a));
			expect(16#e456#, x"42", "ROM_OFF RAM with RAM_BANK 9");
			wr(16#f203#, x"00"); wr(16#f204#, x"00");
			-- a power-on reset puts the identity map back
			n_por <= '0';
			wait for 5 * T;
			n_por <= '1';
			wait for 60 * T;
			check(cpu_n_rst = '1', "CPU not released after the reset");
			expect(16#f205#, x"02", "RAM_BANK after a second reset");
			models_clean("MMU-005");
		end if;

		---------------------------------------------------------------- BRG-004
		if run("BRG-004") then
			-- RAM_WR24/RAM_RD24: 19-bit physical addresses, every length class,
			-- across bank boundaries and across $0ffff, which the 16-bit forms wrap
			for tc in 0 to 7 loop
				case tc is
					when 0 => n := 16#00100#; when 1 => n := 16#0bff0#; when 2 => n := 16#0fff8#;
					when 3 => n := 16#13ffe#; when 4 => n := 16#42abc#; when 5 => n := 16#7ff00#;
					when 6 => n := 16#5c000#; when others => n := 16#20000#;
				end case;
				for len in 1 to 256 loop
					if len = 1 or len = 2 or len = 37 or len = 256 then
						for i in 0 to len - 1 loop buf(i) := b8(tc * 31 + len + i * 5); end loop;
						br_ram_write24(n, len);
						for i in 0 to len - 1 loop buf(i) := x"00"; end loop;
						br_read(x"0a", n, len);
						for i in 0 to len - 1 loop
							check(buf(i) = b8(tc * 31 + len + i * 5), "RAM_RD24 at $" & to_hstring(to_unsigned(n + i, 20)) &
								  " (len " & integer'image(len) & "): $" & to_hstring(buf(i)));
						end loop;
					end if;
				end loop;
				-- the CPU sees the last write through the window
				wr(16#f205#, b8((n + 255) / 16384));
				expect(16#8000# + (n + 255) mod 16384, b8(tc * 31 + 256 + 255 * 5), "RAM_WR24 seen through the window");
			end loop;
			wr(16#f205#, x"02");
			-- the 16-bit forms keep their meaning: SRAM $00000-$0ffff, wrapping
			for i in 0 to 15 loop buf(i) := b8(16#e0# + i); end loop;
			br_ram_write(16#fff8#, 16);
			br_read(x"0a", 16#00000#, 8);
			for i in 0 to 7 loop
				check(buf(i) = b8(16#e8# + i), "RAM_WR wrapped past $ffff to $" & to_hstring(to_unsigned(i, 16)) &
					  ": $" & to_hstring(buf(i)));
			end loop;
			br_read(x"0a", 16#10000#, 8);
			check(buf(0) /= x"e8" or buf(1) /= x"e9", "RAM_WR reached SRAM $10000");
			br_read(x"02", 16#fffc#, 8);
			check(buf(3) = x"e7" and buf(4) = x"e8", "RAM_RD wrap: $" & to_hstring(buf(3)) & " $" & to_hstring(buf(4)));
			-- RAM_RD24 does not touch the ROM, nor ROM_RD the RAM
			br_read(x"0a", 16#00100#, 1);
			check(buf(0) = b8(0 * 31 + 256 + 0), "RAM_RD24 $00100: $" & to_hstring(buf(0)));
			br_read(x"03", 16#00100#, 1);
			check(buf(0) = rom_pattern(16#100#), "ROM_RD $00100 after RAM_WR24: $" & to_hstring(buf(0)));
			models_clean("BRG-004");
		end if;

		---------------------------------------------------------------- BRG-001
		if run("BRG-001") then
			for len in 1 to 256 loop
				if len <= 8 or len mod 37 = 0 or len = 256 then
					n := (len * 997) mod 16#d000#;
					for i in 0 to len - 1 loop buf(i) := b8(len * 3 + i * 11); end loop;
					br_ram_write(n, len);
					for i in 0 to len - 1 loop
						expect(n + i, b8(len * 3 + i * 11), "bridge RAM_WR len " & integer'image(len));
					end loop;
					for i in 0 to len - 1 loop wr(n + i, b8(len + i)); end loop;
					br_read(x"02", n, len);
					for i in 0 to len - 1 loop
						check(buf(i) = b8(len + i), "bridge RAM_RD len " & integer'image(len) &
							  " byte " & integer'image(i) & ": $" & to_hstring(buf(i)));
					end loop;
				end if;
			end loop;
			br_simple(x"05", s);
			-- CPU card presence and ID come from sysctl's expander; here they are reserved
			check(s(5 downto 3) = "000", "STATUS reserved bits 5:3 not 0: $" & to_hstring(s));
			models_clean("BRG-001");
		end if;

		---------------------------------------------------------------- BRG-002
		if run("BRG-002") then
			-- software ID
			rom_busw(16#5555#, x"aa"); rom_busw(16#2aaa#, x"55"); rom_busw(16#5555#, x"90");
			br_read(x"03", 0, 2);
			check(buf(0) = x"bf" and buf(1) = std_logic_vector(to_unsigned(ROM_ID, 8)), "ROM ID $" & to_hstring(buf(0)) & " $" & to_hstring(buf(1)));
			rom_busw(0, x"f0");
			br_read(x"03", 0, 1);
			check(buf(0) = rom_pattern(0), "ID mode not exited");
			-- sector erase of sector 2 ($2000-$2fff)
			rom_busw(16#5555#, x"aa"); rom_busw(16#2aaa#, x"55"); rom_busw(16#5555#, x"80");
			rom_busw(16#5555#, x"aa"); rom_busw(16#2aaa#, x"55"); rom_busw(16#2000#, x"30");
			rom_wait_ready;
			br_read(x"03", 16#2000#, 4);
			check(buf(0) = x"ff" and buf(3) = x"ff", "sector not erased");
			br_read(x"03", 16#1fff#, 1);
			check(buf(0) = rom_pattern(16#1fff#), "erase spilled into the previous sector");
			-- program 16 bytes with DQ polling
			for i in 0 to 15 loop
				rom_busw(16#5555#, x"aa"); rom_busw(16#2aaa#, x"55"); rom_busw(16#5555#, x"a0");
				rom_busw(16#2000# + i, b8(i * 17));
				rom_wait_ready;
			end loop;
			br_read(x"03", 16#2000#, 16);
			for i in 0 to 15 loop
				check(buf(i) = b8(i * 17), "programmed byte " & integer'image(i) & " = $" & to_hstring(buf(i)));
			end loop;
			-- $F0 as program data is a byte to write, not the ID-exit command
			rom_busw(16#5555#, x"aa"); rom_busw(16#2aaa#, x"55"); rom_busw(16#5555#, x"a0");
			rom_busw(16#2010#, x"f0");
			rom_wait_ready;
			br_read(x"03", 16#2010#, 1);
			check(buf(0) = x"f0", "programmed $F0 reads $" & to_hstring(buf(0)));
			-- and the CPU sees it through the banked window (bank 4 = $2000)
			wr(16#f204#, x"04");
			expect(16#e805#, b8(5 * 17), "programmed byte via CPU window");
			models_clean("BRG-002");
		end if;

		---------------------------------------------------------------- DBG-001
		if run("DBG-001") then
			-- drain the trace, stop the CPU, then a cycle must not complete
			br_begin; br_tx(x"08"); br_tx(x"00"); br_xfer(x"00", d); br_xfer(x"00", s);
			n := to_integer(unsigned(s(1 downto 0))) * 256 + to_integer(unsigned(d));
			for i in 1 to n * 4 loop br_tx(x"00"); end loop;
			br_end;
			-- overflow: 600 cycles into a 512-entry ring
			for i in 0 to 599 loop wr(16#0200# + i, b8(i)); end loop;
			br_begin; br_tx(x"08"); br_tx(x"00"); br_xfer(x"00", d); br_xfer(x"00", s);
			n := to_integer(unsigned(s(1 downto 0))) * 256 + to_integer(unsigned(d));
			check(n = 512 and s(7) = '1', "overflow drain: count " & integer'image(n) & ", lost " & std_logic'image(s(7)));
			-- oldest surviving entry is cycle 88 (600 - 512): address $0258, data $58
			br_xfer(x"00", d); check(d = x"58", "oldest entry addr lo $" & to_hstring(d));
			br_xfer(x"00", d); check(d = x"02", "oldest entry addr hi $" & to_hstring(d));
			br_xfer(x"00", d); check(d = x"58", "oldest entry data $" & to_hstring(d));
			br_xfer(x"00", d); check(d = x"00", "oldest entry flags (write) $" & to_hstring(d));
			for i in 1 to 511 * 4 loop br_tx(x"00"); end loop;
			br_end;
			-- a second drain: empty, and the lost flag was cleared by the first
			br_begin; br_tx(x"08"); br_tx(x"00"); br_xfer(x"00", d); br_xfer(x"00", s); br_end;
			check(d = x"00" and s = x"00", "second drain: count $" & to_hstring(s) & to_hstring(d));
			cpu_ctl(x"01");
			br_simple(x"05", s);
			check(s(0) = '1', "STATUS does not show stopped");
			cycle(x"0100", '0', x"5e", d, ok, '1', 200);
			check(not ok, "a cycle completed while stopped");
			-- step one cycle: the pending write completes, exactly once
			n := completions;
			cpu_ctl(x"05");
			check(completions = n + 1, "step-cycle completed " & integer'image(completions - n) & " cycles");
			-- the next cycle is held again
			cycle(x"0101", '1', x"00", d, ok, '0', 200);
			check(not ok, "a second cycle ran after a single step");
			-- release: the held read completes
			n := completions;
			cpu_ctl(x"00");
			check(completions = n + 1, "release completed " & integer'image(completions - n) & " cycles");
			-- trace: the stepped write and the released read
			br_begin; br_tx(x"08"); br_tx(x"00"); br_xfer(x"00", d); br_xfer(x"00", s);
			n := to_integer(unsigned(s(1 downto 0))) * 256 + to_integer(unsigned(d));
			check(n = 2 and s(7) = '0', "trace count " & integer'image(n) & ", header hi $" & to_hstring(s));
			for e in 0 to minimum(n, 2) - 1 loop
				for k in 0 to 3 loop br_xfer(x"00", d); buf(e * 4 + k) := d; end loop;
			end loop;
			br_end;
			check(buf(0) = x"00" and buf(1) = x"01" and buf(2) = x"5e" and buf(3) = x"02",
				  "trace entry 0: " & to_hstring(buf(0)) & to_hstring(buf(1)) & " " &
				  to_hstring(buf(2)) & " " & to_hstring(buf(3)));
			check(buf(4) = x"01" and buf(5) = x"01" and buf(7) = x"01",
				  "trace entry 1: " & to_hstring(buf(4)) & to_hstring(buf(5)) & " flags " & to_hstring(buf(7)));
			-- CPU reset control
			cpu_ctl(x"40");
			wait until rising_edge(clk);
			check(cpu_n_rst = '0', "CPU_CTL bit 6 did not reset the CPU");
			cpu_ctl(x"00");
			wait until rising_edge(clk);
			check(cpu_n_rst = '1', "CPU reset not released");
			models_clean("DBG-001");
		end if;

		---------------------------------------------------------------- CLK-001
		if run("CLK-001") then
			-- the millisecond counter ($f206-$f209, memory-map.md): 12000
			-- clocks a ms, counted from reset
			ms_read(n);
			check(n < 1000, "MS_COUNT after reset: " & integer'image(n));
			-- the rate: from a step, the next is 12000 clocks later (+-20:
			-- each read takes a few clocks), and 50 ms is 600000 clocks
			for k in 1 to 3 loop
				ms_edge(d);
				wait for (12000 - 20) * T;
				expect(16#f206#, d, "MS_COUNT0 12000 clocks after a step, less 20");
				wait for 40 * T;
				expect(16#f206#, b8(to_integer(unsigned(d)) + 1), "MS_COUNT0 12000 clocks after a step, and 20");
			end loop;
			-- (timed from the read that saw the step: a 12001-clock ms is 50
			-- clocks late here)
			ms_edge(d);
			wait for (50 * 12000 - 20) * T;
			expect(16#f206#, b8(to_integer(unsigned(d)) + 49), "MS_COUNT0 50 ms after a step, less 20 clocks");
			wait for 40 * T;
			expect(16#f206#, b8(to_integer(unsigned(d)) + 50), "MS_COUNT0 50 ms after a step, and 20 clocks");
			-- a read that starts with MS_COUNT0 is one value: MS_COUNT1 is
			-- latched when MS_COUNT0 is read, even when the low byte carries
			-- ($xxff to $xx00) before MS_COUNT1 is read
			ms_read(n);
			wait for (255 - n mod 256) * 12000 * T - 200 * T;
			for i in 1 to 20000 loop
				rd(16#f206#, d);
				exit when d = x"ff";
			end loop;
			check(d = x"ff", "MS_COUNT0 never read $ff");
			rd(16#f207#, s);
			wait for 12100 * T;						-- the counter has carried meanwhile
			expect(16#f207#, s, "MS_COUNT1 read after the carry: the value latched with $ff");
			expect(16#f208#, x"00", "MS_COUNT2 latched");
			expect(16#f209#, x"00", "MS_COUNT3 latched");
			expect(16#f206#, x"00", "MS_COUNT0 after the carry");
			expect(16#f207#, b8(to_integer(unsigned(s)) + 1), "MS_COUNT1 after the carry, once MS_COUNT0 was read again");
			-- writes are ignored; reading MS_COUNT1-3 does not latch
			ms_read(n);
			wr(16#f206#, x"55"); wr(16#f207#, x"aa"); wr(16#f208#, x"77"); wr(16#f209#, x"33");
			ms_read(m);
			check(m = n or m = n + 1, "writes moved the counter: " & integer'image(n) & " then " & integer'image(m));
			wait for 12100 * T;
			rd(16#f207#, d);
			check(d = b8(m / 256), "MS_COUNT1 read alone re-latched: $" & to_hstring(d));
			-- a power-on reset clears it
			n_por <= '0';
			wait for 5 * T;
			n_por <= '1';
			wait for 60 * T;						-- the CPU is released after 33 clocks
			ms_read(n);
			check(n = 0, "MS_COUNT 60 clocks after a power-on reset: " & integer'image(n));
			wait for 12000 * T;
			ms_read(n);
			check(n = 1, "MS_COUNT 1 ms after a power-on reset: " & integer'image(n));
			models_clean("CLK-001");
		end if;

		---------------------------------------------------------------- IRQ-003
		if run("IRQ-003") then
			-- the tick: IRQ_PEND bit 4 every 50 ms of the counter, masked at
			-- reset, on CPU IRQ line 3 with SPI complete
			expect(16#f201#, x"00", "IRQ_MASK at reset (the tick masked)");
			ms_read(n);
			wait for ((50 - n mod 50) * 12000 + 200) * T;	-- past the next multiple of 50
			rd(16#f200#, d);
			check(d(4) = '1', "no tick at the counter's multiple of 50: IRQ_PEND $" & to_hstring(d));
			check(cpu_irq = "0000", "a masked tick reached the CPU");
			wr(16#f200#, x"10");
			expect(16#f200#, x"00", "W1C of the tick");
			-- the next comes 50 ms after the last, as the counter reaches a multiple of 50
			wait for (49 * 12000) * T;
			ms_read(n);
			rd(16#f200#, d);
			check(d(4) = '0', "a tick before 50 ms: IRQ_PEND $" & to_hstring(d) & " at " & integer'image(n) & " ms");
			for i in 1 to 20000 loop
				rd(16#f200#, d);
				exit when d(4) = '1';
			end loop;
			ms_read(n);
			check(d(4) = '1' and n mod 50 = 0, "the tick came at " & integer'image(n) & " ms (a multiple of 50)");
			-- unmasked: CPU line 3; SPI complete shares it, each by its own mask bit
			wr(16#f201#, x"10");
			expect(16#f201#, x"10", "IRQ_MASK bit 4");
			check(cpu_irq = "1000", "unmasked tick: CPU IRQ lines " & to_hstring(cpu_irq));
			wr(16#f201#, x"08");
			check(cpu_irq = "0000", "the tick with only SPI's mask bit reached the CPU");
			wr(16#f200#, x"10");
			wr(16#f13f#, b8(2 * 8)); wr(16#f130#, x"00"); wr(16#f132#, x"01");
			for i in 1 to 200 loop rd(16#f133#, d); exit when d = x"01"; end loop;
			expect(16#f200#, x"08", "SPI complete pending");
			check(cpu_irq = "1000", "SPI complete: CPU IRQ lines " & to_hstring(cpu_irq));
			wr(16#f201#, x"10");
			check(cpu_irq = "0000", "SPI complete with only the tick's mask bit reached the CPU");
			wr(16#f200#, x"08");
			wr(16#f201#, x"17");
			check(cpu_irq = "0000", "nothing pending, all unmasked: CPU IRQ lines " & to_hstring(cpu_irq));
			wr(16#f201#, x"00");
			models_clean("IRQ-003");
		end if;

		check(b_bad_oe = 0, "chipset did not drive D with /RDY on " & integer'image(b_bad_oe) & " reads");
		check(b_bad_rdy = 0, integer'image(b_bad_rdy) & " /RDY pulses while /STB was high");
		assert errors = 0 report integer'image(errors) & " chipset errors" severity failure;
		report "tb_chipset (" & ONLY & "): 0 errors";
		finished <= true;
		std.env.finish;
	end process;
end architecture;
