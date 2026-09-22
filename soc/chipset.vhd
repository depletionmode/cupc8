-- CUPC/8 chipset (main board FPGA): everything on the CPU bus except the CPU.
--
--   CPU bus front-end  doc/hardware/cpu-bus.md (answers every cycle, /RDY)
--   address decode     doc/hardware/memory-map.md (RAM, ROM windows, I/O)
--   memory controller  SRAM + ROM chip, 4-clock cycles; the bridge goes first
--   registers          GPO, SPI (via spi_master), IRQ, SLOT_IRQ, SYSCTL, ROM_BANK
--   bridge             sysctl's SPI port: memory access, CPU control, trace
--   stop/step/trace    via /RDY; every completed CPU cycle goes into a ring

library ieee;
use ieee.std_logic_1164.all;
use ieee.numeric_std.all;

entity chipset is
	port(
		clk:			in std_logic;
		n_por:			in std_logic;						-- power-on reset (sysctl)

		-- CPU bus
		cpu_a:			in std_logic_vector(15 downto 0);
		cpu_d_in:		in std_logic_vector(7 downto 0);	-- write data from the CPU
		cpu_d_out:		out std_logic_vector(7 downto 0);	-- read data to the CPU
		cpu_d_oe:		out std_logic;
		cpu_rw:			in std_logic;
		cpu_n_stb:		in std_logic;
		cpu_n_rdy:		out std_logic;
		cpu_sync:		in std_logic;
		cpu_irq:		out std_logic_vector(3 downto 0);
		cpu_tmr_exp:	in std_logic_vector(1 downto 0);
		cpu_halted:		in std_logic;
		cpu_waiting:	in std_logic;
		cpu_n_rst:		out std_logic;
		cpu_present:	in std_logic;						-- PRSNT2_n inverted
		cpu_card_id:	in std_logic_vector(1 downto 0);

		-- memory bus (SRAM + ROM chip)
		mem_a:			out std_logic_vector(18 downto 0);
		mem_d_in:		in std_logic_vector(7 downto 0);
		mem_d_out:		out std_logic_vector(7 downto 0);
		mem_d_oe:		out std_logic;
		mem_n_oe:		out std_logic;
		mem_n_we:		out std_logic;
		mem_n_ce_ram:	out std_logic;
		mem_n_ce_rom:	out std_logic;

		-- SPI to the slots (dev 0-5) and the aux header (dev 6)
		spi_sck:		out std_logic;
		spi_mosi:		out std_logic;
		spi_miso:		in std_logic;
		spi_n_cs:		out std_logic_vector(6 downto 0);
		slot_n_irq:		in std_logic_vector(5 downto 0);

		gpo:			out std_logic_vector(7 downto 0);

		-- bridge (sysctl)
		br_sck:			in std_logic;
		br_mosi:		in std_logic;
		br_miso:		out std_logic;
		br_n_cs:		in std_logic
	);
end entity;

architecture rtl of chipset is
	signal rst: std_logic := '1';
	signal por_cnt: unsigned(4 downto 0) := (others => '0');

	-- CPU front-end
	signal cyc_busy: std_logic := '0';
	signal cyc_a: std_logic_vector(15 downto 0) := (others => '0');
	signal cyc_rw, cyc_sync: std_logic := '1';
	signal cyc_d: std_logic_vector(7 downto 0) := x"00";
	signal rdy_r: std_logic := '1';
	signal dout_r: std_logic_vector(7 downto 0) := x"00";

	-- memory controller
	type mstate_t is (m_idle, m_1, m_2, m_3, m_gap);
	signal mstate: mstate_t := m_idle;
	signal m_owner_br, m_we, m_rom: std_logic := '0';
	signal ma_r: unsigned(18 downto 0) := (others => '0');
	signal md_r: std_logic_vector(7 downto 0) := x"00";
	signal n_oe_r, n_we_r, n_ce_ram_r, n_ce_rom_r: std_logic := '1';
	signal d_oe_r: std_logic := '0';

	-- registers
	signal gpo_r: std_logic_vector(7 downto 0) := x"00";
	type byte8_t is array(0 to 7) of std_logic_vector(7 downto 0);
	signal spi_tx, spi_rx, spi_cfg: byte8_t := (others => x"00");
	signal spi_hold: std_logic_vector(7 downto 0) := x"00";
	signal pending, mask: std_logic_vector(3 downto 0) := "0000";
	signal rom_off: std_logic := '0';
	signal rom_bank: std_logic_vector(7 downto 0) := x"00";
	signal slot_s1, slot_s2: std_logic_vector(5 downto 0) := (others => '0');
	signal slot_any_d: std_logic := '0';

	-- SPI master
	signal spi_start, spi_busy, spi_done: std_logic := '0';
	signal spi_dev, spi_cur: unsigned(2 downto 0) := "000";
	signal spi_rxb: std_logic_vector(7 downto 0);
	signal spi_cs8: std_logic_vector(7 downto 0);

	-- bridge
	signal br_req, br_we, br_rom, br_ack, br_ctl_wr, br_pop, br_drain: std_logic := '0';
	signal br_addr: unsigned(18 downto 0);
	signal br_wdata, br_rdata, br_ctl, br_status: std_logic_vector(7 downto 0) := x"00";

	-- stop / step
	signal step_instr, step_cycle, step_seen_sync: std_logic := '0';

	-- trace ring: {flags, data, addr hi, addr lo}
	type ring_t is array(0 to 511) of std_logic_vector(31 downto 0);
	signal ring: ring_t;
	signal tr_wr, tr_rd: unsigned(8 downto 0) := (others => '0');
	signal tr_count: unsigned(9 downto 0) := (others => '0');
	signal tr_data: std_logic_vector(31 downto 0) := (others => '0');
	signal tr_ovf: std_logic := '0';

	signal spi_tx_sel, spi_cfg_sel: std_logic_vector(7 downto 0);
