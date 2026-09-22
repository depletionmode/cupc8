-- Bus bridge: SPI slave to the sysctl RP2040 (doc/hardware/memory-map.md,
-- "In-system programming"). Mode 0, ≤ 1 MHz, oversampled by clk.
--
-- Byte timing: when byte k completes, the MISO shifter loads `tx_next`, the
-- byte for slot k+1. Anything the state machine decides while handling byte
-- k therefore lands in slot k+2 at the earliest; that is why every response
-- is preceded by one dummy byte.
--
-- Memory accesses go to the chipset through req/ack. The chipset serves them
-- ahead of the CPU, which stalls until the bridge is done.

library ieee;
use ieee.std_logic_1164.all;
use ieee.numeric_std.all;

entity bridge is
	port(
		clk:		in std_logic;
		rst:		in std_logic;
		-- SPI slave (asynchronous to clk)
		sck:		in std_logic;
		mosi:		in std_logic;
		miso:		out std_logic;
		n_cs:		in std_logic;
		-- memory requests to the chipset
		req:		out std_logic;
		req_we:		out std_logic;
		req_rom:	out std_logic;					-- 1 = ROM chip, 0 = SRAM
		req_addr:	out unsigned(18 downto 0);
		req_wdata:	out std_logic_vector(7 downto 0);
		ack:		in std_logic;					-- pulse: access done
		rdata:		in std_logic_vector(7 downto 0);
		-- control and status
		status:		in std_logic_vector(7 downto 0);
		gpo:		in std_logic_vector(7 downto 0);
		cpu_ctl:	out std_logic_vector(7 downto 0);	-- bits 0 and 6 are levels
		ctl_wr:		out std_logic;						-- pulse when CPU_CTL was written
		-- trace ring read port
		tr_count:	in unsigned(9 downto 0);		-- entries waiting (0..512)
		tr_data:	in std_logic_vector(31 downto 0);	-- oldest entry
		tr_lost:	in std_logic;					-- entries were dropped since the last drain
		tr_pop:		out std_logic;
		tr_drain:	out std_logic					-- pulse: a drain started (clears tr_lost)
	);
end entity;

architecture rtl of bridge is
	signal sck_s, mosi_s, cs_s: std_logic_vector(2 downto 0) := "000";
	signal rx_sh, tx_sh, tx_next: std_logic_vector(7 downto 0) := x"00";
	signal bits: unsigned(2 downto 0) := "000";

	type state_t is (st_cmd, st_arg, st_wdata, st_stream_mem, st_stream_trace, st_ctl, st_ignore);
	signal state: state_t := st_cmd;
	signal cmd: std_logic_vector(7 downto 0) := x"00";
	signal argn: unsigned(2 downto 0) := "000";			-- argument bytes received
	signal addr: unsigned(23 downto 0) := (others => '0');
	signal len: unsigned(8 downto 0) := (others => '0');	-- bytes still to move
	signal req_r, we_r, rom_r: std_logic := '0';
	signal wdata_r: std_logic_vector(7 downto 0) := x"00";
	signal ctl_r: std_logic_vector(7 downto 0) := x"00";
	signal ctl_wr_r, pop_r, drain_r: std_logic := '0';
	signal lost_r: std_logic := '0';
	signal tcount: unsigned(9 downto 0) := (others => '0');	-- trace entries to stream
	signal tbyte: unsigned(1 downto 0) := "00";
	signal thdr: unsigned(1 downto 0) := "00";				-- trace header bytes left
