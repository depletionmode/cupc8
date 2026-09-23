-- Formal properties of the chipset (BUS-004, MMU-004, SPI-004), proven by
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

	---------------------------------------------------------------- SPI-004
	spi_one_cs: assert always onehot0(not spi_n_cs);
}
