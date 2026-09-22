-- Chipset testbench (MMU, ROM, SPI, IRQ, BRG, DBG tests).
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

	-- bridge
	signal br_sck, br_mosi: std_logic := '0';
	signal br_n_cs: std_logic := '1';
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
		cpu_n_rst => cpu_n_rst, cpu_present => '1', cpu_card_id => "10",
		mem_a => mem_a, mem_d_in => mem_d, mem_d_out => mem_d_out, mem_d_oe => mem_d_oe,
		mem_n_oe => mem_n_oe, mem_n_we => mem_n_we, mem_n_ce_ram => mem_n_ce_ram,
		mem_n_ce_rom => mem_n_ce_rom,
		spi_sck => spi_sck, spi_mosi => spi_mosi, spi_miso => spi_miso, spi_n_cs => spi_n_cs,
		slot_n_irq => slot_n_irq, gpo => gpo,
		br_sck => br_sck, br_mosi => br_mosi, br_miso => br_miso, br_n_cs => br_n_cs);

	mem_d <= mem_d_out when mem_d_oe = '1' else (others => 'Z');
	ram_a <= "000" & mem_a(15 downto 0);		-- SRAM A16-A18 are tied low on the board

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

	-- count completed CPU cycles (/RDY is a one-clock pulse the BFM can miss)
	count_rdy: process(clk)
	begin
		if rising_edge(clk) and cpu_n_rdy = '0' then
			completions <= completions + 1;
		end if;
	end process;

	bfm: process
	begin
		wait on b_go;
		wait until falling_edge(clk);
		cpu_a <= b_addr; cpu_rw <= b_rw; cpu_dw <= b_wdata; cpu_sync <= b_sync; cpu_n_stb <= '0';
		loop
			wait until rising_edge(clk);
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
		variable n: natural;
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
		procedure br_read(cmd: std_logic_vector(7 downto 0); addr: natural; count: natural) is
			variable r: std_logic_vector(7 downto 0);
		begin
			br_begin; br_tx(cmd); br_tx(b8(addr)); br_tx(b8(addr / 256));
			if cmd = x"03" then br_tx(b8(addr / 65536)); end if;
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
		wait for 30 * T;
		check(cpu_n_rst = '1', "CPU held in reset after power-on");

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
			wr(16#f200#, x"0f");
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
			expect(16#f201#, x"0f", "mask upper bits read 0");
			-- slot IRQs: $f202 is live, IRQ0 latches on the rising edge of the OR
			slot_n_irq <= "111011";						-- slot 3 (dev 2)
			wait for 5 * T;
			expect(16#f202#, x"04", "SLOT_IRQ live");
			expect(16#f200#, x"01", "IRQ0 on slot IRQ");
			wr(16#f200#, x"01");
			slot_n_irq <= "011011";						-- a second card while the first holds
			wait for 5 * T;
			expect(16#f202#, x"24", "SLOT_IRQ with two cards");
			expect(16#f200#, x"00", "no new edge while another card holds IRQ");
			slot_n_irq <= "111111";
			wait for 5 * T;
			expect(16#f202#, x"00", "SLOT_IRQ released");
			slot_n_irq <= "111110";
			wait for 5 * T;
			expect(16#f200#, x"01", "a new edge after all released");
			slot_n_irq <= "111111";
			wr(16#f200#, x"0f");
			wr(16#f201#, x"00");
			models_clean("IRQ-001");
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
			check(s(3) = '1' and s(5 downto 4) = "10", "STATUS present/card id: $" & to_hstring(s));
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

		check(b_bad_oe = 0, "chipset did not drive D with /RDY on " & integer'image(b_bad_oe) & " reads");
		assert errors = 0 report integer'image(errors) & " chipset errors" severity failure;
		report "tb_chipset (" & ONLY & "): 0 errors";
		finished <= true;
		std.env.finish;
	end process;
end architecture;