begin
	miso <= tx_sh(7);
	req <= req_r;
	req_we <= we_r;
	req_rom <= rom_r;
	req_addr <= addr(18 downto 0);
	req_wdata <= wdata_r;
	cpu_ctl <= ctl_r;
	ctl_wr <= ctl_wr_r;
	tr_pop <= pop_r;
	tr_drain <= drain_r;

	process(clk)
		variable rise, fall, byte_done: boolean;
		variable b: std_logic_vector(7 downto 0);

		-- the byte after next (see header)
		procedure respond(v: std_logic_vector(7 downto 0)) is
		begin
			tx_next <= v;
		end procedure;

		procedure mem_access(write: std_logic) is
		begin
			req_r <= '1';
			we_r <= write;
			rom_r <= '1' when cmd = x"03" or cmd = x"04" else '0';
		end procedure;

		function trace_byte(e: std_logic_vector(31 downto 0); i: unsigned(1 downto 0))
				return std_logic_vector is
		begin
			case to_integer(i) is
				when 0 => return e(7 downto 0);		-- addr lo
				when 1 => return e(15 downto 8);	-- addr hi
				when 2 => return e(23 downto 16);	-- data
				when others => return e(31 downto 24);	-- flags
			end case;
		end function;
	begin
		if rising_edge(clk) then
			sck_s <= sck_s(1 downto 0) & sck;
			mosi_s <= mosi_s(1 downto 0) & mosi;
			cs_s <= cs_s(1 downto 0) & n_cs;
			ctl_wr_r <= '0';
			pop_r <= '0';
			drain_r <= '0';

			if ack = '1' then
				req_r <= '0';
				if we_r = '0' then
					respond(rdata);				-- next data byte for the stream
				end if;
			end if;

			rise := sck_s(2) = '0' and sck_s(1) = '1';
			fall := sck_s(2) = '1' and sck_s(1) = '0';
			byte_done := false;

			if rst = '1' or cs_s(1) = '1' then
				bits <= "000";
				state <= st_cmd;
				tx_sh <= x"00";
				tx_next <= x"00";
			else
				if rise then
					b := rx_sh(6 downto 0) & mosi_s(1);
					rx_sh <= b;
					bits <= bits + 1;
					if bits = 7 then
						byte_done := true;
						tx_sh <= tx_next;		-- the next slot's byte
						tx_next <= x"00";
					end if;
				elsif fall and bits /= 0 then
					tx_sh <= tx_sh(6 downto 0) & '0';
				end if;

				if byte_done then
					case state is
					when st_cmd =>
						cmd <= b;
						argn <= "000";
						addr <= (others => '0');
						case b is
							when x"01" | x"02" | x"03" | x"04" => state <= st_arg;
							when x"05" => respond(status);
							when x"06" => respond(gpo);
							when x"07" => state <= st_ctl;
							when x"08" =>
								-- snapshot how many entries this drain will return; the
								-- count's low byte goes out right after the dummy byte
								tcount <= tr_count;
								lost_r <= tr_lost;
								drain_r <= '1';
								respond(std_logic_vector(tr_count(7 downto 0)));
								thdr <= "01";
								tbyte <= "00";
								state <= st_stream_trace;
							when others => state <= st_ignore;
						end case;

					when st_arg =>
						argn <= argn + 1;
						if (cmd = x"01" or cmd = x"02") then
							-- addr16, len8
							case to_integer(argn) is
								when 0 => addr(7 downto 0) <= unsigned(b);
								when 1 => addr(15 downto 8) <= unsigned(b);
								when others =>
									len <= resize(unsigned(b), 9) + 1;
									if cmd = x"01" then
										state <= st_wdata;
									else
										mem_access('0');			-- data 0 for the slot after the dummy
										state <= st_stream_mem;
									end if;
							end case;
						else
							-- addr24, then len8 (ROM_RD) or data8 (ROM_BUSW)
							case to_integer(argn) is
								when 0 => addr(7 downto 0) <= unsigned(b);
								when 1 => addr(15 downto 8) <= unsigned(b);
								when 2 => addr(23 downto 16) <= unsigned(b);
								when others =>
									if cmd = x"04" then
										wdata_r <= b;
										mem_access('1');
										state <= st_ignore;
									else
										len <= resize(unsigned(b), 9) + 1;
										mem_access('0');
										state <= st_stream_mem;
									end if;
							end case;
						end if;

					when st_wdata =>
						if len /= 0 then
							wdata_r <= b;
							mem_access('1');
							len <= len - 1;
						end if;

					when st_stream_mem =>
						-- this byte was the dummy or data i-1; data i is in tx_next.
						-- advance and fetch the byte for the slot after next.
						if len > 1 then
							addr <= addr + 1;
							len <= len - 1;
						else
							len <= (others => '0');
							state <= st_ignore;
						end if;

					when st_stream_trace =>
						if thdr = "01" then
							respond(lost_r & "00000" & std_logic_vector(tcount(9 downto 8)));
							thdr <= "00";
						elsif tcount /= 0 then
							respond(trace_byte(tr_data, tbyte));
							tbyte <= tbyte + 1;
							if tbyte = 3 then
								pop_r <= '1';
								tcount <= tcount - 1;
							end if;
						end if;

					when st_ctl =>
						ctl_r <= b;
						ctl_wr_r <= '1';
						state <= st_ignore;

					when st_ignore =>
						null;
					end case;
				end if;
			end if;

			-- RAM_WR: the address advances after each write completes
			if ack = '1' and we_r = '1' and state = st_wdata then
				addr <= addr + 1;
			end if;
			-- RAM_RD / ROM_RD: after each byte boundary, fetch the next address
			if byte_done and state = st_stream_mem and len > 1 then
				req_r <= '1';
				we_r <= '0';
			end if;
		end if;
	end process;
end architecture;
