-- Directed tests of cpu.vhd (CPU-004..007), run by tools/cpudirected.py.
--
--   CPU-004  reset state; reset held mid-instruction restarts cleanly; timers
--            and I are cleared; nothing is driven while in reset
--   CPU-005  IRQs: not taken with I=0 nor right after POP pcl; lowest number first; push order pch,
--            pcl, f; I cleared; vector read; the return is exact; taken only
--            at instruction boundaries (an IRQ raised at every clock phase)
--   CPU-006  timers count retired instructions (including WAI waits, once
--            every 3 clocks); TMR_EXP one clock wide, once per expiry; 0 stops
--   CPU-007  WAI is a NOP with I=0 and parks with I=1 (no bus cycles) until
--            an IRQ; HALT stops for good, whatever the IRQs; HALTED/WAITING
--
-- The program is test/cpu/directed.s; its labels arrive as the package
-- cpu_directed_syms (generated). The chipset model plants `b <entry>` at the
-- reset vector, keeps IRQ_PEND/IRQ_MASK at $f200/$f201, and logs every cycle.

library ieee;
use ieee.std_logic_1164.all;
use ieee.numeric_std.all;
use std.textio.all;
use work.cpu_directed_syms.all;

entity tb_cpu_directed is
	generic(
		IMAGE:	string := "image.hex";		-- loaded at $1000
		ONLY:	string := "all"
	);
end entity;

architecture sim of tb_cpu_directed is
	signal clk:		std_logic := '0';
	signal n_rst:	std_logic := '0';
	signal a:		std_logic_vector(15 downto 0);
	signal d_in, d_out: std_logic_vector(7 downto 0);
	signal d_oe, rw, n_stb, sync, halted, waiting: std_logic;
	signal n_rdy:	std_logic := '1';
	signal irq:		std_logic_vector(3 downto 0);
	signal tmr_exp:	std_logic_vector(1 downto 0);
	signal pc, sp:	std_logic_vector(15 downto 0);
	signal r0, r1:	std_logic_vector(7 downto 0);
	signal fl:		std_logic_vector(1 downto 0);
	signal done:	boolean := false;

	-- stimulus -> chipset
	signal entry:	natural := L_main;
	signal poke_en:	boolean := false;
	signal poke_a:	natural := 0;
	signal poke_d:	std_logic_vector(7 downto 0) := x"00";
	signal set_pend: std_logic_vector(3 downto 0) := "0000";

	-- chipset -> stimulus (observations)
	signal pending, mask: std_logic_vector(3 downto 0) := "0000";
	signal clocks:	natural := 0;
	signal fetch_n:	natural := 0;				-- opcode fetches since power-on
	signal fetch_a:	natural := 0;				-- address of the last one
	signal cycles_n: natural := 0;				-- bus cycles started
	signal entries:	natural := 0;				-- handler entries
	signal ent_vec:	natural := 0;				-- which handler
	signal ent_pch, ent_pcl, ent_f: std_logic_vector(7 downto 0) := x"00";
	signal ent_rd0, ent_rd1: natural := 0;		-- the two reads before it (the vector)
	signal ent_sp:	natural := 0;				-- SP when the handler starts
	signal ent_i:	std_logic := '0';			-- I when the handler starts
	signal exp0_n, exp1_n: natural := 0;
	signal exp0_fetch: natural := 0;			-- last fetch before the pulse
	signal exp0_wait: std_logic := '0';			-- parked in WAI at the pulse
	signal exp0_clk: natural := 0;
	signal wait_clk: natural := 0;				-- clock WAITING last rose
	signal mem300:	std_logic_vector(7 downto 0) := x"00";
	signal violations: natural := 0;
