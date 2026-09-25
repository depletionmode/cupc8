-- Formal properties of the chipset (BUS-004, MMU-004, SPI-004, CLK-002), proven by
-- SymbiYosys (soc/formal/chipset.sby). The assumptions describe the CPU card
-- as doc/hardware/cpu-bus.md specifies it; everything else is unconstrained.

vunit chipset_props(chipset(rtl)) {
	default clock is rising_edge(clk);

	-- stable()/rose() look one clock back: not meaningful at the first clock
	signal past_valid: std_logic := '0';
	process(clk) begin
		if rising_edge(clk) then past_valid <= '1'; end if;
	end process;

	-- the CPU card: a request (and its write data) holds still until /RDY;
	-- it resets synchronously, idling /STB from the next edge
	assume always (cpu_n_rst = '1' and cpu_n_stb = '0' and cpu_n_rdy = '1') ->
		next (cpu_n_stb = '0' and stable(cpu_a) and stable(cpu_rw) and stable(cpu_d_in) and stable(cpu_sync));
	assume always (cpu_n_rst = '0') -> next (cpu_n_stb = '1');

	---------------------------------------------------------------- BUS-004
	-- one D driver: the chipset drives D only to answer a CPU read
	bus_one_driver: assert always (cpu_d_oe = '1') -> (cpu_n_stb = '0' and cpu_rw = '1');
	-- /RDY only while /STB is low, and exactly one clock wide
	bus_rdy_in_cycle: assert always (cpu_n_rdy = '0') -> (cpu_n_stb = '0');
	bus_rdy_one_clock: assert always (cpu_n_rdy = '0') -> next (cpu_n_rdy = '1');
	-- the bridge and a CPU memory cycle are never granted together: an access
	-- keeps its owner and address from start to end, and a bridge completion
	-- never coincides with a CPU completion from memory
	bus_owner_held: assert always (past_valid = '1' and (mstate = m_2 or mstate = m_3)) ->
		(stable(m_owner_br) and stable(ma_r));
	bus_one_grant: assert always (br_ack = '1') -> (m_owner_br = '1');

	-- invariants that make the induction proof go through (each is itself
	-- checked): a cycle in progress is still requested, and /RDY is only
	-- pending for a cycle that was accepted
	inv_busy_requested: assert always (cyc_busy = '1') -> (cpu_n_stb = '0');
	inv_rdy_accepted: assert always (rdy_r = '0') -> (cyc_busy = '1');
	inv_rw_held: assert always (cyc_busy = '1') -> (cpu_rw = cyc_rw);

	---------------------------------------------------------------- MMU-004
	mmu_one_chip: assert always not (mem_n_ce_ram = '0' and mem_n_ce_rom = '0');
	mmu_no_fight: assert always not (mem_d_oe = '1' and mem_n_oe = '0');
	-- /WE low only with a steady address, set before it falls and held after it rises
	mmu_we_addr: assert always (past_valid = '1' and mem_n_we = '0') -> stable(mem_a);
	mmu_we_release: assert always (past_valid = '1' and rose(mem_n_we)) -> stable(mem_a);
	mmu_we_chip: assert always (mem_n_we = '0') -> (mem_n_ce_ram = '0' or mem_n_ce_rom = '0');
	-- invariants for the induction: /WE is low only in m_2, and a chip is
	-- selected through m_1 and m_2 of every access
	inv_mstate: assert always mstate = m_idle or mstate = m_1 or mstate = m_2 or mstate = m_3 or mstate = m_gap;
	inv_we_m2: assert always (mem_n_we = '0') -> (mstate = m_2);
	inv_doe_write: assert always (d_oe_r = '1') -> (m_we = '1');
	inv_noe_read: assert always (n_oe_r = '0') -> (m_we = '0');
	inv_ce_access: assert always (mstate = m_1 or mstate = m_2) -> (mem_n_ce_ram = '0' or mem_n_ce_rom = '0');

	---------------------------------------------------------------- MMU-004: the RAM window
	-- where a CPU memory access goes (checked as the controller starts it, in
	-- m_1, from the cycle's latched address): $8000-$bfff to {RAM_BANK,
	-- A[13:0]}; every other RAM address to {000, A}; the ROM windows to the
	-- ROM chip as before; I/O never to memory. RAM_BANK resets to 2 (the
	-- identity map).
	mmu_ram_window: assert always (mstate = m_1 and m_owner_br = '0' and m_rom = '0' and cyc_a(15 downto 14) = "10") ->
		(ma_r = unsigned(std_logic_vector'(ram_bank & cyc_a(13 downto 0))));
	mmu_ram_flat: assert always (mstate = m_1 and m_owner_br = '0' and m_rom = '0' and cyc_a(15 downto 14) /= "10") ->
		(ma_r = unsigned(std_logic_vector'("000" & cyc_a)));
	mmu_rom_fixed: assert always (mstate = m_1 and m_owner_br = '0' and m_rom = '1' and cyc_a(11) = '0') ->
		(cyc_a(15 downto 12) = x"e" and ma_r = unsigned(std_logic_vector'("00000000" & cyc_a(10 downto 0))));
	mmu_rom_banked: assert always (mstate = m_1 and m_owner_br = '0' and m_rom = '1' and cyc_a(11) = '1') ->
		(cyc_a(15 downto 12) = x"e" and ma_r = unsigned(std_logic_vector'(rom_bank & cyc_a(10 downto 0))));
	mmu_io_not_memory: assert always (mstate = m_1 and m_owner_br = '0') -> (cyc_a(15 downto 12) /= x"f");
	mmu_ram_bank_reset: assert always (rst = '1') -> next (ram_bank = "00010");

	---------------------------------------------------------------- SPI-004
	spi_one_cs: assert always onehot0(not spi_n_cs);

	---------------------------------------------------------------- CLK-002
	-- the millisecond counter and the tick (memory-map.md). Each value one
	-- clock back, and whether that clock was in reset.
	signal rst_q: std_logic := '1';
	signal ms_q: unsigned(31 downto 0) := (others => '0');
	signal div_q: unsigned(13 downto 0) := (others => '0');
	signal lat_q: std_logic_vector(23 downto 0) := (others => '0');
	signal p4_q: std_logic := '0';
	process(clk) begin
		if rising_edge(clk) then
			rst_q <= rst; ms_q <= ms_cnt; div_q <= ms_div; lat_q <= ms_lat; p4_q <= pending(4);
		end if;
	end process;

	-- the divider counts 0..11999 and the counter steps by one exactly as it
	-- wraps: 12000 clocks a millisecond
	clk_div_range: assert always ms_div < MS_CLOCKS;
	clk_tick_range: assert always tick_div < TICK_MS;
	clk_ms_rate: assert always (past_valid = '1' and rst_q = '0') ->
		((div_q /= MS_CLOCKS - 1 and ms_div = div_q + 1 and ms_cnt = ms_q) or
		 (div_q = MS_CLOCKS - 1 and ms_div = 0 and ms_cnt = ms_q + 1));
	clk_reset: assert always (rst = '1') -> next (ms_cnt = 0 and ms_div = 0 and tick_div = 0);
	-- a read of MS_COUNT0 answers bits 7:0 and latches bits 31:8 of one and
	-- the same value; nothing else moves the latch, and MS_COUNT1-3 read it
	clk_latch: assert always (rdy_r = '0' and cyc_rw = '1' and cyc_a = x"f206") ->
		(unsigned(std_logic_vector'(ms_lat & dout_r)) = ms_q);
	clk_latch_held: assert always (past_valid = '1' and rst_q = '0' and ms_lat /= lat_q) ->
		(rdy_r = '0' and cyc_rw = '1' and cyc_a = x"f206");
	clk_read1: assert always (rdy_r = '0' and cyc_rw = '1' and cyc_a = x"f207") -> (dout_r = ms_lat(7 downto 0));
	clk_read2: assert always (rdy_r = '0' and cyc_rw = '1' and cyc_a = x"f208") -> (dout_r = ms_lat(15 downto 8));
	clk_read3: assert always (rdy_r = '0' and cyc_rw = '1' and cyc_a = x"f209") -> (dout_r = ms_lat(23 downto 16));
	-- the tick is set only as the counter steps with tick_div wrapping (every
	-- 50th step), and always then unless that clock's W1C cleared it
	irq_tick_when: assert always (past_valid = '1' and rst_q = '0' and pending(4) = '1' and p4_q = '0') ->
		(ms_cnt /= ms_q and tick_div = 0);
	irq_tick_set: assert always (past_valid = '1' and rst_q = '0' and ms_cnt /= ms_q and tick_div = 0 and
		not (rdy_r = '0' and cyc_rw = '0' and cyc_a = x"f200" and cyc_d(4) = '1')) -> (pending(4) = '1');
	-- CPU IRQ line 3 is SPI complete or the tick, each by its own mask bit;
	-- lines 0-2 are bits 0-2 as before
	irq_line3: assert always cpu_irq(3) = ((pending(3) and mask(3)) or (pending(4) and mask(4)));
	irq_lines: assert always cpu_irq(2 downto 0) = (pending(2 downto 0) and mask(2 downto 0));
	irq_tick_reset: assert always (rst = '1') -> next (mask(4) = '0');
}
