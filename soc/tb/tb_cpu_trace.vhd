-- Lockstep trace testbench for cpu.vhd (tests CPU-001, BUS-001, BUS-003).
--
-- A chipset model answers the CPU bus (doc/hardware/cpu-bus.md): 64 KB RAM,
-- IRQ_PEND/IRQ_MASK at $f200/$f201, TMR_EXP latching, and WAITS wait states
-- per cycle (WAITS < 0: random 0..15 from SEED). It prints the same trace as
-- tools/simtrace.nim:
--
--   S pppp r0 r1 f ssss   state at each opcode fetch, f = I<<1 | Z
--   W aaaa dd             each completed write cycle
--   E halt|end|limit      why the run stopped
--
-- The CPU resets to $e000; a `b $1000` planted there reaches the image, and
-- tracing starts at the first fetch from $1000 (where sim.nim starts).
--
-- BUS-003 options: STALL > 0 adds, to one cycle in eight, a stall of up to
-- STALL clocks. RESET_AT > 0 pulls /CPU_RST in the middle of a bus cycle once,
-- at that cycle count or at the HALT fetch if that comes first; memory goes
-- back to the image and only the run after the reset is traced, so it must
-- match sim.nim exactly.

library ieee;
use ieee.std_logic_1164.all;
use ieee.numeric_std.all;
use std.textio.all;

entity tb_cpu_trace is
	generic(
		IMAGE:		string := "image.hex";	-- one hex byte per line, loaded at $1000
		WAITS:		integer := 0;
		SEED:		natural := 1;
		MAX_CYCLES:	natural := 20_000_000;
		STALL:		natural := 0;
		RESET_AT:	natural := 0
	);
end entity;

architecture sim of tb_cpu_trace is
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
	signal pending, mask: std_logic_vector(3 downto 0) := "0000";

	function hx(v: std_logic_vector) return string is
		constant digits: string(1 to 16) := "0123456789abcdef";
		constant vv: std_logic_vector(v'length - 1 downto 0) := v;
		variable r: string(1 to (v'length + 3) / 4);
		variable nib: std_logic_vector(3 downto 0);
		variable hi: integer;
	begin
		for i in r'range loop
			hi := v'length - 1 - (i - 1) * 4;
			nib := (others => '0');
			for b in 0 to 3 loop
				if hi - 3 + b >= 0 then nib(b) := vv(hi - 3 + b); end if;
			end loop;
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
		variable loaded, started, busy: boolean := false;
		variable image_end: natural := 16#1000#;
		variable cyc_a: natural;
		variable cyc_rw: std_logic;
		variable cyc_d: std_logic_vector(7 downto 0);
		variable count: integer;
		variable lfsr: unsigned(15 downto 0) := to_unsigned(SEED mod 65535 + 1, 16);
		variable cycles: natural := 0;
		variable p: std_logic_vector(3 downto 0);
		file f: text;
		variable l: line;
		variable b: std_logic_vector(7 downto 0);
		variable ld: natural := 16#1000#;
		variable op: std_logic_vector(7 downto 0);
		variable mem_at_power_on: mem_t;		-- for RESET_AT (not "image": VHDL would take it for IMAGE)
		variable rst_count: natural := 5;		-- clocks of /CPU_RST still to hold
		variable reset_done: boolean := RESET_AT = 0;
	begin
		if not loaded then
			loaded := true;
			mem(16#e000#) := x"b0"; mem(16#e001#) := x"00"; mem(16#e002#) := x"10";
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
			image_end := ld;
			mem_at_power_on := mem;
		end if;

		if rising_edge(clk) and not done then
			cycles := cycles + 1;
			p := pending;
			if rst_count > 0 then
				rst_count := rst_count - 1;
				n_rst <= '0';
			else
				n_rst <= '1';
			end if;
			d_in <= (others => 'X');
			n_rdy <= '1';

			if n_rdy = '0' then
				-- the CPU samples /RDY at this edge: the cycle completes
				busy := false;
				if cyc_rw = '0' then
					if started then emit("W " & hx(std_logic_vector(to_unsigned(cyc_a, 16))) & " " & hx(cyc_d)); end if;
					if cyc_a = 16#f200# then
						p := p and not cyc_d(3 downto 0);		-- write 1 to clear
					elsif cyc_a = 16#f201# then
						mask <= cyc_d(3 downto 0);
					end if;
					mem(cyc_a) := cyc_d;
				end if;
			elsif not busy and n_stb = '0' and n_rst = '1' then
				-- a new cycle: sample it
				busy := true;
				cyc_a := to_integer(unsigned(a));
				cyc_rw := rw;
				cyc_d := d_out;
				if rw = '0' then
					assert d_oe = '1' report "write cycle without D driven" severity failure;
				else
					assert d_oe = '0' report "CPU drives D in a read cycle" severity failure;
				end if;
				if WAITS >= 0 then
					count := WAITS;
				else
					lfsr := lfsr(14 downto 0) & (lfsr(15) xor lfsr(13) xor lfsr(12) xor lfsr(10));
					count := to_integer(lfsr(3 downto 0));
				end if;
				if STALL > 0 then
					lfsr := lfsr(14 downto 0) & (lfsr(15) xor lfsr(13) xor lfsr(12) xor lfsr(10));
					if lfsr(2 downto 0) = "000" then
						count := count + to_integer(lfsr(15 downto 8)) mod (STALL + 1);
					end if;
				end if;
				-- BUS-003: one reset in the middle of a cycle, then a clean rerun
				if not reset_done and (cycles >= RESET_AT or
				                      (sync = '1' and mem(cyc_a)(7 downto 3) = "11111")) then
					reset_done := true;
					emit("R reset in the cycle at $" & hx(std_logic_vector(to_unsigned(cyc_a, 16))) &
						 ", clock " & integer'image(cycles));
					rst_count := 3;
					n_rst <= '0';
					busy := false;
					started := false;
					mem := mem_at_power_on;
					p := "0000";
					mask <= "0000";
				end if;
				if sync = '1' and busy then
					if pc = x"1000" and reset_done then started := true; end if;
					if started then
						emit("S " & hx(pc) & " " & hx(r0) & " " & hx(r1) & " " &
							 hx("00" & fl) & " " & hx(sp));
						if cyc_a >= image_end then
							emit("E end"); done <= true;
						else
							op := mem(cyc_a);
							if op(7 downto 3) = "11111" then
								emit("E halt"); done <= true;
							end if;
						end if;
					end if;
				end if;
			elsif busy then
				-- protocol monitor: the request must hold still until /RDY
				assert n_stb = '0' and to_integer(unsigned(a)) = cyc_a and rw = cyc_rw
					report "CPU changed the request before /RDY" severity failure;
			end if;

			if busy and n_rdy = '1' then
				if count <= 0 then
					n_rdy <= '0';
					if cyc_rw = '1' then
						if cyc_a = 16#f200# then d_in <= "0000" & p;
						elsif cyc_a = 16#f201# then d_in <= "0000" & mask;
						else d_in <= mem(cyc_a);
						end if;
					end if;
				else
					count := count - 1;
				end if;
			end if;

			if tmr_exp(0) = '1' then p(1) := '1'; end if;
			if tmr_exp(1) = '1' then p(2) := '1'; end if;
			pending <= p;

			if cycles >= MAX_CYCLES then
				emit("E limit"); done <= true;
			end if;
		end if;
	end process;
end architecture;