begin
	dut: entity work.cpu port map(
		clk => clk, n_rst => n_rst, a => a, d_in => d_in, d_out => d_out, d_oe => d_oe,
		rw => rw, n_stb => n_stb, n_rdy => n_rdy, sync => sync, irq => irq,
		tmr_exp => tmr_exp, halted => halted, waiting => waiting,
		dbg_pc => pc, dbg_sp => sp, dbg_r0 => r0, dbg_r1 => r1, dbg_f => fl);

	clk <= not clk after 5 ns when not done;
	irq <= pending and mask;

	chipset: process(clk)
		type mem_t is array(0 to 65535) of std_logic_vector(7 downto 0);
		variable mem: mem_t := (others => x"00");
		variable loaded, busy: boolean := false;
		variable cyc_a: natural;
		variable cyc_rw, cyc_sync: std_logic;
		variable cyc_d: std_logic_vector(7 downto 0);
		variable p: std_logic_vector(3 downto 0);
		variable w0, w1, w2: std_logic_vector(7 downto 0) := x"00";		-- last three writes
		variable r_prev, r_last: natural := 0;						-- last two reads
		variable exp_prev: std_logic_vector(1 downto 0) := "00";
		variable wait_prev: std_logic := '0';
		variable rst_prev: std_logic := '0';
		variable v: natural;
		file f: text;
		variable l: line;
		variable b: std_logic_vector(7 downto 0);
		variable ld: natural := 16#1000#;
	begin
		if not loaded then
			loaded := true;
			file_open(f, IMAGE, read_mode);
			while not endfile(f) loop
				readline(f, l);
				if l /= null and l'length > 0 then
					hread(l, b);
					mem(ld) := b;
					ld := ld + 1;
				end if;
			end loop;
			file_close(f);
			-- the IRQ vectors ($0010 + 2n, little-endian) point at h0..h3
			mem(16#10#) := std_logic_vector(to_unsigned(L_h0 mod 256, 8)); mem(16#11#) := std_logic_vector(to_unsigned(L_h0 / 256, 8));
			mem(16#12#) := std_logic_vector(to_unsigned(L_h1 mod 256, 8)); mem(16#13#) := std_logic_vector(to_unsigned(L_h1 / 256, 8));
			mem(16#14#) := std_logic_vector(to_unsigned(L_h2 mod 256, 8)); mem(16#15#) := std_logic_vector(to_unsigned(L_h2 / 256, 8));
			mem(16#16#) := std_logic_vector(to_unsigned(L_h3 mod 256, 8)); mem(16#17#) := std_logic_vector(to_unsigned(L_h3 / 256, 8));
		end if;

		if rising_edge(clk) and not done then
			clocks <= clocks + 1;
			p := pending or set_pend;
			n_rdy <= '1';
			d_in <= (others => 'X');
			if poke_en then
				if poke_a = 16#f201# then mask <= poke_d(3 downto 0);
				else mem(poke_a) := poke_d;
				end if;
			end if;
			-- the reset vector jumps to the section under test
			mem(16#e000#) := x"b0";
			mem(16#e001#) := std_logic_vector(to_unsigned(entry mod 256, 8));
			mem(16#e002#) := std_logic_vector(to_unsigned(entry / 256, 8));

			-- nothing may be driven once reset has been low for a clock
			-- (cpu-bus.md: the card's outputs go idle one clock after /CPU_RST falls)
			if n_rst = '0' and rst_prev = '0' and (n_stb = '0' or d_oe = '1') then
				report "CPU active during reset" severity error;
				violations <= violations + 1;
			end if;

			if n_rdy = '0' then
				busy := false;
				if cyc_rw = '0' then
					if cyc_a = 16#f200# then
						p := p and not cyc_d(3 downto 0);
					elsif cyc_a = 16#f201# then
						mask <= cyc_d(3 downto 0);
					else
						mem(cyc_a) := cyc_d;
					end if;
					w0 := w1; w1 := w2; w2 := cyc_d;
				else
					r_prev := r_last; r_last := cyc_a;
				end if;
			elsif not busy and n_stb = '0' and n_rst = '1' then
				busy := true;
				cyc_a := to_integer(unsigned(a));
				cyc_rw := rw;
				cyc_d := d_out;
				cyc_sync := sync;
				cycles_n <= cycles_n + 1;
				if sync = '1' then
					fetch_n <= fetch_n + 1;
					fetch_a <= cyc_a;
					if cyc_a = L_h0 or cyc_a = L_h1 or cyc_a = L_h2 or cyc_a = L_h3 then
						entries <= entries + 1;
						ent_vec <= cyc_a;
						ent_pch <= w0; ent_pcl <= w1; ent_f <= w2;
						ent_rd0 <= r_prev; ent_rd1 <= r_last;
						ent_sp <= to_integer(unsigned(sp));
						ent_i <= fl(1);
					end if;
				end if;
			end if;
			if busy and n_rdy = '1' then
				n_rdy <= '0';
				if cyc_rw = '1' then
					if cyc_a = 16#f200# then d_in <= "0000" & p;
					elsif cyc_a = 16#f201# then d_in <= "0000" & mask;
					else d_in <= mem(cyc_a);
					end if;
				end if;
			end if;

			-- timer pulses: one clock wide, counted
			for t in 0 to 1 loop
				if tmr_exp(t) = '1' and exp_prev(t) = '1' then
					report "TMR_EXP" & integer'image(t) & " wider than one clock" severity error;
					violations <= violations + 1;
				end if;
			end loop;
			if tmr_exp(0) = '1' then
				p(1) := '1';
				exp0_n <= exp0_n + 1;
				exp0_fetch <= fetch_a;
				exp0_wait <= waiting;
				exp0_clk <= clocks;
			end if;
			if tmr_exp(1) = '1' then
				p(2) := '1';
				exp1_n <= exp1_n + 1;
			end if;
			exp_prev := tmr_exp;
			if waiting = '1' and wait_prev = '0' then wait_clk <= clocks; end if;
			wait_prev := waiting;
			rst_prev := n_rst;
			if n_rst = '0' then
				p := "0000";					-- a machine reset clears the IRQ controller
				mask <= "0000";
				busy := false;
			end if;
			pending <= p;
			mem300 <= mem(16#300#);
		end if;
	end process;

	stim: process
		variable errors: natural := 0;
		variable n, t0, c0: natural;
		variable seen_bad: boolean;
		variable span: integer;

		procedure check(cond: boolean; msg: string) is
		begin
			if not cond then
				report msg severity error;
				errors := errors + 1;
			end if;
		end procedure;

		function run(name: string) return boolean is
		begin
			return ONLY = "all" or ONLY = name;
		end function;

		procedure tick(k: natural) is
		begin
			for i in 1 to k loop wait until rising_edge(clk); end loop;
		end procedure;

		-- wait until the CPU fetches the opcode at `addr`
		procedure wait_fetch(addr: natural; what: string; limit: natural := 5000) is
			variable last: natural := fetch_n;
		begin
			for i in 1 to limit loop
				wait until rising_edge(clk);
				if fetch_n /= last then
					last := fetch_n;
					if fetch_a = addr then return; end if;
				end if;
			end loop;
			check(false, "never fetched " & what);
		end procedure;

		procedure boot(e: natural) is
		begin
			n_rst <= '0';
			entry <= e;
			set_pend <= "0000";
			tick(6);
			n_rst <= '1';
		end procedure;

		procedure poke(addr: natural; v: std_logic_vector(7 downto 0)) is
		begin
			poke_a <= addr; poke_d <= v; poke_en <= true;
			wait until rising_edge(clk);
			poke_en <= false;
		end procedure;

		procedure raise(bits: std_logic_vector(3 downto 0)) is
		begin
			set_pend <= bits;
			wait until rising_edge(clk);
			set_pend <= "0000";
		end procedure;

		function u8(v: natural) return std_logic_vector is
		begin
			return std_logic_vector(to_unsigned(v mod 256, 8));
		end function;
	begin
		---------------------------------------------------------------- CPU-004
		if run("CPU-004") then
			boot(L_rst_prog);
			-- the first cycle after reset: an opcode fetch at $e000, clean state
			wait until rising_edge(clk) and n_stb = '0';
			check(sync = '1' and a = x"e000", "first cycle is not the fetch at $e000");
			check(pc = x"e000" and sp = x"0100" and r0 = x"00" and r1 = x"00" and fl = "00",
				  "reset state pc=" & to_hstring(pc) & " sp=" & to_hstring(sp) &
				  " r0=" & to_hstring(r0) & " r1=" & to_hstring(r1) & " f=" & to_hstring(fl));
			wait_fetch(L_rst_loop, "rst_loop");
			check(r0 = x"12" and r1 = x"34" and fl = "11", "before the mid-instruction reset");
			-- reset while the CPU is fetching the address operand of `ld`
			wait until rising_edge(clk) and n_stb = '0' and to_integer(unsigned(a)) = L_rst_loop + 1;
			n_rst <= '0';
			entry <= L_rst_idle;
			tick(3);
			n_rst <= '1';
			wait until rising_edge(clk) and n_stb = '0';
			check(sync = '1' and a = x"e000", "no clean restart after a mid-instruction reset");
			check(sp = x"0100" and r0 = x"00" and r1 = x"00" and fl = "00",
				  "state after the mid-instruction reset: sp=" & to_hstring(sp) & " f=" & to_hstring(fl));
			-- TMR0 was loaded with 5 before the reset: it must not fire now
			n := exp0_n;
			tick(400);
			check(exp0_n = n, "a timer survived reset");
			check(halted = '0' and waiting = '0', "HALTED/WAITING after reset");
		end if;

		---------------------------------------------------------------- CPU-005
		if run("CPU-005") then
			boot(L_irq_prog);
			wait_fetch(L_irq_loop, "irq_loop");
			-- I = 0: pending, unmasked IRQs are not taken
			raise("0110");
			n := entries;
			tick(300);
			check(entries = n, "IRQ taken with I = 0");
			-- STI: the lowest-numbered pending IRQ (1) goes first
			poke(16#0400#, x"01");
			wait until rising_edge(clk) and entries = n + 1 for 20 us;
			check(ent_vec = L_h1, "first handler is not IRQ1's");
			check(ent_rd0 = 16#12# and ent_rd1 = 16#13#, "vector not read from $0012/$0013: " &
				  integer'image(ent_rd0) & "/" & integer'image(ent_rd1));
			check(ent_pch = u8(L_irq_loop2 / 256) and ent_pcl = u8(L_irq_loop2),
				  "pushed return $" & to_hstring(ent_pch) & to_hstring(ent_pcl) & " (want irq_loop2)");
			check(ent_f = x"03", "pushed f $" & to_hstring(ent_f) & " (want I=1 Z=1)");
			check(ent_i = '0', "I not cleared on entry");
			check(ent_sp = 16#103#, "SP after the three pushes: " & integer'image(ent_sp));
			-- IRQ2 still pending: `pop f` restores I first, so it is taken in
			-- h1's epilogue, before `pop pcl` (the manual's return sequence);
			-- it nests three bytes deeper and unwinds exactly
			wait until rising_edge(clk) and entries = n + 2 for 20 us;
			check(ent_vec = L_h2, "second handler is not IRQ2's");
			check(ent_pch = u8(L_h1_ret / 256) and ent_pcl = u8(L_h1_ret) and ent_f = x"03",
				  "IRQ2 pushed $" & to_hstring(ent_pch) & to_hstring(ent_pcl) & " f=" & to_hstring(ent_f) &
				  " (want h1_ret, f=$03)");
			check(ent_sp = 16#105#, "SP in the nested handler: " & integer'image(ent_sp) & " (want $0105)");
			wait_fetch(L_irq_loop2, "irq_loop2 after the handlers");
			check(fl(1) = '1' and sp = x"0100", "I/SP not restored by the return");
			-- an IRQ raised at every clock phase of the loop is taken only at a
			-- boundary: the pushed return is always one of the loop's instructions
			seen_bad := false;
			for k in 0 to 40 loop
				wait_fetch(L_irq_loop2, "irq_loop2 (phase " & integer'image(k) & ")");
				tick(k);
				n := entries;
				raise("0001");
				wait until rising_edge(clk) and entries = n + 1 for 20 us;
				t0 := to_integer(unsigned(ent_pch)) * 256 + to_integer(unsigned(ent_pcl));
				if ent_vec /= L_h0 or not (t0 = L_irq_loop2 or t0 = L_irq_loop2 + 2 or t0 = L_irq_loop2 + 5) then
					check(false, "phase " & integer'image(k) & ": handler " & integer'image(ent_vec) &
						  " pushed $" & integer'image(t0) & ", not an instruction boundary");
					seen_bad := true;
				end if;
			end loop;
			check(mem300 = x"10", "handler 0 did not run");
			-- an IRQ due as POP pcl retires is taken after the POP pch: an IRQ
			-- between the two would push over the popped byte, and its
			-- handler's POP pcl would replace pcl
			n := entries;
			boot(L_irq_ret_prog);
			wait until rising_edge(clk) and entries = n + 1 for 20 us;
			check(ent_vec = L_h1 and ent_pch = u8(L_irq_ret_back / 256) and ent_pcl = u8(L_irq_ret_back),
				  "an IRQ due at POP pcl pushed $" & to_hstring(ent_pch) & to_hstring(ent_pcl) &
				  " (want irq_ret_back, after the POP pch)");
			wait_fetch(L_irq_ret_done, "irq_ret_done after the handler");
		end if;

		---------------------------------------------------------------- CPU-006
		if run("CPU-006") then
			n := exp0_n;					-- CPU-005's last test fires TMR0 too
			boot(L_tmr_prog);
			wait until rising_edge(clk) and halted = '1' for 50 us;
			-- TMR0 #3 counts its own retirement: it fires as the 2nd following
			-- instruction retires, and TMR0 #1 fires on its own retirement
			check(exp0_n - n = 2, "TMR0 fired " & integer'image(exp0_n - n) & " times (want 2)");
			check(exp0_fetch = L_tmr_self, "the second expiry was not TMR0 #1's own");
			check(exp1_n = 0, "TMR1 fired after being stopped with 0");
			-- first expiry position: rerun and stop at it
			boot(L_tmr_prog);
			n := exp0_n;
			wait until rising_edge(clk) and exp0_n = n + 1 for 50 us;
			check(exp0_fetch = L_tmr_fire, "TMR0 #3 fired after the wrong instruction");
			-- in WAI the timers keep counting, one tick every 3 clocks: the
			-- expiry comes 12 clocks later for 4 more counts
			span := 0;
			for pass in 0 to 1 loop
				boot(L_tmr_wai);
				poke(16#0200#, u8(4 + pass * 4));
				n := entries;
				wait until rising_edge(clk) and entries = n + 1 for 50 us;
				check(ent_vec = L_h1, "the timer IRQ did not wake the WAI");
				check(exp0_wait = '1', "the timer did not expire while parked");
				if pass = 0 then span := exp0_clk - wait_clk;
				else check(exp0_clk - wait_clk - span = 12,
						   "4 more counts took " & integer'image(exp0_clk - wait_clk - span) & " clocks (want 12)");
				end if;
				wait_fetch(L_tmr_woke, "the instruction after WAI");
			end loop;
		end if;

		---------------------------------------------------------------- CPU-007
		if run("CPU-007") then
			-- WAI with I = 0 is a NOP
			boot(L_wai_nop);
			wait_fetch(L_wai_nop_done, "past WAI with I = 0", 400);
			check(r0 = x"77", "the instruction after the WAI did not run");
			-- WAI with I = 1 parks: WAITING, no bus cycles, until an IRQ
			boot(L_wai_park);
			wait until rising_edge(clk) and waiting = '1' for 20 us;
			check(waiting = '1', "WAI with I = 1 did not park");
			c0 := cycles_n;
			tick(500);
			check(cycles_n = c0, "bus cycles while parked in WAI");
			raise("0001");
			tick(50);
			check(cycles_n = c0 and waiting = '1', "a masked IRQ woke the WAI");
			poke(16#f201#, x"01");
			wait_fetch(L_wai_park_done, "past WAI after the IRQ");
			check(waiting = '0', "WAITING still high after the IRQ");
			check(r0 = x"66" and mem300 = x"10", "the handler and then the next instruction ran");
			-- HALT stops for good, IRQs or not
			boot(L_halt_prog);
			wait until rising_edge(clk) and halted = '1' for 20 us;
			check(halted = '1', "HALTED not set");
			c0 := cycles_n;
			raise("1111");
			tick(1000);
			check(cycles_n = c0 and halted = '1', "the CPU ran after HALT");
			check(r0 = x"0f", "the instruction after HALT ran");
			boot(L_rst_idle);
			tick(20);
			check(halted = '0', "HALTED survived reset");
		end if;

		check(violations = 0, integer'image(violations) & " protocol violations");
		assert errors = 0 report integer'image(errors) & " errors" severity failure;
		report "tb_cpu_directed (" & ONLY & "): 0 errors";
		done <= true;
		std.env.finish;
	end process;
end architecture;