begin
	cpu_n_rdy <= rdy_r;
	cpu_d_out <= dout_r;
	cpu_d_oe <= '1' when rdy_r = '0' and cyc_rw = '1' else '0';
	cpu_irq <= pending and mask;
	cpu_n_rst <= '0' when rst = '1' or br_ctl(6) = '1' else '1';

	mem_a <= std_logic_vector(ma_r);
	mem_d_out <= md_r;
	mem_d_oe <= d_oe_r;
	mem_n_oe <= n_oe_r;
	mem_n_we <= n_we_r;
	mem_n_ce_ram <= n_ce_ram_r;
	mem_n_ce_rom <= n_ce_rom_r;

	gpo <= gpo_r;
	spi_n_cs <= spi_cs8(6 downto 0);

	br_status <= rst & (cpu_present and not cpu_n_stb) & cpu_card_id & cpu_present &
				 cpu_waiting & cpu_halted &
				 (br_ctl(0) and not step_instr and not step_cycle);

	spi_tx_sel <= spi_tx(to_integer(spi_dev));
	spi_cfg_sel <= spi_cfg(to_integer(spi_dev));

	spi0: entity work.spi_master port map(
		clk => clk, rst => rst, start => spi_start, dev => spi_dev,
		tx => spi_tx_sel, cpol => spi_cfg_sel(1), cpha => spi_cfg_sel(2),
		div => unsigned(spi_cfg_sel(7 downto 3)),
		hold => spi_hold, busy => spi_busy, done => spi_done, rx => spi_rxb,
		sck => spi_sck, mosi => spi_mosi, miso => to_x01(spi_miso), n_cs => spi_cs8);

	br0: entity work.bridge port map(
		clk => clk, rst => rst, sck => br_sck, mosi => br_mosi, miso => br_miso, n_cs => br_n_cs,
		req => br_req, req_we => br_we, req_rom => br_rom, req_addr => br_addr,
		req_wdata => br_wdata, ack => br_ack, rdata => br_rdata,
		status => br_status, gpo => gpo_r, cpu_ctl => br_ctl, ctl_wr => br_ctl_wr,
		tr_count => tr_count, tr_data => tr_data, tr_lost => tr_ovf, tr_pop => br_pop,
		tr_drain => br_drain);

	process(clk)
		variable a: unsigned(15 downto 0);
		variable dev: natural range 0 to 15;
		variable reg: std_logic_vector(3 downto 0);
		variable rd: std_logic_vector(7 downto 0);
		variable p: std_logic_vector(3 downto 0);
		variable accept, is_io: boolean;
		variable phys: unsigned(18 downto 0);
		variable rom: std_logic;
		variable slot_any: std_logic;
		variable entry: std_logic_vector(31 downto 0);
		variable tr_push, tr_pop: boolean;
	begin
		if rising_edge(clk) then
			-- power-on reset: hold everything (and the CPU) for 16 clocks
			if n_por = '0' then
				por_cnt <= (others => '0');
				rst <= '1';
			elsif por_cnt /= 16 then
				por_cnt <= por_cnt + 1;
				rst <= '1';
			else
				rst <= '0';
			end if;

			spi_start <= '0';
			br_ack <= '0';
			tr_push := false;
			tr_pop := false;
			p := pending;
			tr_data <= ring(to_integer(tr_rd));

			if rst = '1' then
				cyc_busy <= '0'; rdy_r <= '1'; mstate <= m_idle;
				n_oe_r <= '1'; n_we_r <= '1'; n_ce_ram_r <= '1'; n_ce_rom_r <= '1'; d_oe_r <= '0';
				gpo_r <= x"00"; spi_hold <= x"00"; p := "0000"; mask <= "0000";
				rom_off <= '0'; rom_bank <= x"00";
				step_instr <= '0'; step_cycle <= '0';
				tr_wr <= (others => '0'); tr_rd <= (others => '0'); tr_count <= (others => '0');
				tr_ovf <= '0';
			else
				------------------------------------------------------------ IRQ sources
				slot_s1 <= not slot_n_irq;
				slot_s2 <= slot_s1;
				slot_any := '0';
				for i in 0 to 5 loop slot_any := slot_any or slot_s2(i); end loop;
				if slot_any = '1' and slot_any_d = '0' then p(0) := '1'; end if;
				slot_any_d <= slot_any;
				if cpu_tmr_exp(0) = '1' then p(1) := '1'; end if;
				if cpu_tmr_exp(1) = '1' then p(2) := '1'; end if;
				if spi_done = '1' then
					p(3) := '1';
					spi_rx(to_integer(spi_cur)) <= spi_rxb;
				end if;

				------------------------------------------------------------ stop / step
				if br_ctl_wr = '1' then
					if br_ctl(1) = '1' then step_instr <= '1'; step_seen_sync <= '0'; end if;
					if br_ctl(2) = '1' then step_cycle <= '1'; end if;
				end if;

				------------------------------------------------------------ CPU front-end
				if rdy_r = '0' then
					-- the CPU samples /RDY at this edge: the cycle completes; trace it
					rdy_r <= '1';
					cyc_busy <= '0';
					if cyc_rw = '1' then entry(23 downto 16) := dout_r;
					else entry(23 downto 16) := cyc_d;
					end if;
					entry(15 downto 0) := cyc_a;
					entry(31 downto 24) := "000000" & cyc_sync & cyc_rw;
					ring(to_integer(tr_wr)) <= entry;
					tr_wr <= tr_wr + 1;
					tr_push := true;
				elsif cyc_busy = '0' and cpu_n_stb = '0' then
					-- may we take a new cycle?
					accept := br_req = '0' and mstate = m_idle;
					if br_ctl(0) = '1' then
						if step_cycle = '1' then
							if accept then step_cycle <= '0'; end if;
						elsif step_instr = '1' then
							if cpu_sync = '1' and step_seen_sync = '1' then
								accept := false;		-- the next instruction: stop here
								step_instr <= '0';
							elsif accept and cpu_sync = '1' then
								step_seen_sync <= '1';
							end if;
						else
							accept := false;
						end if;
					end if;

					if accept then
						cyc_busy <= '1';
						cyc_a <= cpu_a;
						cyc_rw <= cpu_rw;
						cyc_d <= cpu_d_in;
						cyc_sync <= cpu_sync;
						a := unsigned(cpu_a);
						is_io := a(15 downto 12) = x"f";
						rom := '0';
						if a < x"e000" then
							phys := "000" & a;
						elsif a(15 downto 12) = x"e" and rom_off = '1' then
							phys := "000" & a;
						elsif a(15 downto 12) = x"e" then
							rom := '1';
							if a(11) = '0' then phys := "00000000" & a(10 downto 0);
							else phys := unsigned(rom_bank) & a(10 downto 0);
							end if;
						end if;

						if is_io then
							-- registers answer at once
							dev := to_integer(a(7 downto 4));
							reg := std_logic_vector(a(3 downto 0));
							rd := x"00";
							case a(11 downto 8) is
							when x"0" =>
								if a(7 downto 0) = x"00" then
									rd := gpo_r;
									if cpu_rw = '0' then gpo_r <= cpu_d_in; end if;
								end if;
							when x"1" =>
								if dev < 8 then
									case reg is
									when x"0" =>
										if cpu_rw = '0' then spi_tx(dev) <= cpu_d_in; end if;
									when x"1" =>
										rd := spi_rx(dev);
									when x"2" =>
										if cpu_rw = '0' and spi_busy = '0' then
											spi_dev <= to_unsigned(dev, 3);
											spi_cur <= to_unsigned(dev, 3);
											spi_start <= '1';
										end if;
									when x"3" =>
										rd := "0000000" & not (spi_busy or spi_start);
									when x"4" =>
										rd := "0000000" & spi_hold(dev);
										if cpu_rw = '0' then
											if cpu_d_in(0) = '1' then
												spi_hold <= (others => '0');
												spi_hold(dev) <= '1';
											elsif spi_hold(dev) = '1' then
												spi_hold <= (others => '0');
											end if;
										end if;
									when x"f" =>
										if cpu_rw = '0' then spi_cfg(dev) <= cpu_d_in; end if;
									when others => null;
									end case;
								end if;
							when x"2" =>
								case a(7 downto 0) is
								when x"00" =>
									rd := "0000" & p;
									if cpu_rw = '0' then p := p and not cpu_d_in(3 downto 0); end if;
								when x"01" =>
									rd := "0000" & mask;
									if cpu_rw = '0' then mask <= cpu_d_in(3 downto 0); end if;
								when x"02" =>
									rd := "00" & slot_s2;
								when x"03" =>
									rd := "0000000" & rom_off;
									if cpu_rw = '0' then rom_off <= cpu_d_in(0); end if;
								when x"04" =>
									rd := rom_bank;
									if cpu_rw = '0' then rom_bank <= cpu_d_in; end if;
								when others => null;
								end case;
							when others => null;
							end case;
							dout_r <= rd;
							rdy_r <= '0';
						elsif rom = '1' and cpu_rw = '0' then
							rdy_r <= '0';				-- CPU writes to the ROM are ignored
						else
							-- to the memory controller
							ma_r <= phys;
							m_rom <= rom;
							m_we <= not cpu_rw;
							md_r <= cpu_d_in;
							m_owner_br <= '0';
							mstate <= m_1;
							n_ce_ram_r <= rom;
							n_ce_rom_r <= not rom;
							n_oe_r <= not cpu_rw;
							d_oe_r <= not cpu_rw;
						end if;
					end if;
				end if;

				------------------------------------------------------------ memory controller
				case mstate is
				when m_idle =>
					if br_req = '1' then
						-- the bridge goes first (the CPU front-end holds off above)
						m_owner_br <= '1';
						m_rom <= br_rom;
						m_we <= br_we;
						if br_rom = '1' then ma_r <= br_addr;
						else ma_r <= "000" & br_addr(15 downto 0);
						end if;
						md_r <= br_wdata;
						n_ce_ram_r <= br_rom;
						n_ce_rom_r <= not br_rom;
						n_oe_r <= br_we;
						d_oe_r <= br_we;
						mstate <= m_1;
					end if;
				when m_1 =>
					if m_we = '1' then n_we_r <= '0'; end if;
					mstate <= m_2;
				when m_2 =>
					-- two full clocks since the address went out: data is valid
					n_we_r <= '1';
					if m_owner_br = '1' then
						br_rdata <= mem_d_in;
						br_ack <= '1';
					else
						dout_r <= mem_d_in;
						rdy_r <= '0';
					end if;
					if m_we = '1' then
						mstate <= m_3;				-- hold data/CE one more clock (tDH)
					else
						n_oe_r <= '1'; n_ce_ram_r <= '1'; n_ce_rom_r <= '1';
						mstate <= m_gap;
					end if;
				when m_3 =>
					n_ce_ram_r <= '1'; n_ce_rom_r <= '1'; d_oe_r <= '0';
					mstate <= m_gap;
				when m_gap =>
					-- one idle clock: the bridge drops req after seeing ack
					mstate <= m_idle;
				end case;

				------------------------------------------------------------ trace ring
				tr_pop := br_pop = '1' and tr_count /= 0;
				if br_drain = '1' then
					tr_ovf <= '0';				-- reported in this drain's header
				end if;
				if tr_push and tr_count = 512 then
					-- full: the new entry replaces the oldest
					tr_rd <= tr_rd + 1;
					tr_ovf <= '1';
				elsif tr_push and not tr_pop then
					tr_count <= tr_count + 1;
				elsif tr_pop and not tr_push then
					tr_rd <= tr_rd + 1;
					tr_count <= tr_count - 1;
				elsif tr_push and tr_pop then
					tr_rd <= tr_rd + 1;			-- one in, one out
				end if;
			end if;
			pending <= p;
		end if;
	end process;
end architecture;
