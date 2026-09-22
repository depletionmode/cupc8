-- CUPC/8 CPU (the CPU card logic).
--
-- ISA: doc/CUPC8 Manual.md §3 (reference model: tools/sim.nim).
-- Bus: doc/hardware/cpu-bus.md. Every memory access is one /STB-/RDY
-- handshake, so the chipset (or a testbench) can insert any number of wait
-- states; nothing here assumes memory timing.
--
-- Each instruction runs:
--   fetch opcode (SYNC) → [immediate | 16-bit address | indirect pointer]
--   → execute → [one data read or write] → timer tick → IRQ check.
-- The two clocks between the timer tick and the IRQ check give the chipset
-- time to latch TMR_EXP into IRQ_PEND. An IRQ raised by an instruction (a
-- timer expiring, a store to $f200/$f201) is therefore seen at that same
-- instruction boundary, as in sim.nim.

library ieee;
use ieee.std_logic_1164.all;
use ieee.numeric_std.all;

entity cpu is
	port(
		clk:		in std_logic;
		n_rst:		in std_logic;

		-- CPU bus
		a:			out std_logic_vector(15 downto 0);
		d_in:		in std_logic_vector(7 downto 0);
		d_out:		out std_logic_vector(7 downto 0);
		d_oe:		out std_logic;						-- drive D (write cycles only)
		rw:			out std_logic;						-- 1 = read
		n_stb:		out std_logic;
		n_rdy:		in std_logic;
		sync:		out std_logic;						-- opcode-fetch cycle
		irq:		in std_logic_vector(3 downto 0);	-- pending & mask
		tmr_exp:	out std_logic_vector(1 downto 0);
		halted:		out std_logic;
		waiting:	out std_logic;

		-- architectural state for testbenches; left open in hardware
		dbg_pc:		out std_logic_vector(15 downto 0);
		dbg_sp:		out std_logic_vector(15 downto 0);
		dbg_r0:		out std_logic_vector(7 downto 0);
		dbg_r1:		out std_logic_vector(7 downto 0);
		dbg_f:		out std_logic_vector(1 downto 0)	-- I & Z
	);
end entity;

architecture rtl of cpu is
	type state_t is (
		s_reset, s_fetch, s_imm, s_addr_lo, s_addr_hi, s_ptr_lo, s_ptr_hi,
		s_exec, s_mem_rd, s_mem_wr, s_tick, s_settle, s_check,
		s_irq_h, s_irq_l, s_irq_f, s_vec_lo, s_vec_hi, s_halt);
	signal state: state_t := s_reset;

	signal r0, r1:		unsigned(7 downto 0) := x"00";
	signal pc:			unsigned(15 downto 0) := x"e000";
	signal sp:			unsigned(15 downto 0) := x"0100";
	signal zf, iflag:	std_logic := '0';
	signal pcl:			unsigned(7 downto 0) := x"00";		-- latch for `pop pcl`
	signal ir:			std_logic_vector(7 downto 0) := x"80";
	signal imm:			unsigned(7 downto 0) := x"00";
	signal ea:			unsigned(15 downto 0) := x"0000";	-- address operand / pointer
	signal lo:			unsigned(7 downto 0) := x"00";
	signal tmr0, tmr1:	unsigned(7 downto 0) := x"00";
	signal wait_r:		std_logic := '0';
	signal irq_n:		unsigned(1 downto 0) := "00";

	-- bus output registers
	signal a_r:			unsigned(15 downto 0) := x"ffff";
	signal dout_r:		std_logic_vector(7 downto 0) := x"00";
	signal oe_r, sync_r: std_logic := '0';
	signal rw_r, stb_r:	std_logic := '1';
	signal exp_r:		std_logic_vector(1 downto 0) := "00";

	-- ALU
	signal alu_a, alu_b, alu_r: unsigned(7 downto 0);
	signal alu_z, alu_wr, alu_wz: std_logic;

	-- instruction classes (opcode bits 7..3)
	constant OP_MOV:  std_logic_vector(4 downto 0) := "10001";	-- $88
	constant OP_PUSH: std_logic_vector(4 downto 0) := "10010";	-- $90
	constant OP_POP:  std_logic_vector(4 downto 0) := "10011";	-- $98
	constant OP_LD:   std_logic_vector(4 downto 0) := "10100";	-- $a0
	constant OP_ST:   std_logic_vector(4 downto 0) := "10101";	-- $a8
	constant OP_LDD:  std_logic_vector(4 downto 0) := "01110";	-- $70
	constant OP_STD:  std_logic_vector(4 downto 0) := "01111";	-- $78
	constant OP_B:    std_logic_vector(4 downto 0) := "10110";	-- $b0
	constant OP_BZF:  std_logic_vector(4 downto 0) := "10111";	-- $b8
	constant OP_CLI:  std_logic_vector(4 downto 0) := "11000";	-- $c0
	constant OP_STI:  std_logic_vector(4 downto 0) := "11001";	-- $c8
	constant OP_TMR0: std_logic_vector(4 downto 0) := "11100";	-- $e0
	constant OP_TMR1: std_logic_vector(4 downto 0) := "11101";	-- $e8
	constant OP_WAI:  std_logic_vector(4 downto 0) := "11110";	-- $f0
	constant OP_HALT: std_logic_vector(4 downto 0) := "11111";	-- $f8

	function is_alu(op: std_logic_vector(4 downto 0)) return boolean is
	begin
		case op is
			when "00000" | "00001" | "00010" | "00011" | "00100" | "00110" |
				 "00111" | "01000" | "01001" | "01100" | "01101" => return true;
			when others => return false;
		end case;
	end function;

	-- opcodes whose bit 2 means "an immediate byte follows"
	function takes_imm(op: std_logic_vector(7 downto 0)) return boolean is
		constant cls: std_logic_vector(4 downto 0) := op(7 downto 3);
	begin
		if op(2) = '0' then
			return false;
		elsif is_alu(cls) or cls = OP_MOV or cls = OP_TMR0 or cls = OP_TMR1 then
			return true;
		elsif cls = OP_PUSH then
			return op(1) = '0';		-- push pch/pcl (bits 2,1 set) take no immediate
		end if;
		return false;
	end function;

	function takes_addr(op: std_logic_vector(7 downto 0)) return boolean is
		constant cls: std_logic_vector(4 downto 0) := op(7 downto 3);
	begin
		return cls = OP_LD or cls = OP_ST or cls = OP_LDD or cls = OP_STD or
			   cls = OP_B or cls = OP_BZF;
	end function;
begin
	alu0: entity work.alu port map(
		op => ir(7 downto 3), a => alu_a, b => alu_b,
		r => alu_r, z => alu_z, writes_r => alu_wr, writes_z => alu_wz);

	alu_a <= r1 when ir(0) = '1' else r0;
	alu_b <= imm when ir(2) = '1' else r1 when ir(1) = '1' else r0;

	a <= std_logic_vector(a_r);
	d_out <= dout_r;
	d_oe <= oe_r;
	rw <= rw_r;
	n_stb <= stb_r;
	sync <= sync_r;
	tmr_exp <= exp_r;
	halted <= '1' when state = s_halt else '0';
	waiting <= wait_r;

	dbg_pc <= std_logic_vector(pc);
	dbg_sp <= std_logic_vector(sp);
	dbg_r0 <= std_logic_vector(r0);
	dbg_r1 <= std_logic_vector(r1);
	dbg_f <= iflag & zf;

	process(clk)
		variable cls: std_logic_vector(4 downto 0);
		variable ra, rb, v: unsigned(7 downto 0);
		variable addr: unsigned(15 downto 0);
		variable rdy: boolean;

		-- start a bus cycle; outputs are registered and appear after this edge
		procedure bus_read(ad: unsigned(15 downto 0); is_fetch: std_logic := '0') is
		begin
			a_r <= ad; rw_r <= '1'; oe_r <= '0'; stb_r <= '0'; sync_r <= is_fetch;
		end procedure;
		procedure bus_write(ad: unsigned(15 downto 0); dv: unsigned(7 downto 0)) is
		begin
			a_r <= ad; rw_r <= '0'; dout_r <= std_logic_vector(dv); oe_r <= '1';
			stb_r <= '0'; sync_r <= '0';
		end procedure;
		procedure bus_idle is
		begin
			stb_r <= '1'; oe_r <= '0'; rw_r <= '1'; sync_r <= '0';
		end procedure;
		procedure set_ra(val: unsigned(7 downto 0)) is
		begin
			if ir(0) = '1' then r1 <= val; else r0 <= val; end if;
		end procedure;
	begin
		if rising_edge(clk) then
			rdy := stb_r = '0' and n_rdy = '0';
			cls := ir(7 downto 3);
			if ir(0) = '1' then ra := r1; else ra := r0; end if;
			if ir(1) = '1' then rb := r1; else rb := r0; end if;
			exp_r <= "00";

			if n_rst = '0' then
				state <= s_reset;
				bus_idle;
			else
				case state is
				when s_reset =>
					r0 <= x"00"; r1 <= x"00"; pc <= x"e000"; sp <= x"0100";
					zf <= '0'; iflag <= '0'; pcl <= x"00"; wait_r <= '0';
					tmr0 <= x"00"; tmr1 <= x"00";
					bus_read(x"e000", '1');
					state <= s_fetch;

				when s_fetch =>
					if rdy then
						ir <= d_in;
						pc <= pc + 1;
						if takes_imm(d_in) then
							bus_read(pc + 1);
							state <= s_imm;
						elsif takes_addr(d_in) then
							bus_read(pc + 1);
							state <= s_addr_lo;
						else
							bus_idle;
							state <= s_exec;
						end if;
					end if;

				when s_imm =>
					if rdy then
						imm <= unsigned(d_in);
						pc <= pc + 1;
						bus_idle;
						state <= s_exec;
					end if;

				when s_addr_lo =>
					if rdy then
						lo <= unsigned(d_in);
						pc <= pc + 1;
						bus_read(pc + 1);
						state <= s_addr_hi;
					end if;

				when s_addr_hi =>
					if rdy then
						pc <= pc + 1;
						addr := unsigned(d_in) & lo;
						ea <= addr;
						if cls = OP_LDD or cls = OP_STD then
							bus_read(addr);				-- fetch the pointer
							state <= s_ptr_lo;
						else
							bus_idle;
							state <= s_exec;
						end if;
					end if;

				when s_ptr_lo =>
					if rdy then
						lo <= unsigned(d_in);
						bus_read(ea + 1);
						state <= s_ptr_hi;
					end if;

				when s_ptr_hi =>
					if rdy then
						ea <= unsigned(d_in) & lo;
						bus_idle;
						state <= s_exec;
					end if;

				when s_exec =>
					state <= s_tick;
					if is_alu(cls) then
						if alu_wr = '1' then set_ra(alu_r); end if;
						if alu_wz = '1' then zf <= alu_z; end if;
					elsif cls = OP_MOV then
						set_ra(alu_b);
					elsif cls = OP_LD or cls = OP_LDD then
						if ir(2) = '1' then addr := ea + rb; else addr := ea; end if;
						bus_read(addr);
						state <= s_mem_rd;
					elsif cls = OP_ST or cls = OP_STD then
						if ir(2) = '1' then addr := ea + ra; else addr := ea; end if;
						bus_write(addr, rb);
						state <= s_mem_wr;
					elsif cls = OP_PUSH then
						if ir(2 downto 0) = "111" then			-- push pcl
							addr := pc + 3; v := addr(7 downto 0);
						elsif ir(2 downto 1) = "11" then		-- push pch
							addr := pc + 4; v := addr(15 downto 8);
						else
							v := alu_b;
						end if;
						bus_write(sp, v);
						sp <= sp + 1;
						state <= s_mem_wr;
					elsif cls = OP_POP then
						bus_read(sp - 1);
						sp <= sp - 1;
						state <= s_mem_rd;
					elsif cls = OP_B then
						pc <= ea;
					elsif cls = OP_BZF then
						if zf = '1' then pc <= ea; end if;
					elsif cls = OP_CLI then
						iflag <= '0';
					elsif cls = OP_STI then
						iflag <= '1';
					elsif cls = OP_TMR0 then
						tmr0 <= alu_b;
					elsif cls = OP_TMR1 then
						tmr1 <= alu_b;
					elsif cls = OP_WAI then
						wait_r <= iflag;
					elsif cls = OP_HALT then
						state <= s_halt;
					end if;
					-- anything else (NOP, undefined opcodes) is a 1-byte no-op

				when s_mem_rd =>
					if rdy then
						bus_idle;
						state <= s_tick;
						v := unsigned(d_in);
						if cls = OP_POP then
							if ir(2 downto 0) = "111" then			-- pop pcl
								pcl <= v;
							elsif ir(2 downto 1) = "11" then		-- pop pch: jump
								pc <= v & pcl;
							elsif ir(2 downto 0) = "100" then		-- pop f
								zf <= v(0);
								iflag <= v(1);
							else
								set_ra(v);
							end if;
						else
							set_ra(v);								-- ld / ldd
						end if;
					end if;

				when s_mem_wr =>
					if rdy then
						bus_idle;
						state <= s_tick;
					end if;

				when s_tick =>
					if tmr0 /= 0 then
						tmr0 <= tmr0 - 1;
						if tmr0 = 1 then exp_r(0) <= '1'; end if;
					end if;
					if tmr1 /= 0 then
						tmr1 <= tmr1 - 1;
						if tmr1 = 1 then exp_r(1) <= '1'; end if;
					end if;
					state <= s_settle;

				when s_settle =>		-- TMR_EXP is high in this clock; the chipset latches it
					state <= s_check;

				when s_check =>
					if iflag = '1' and irq /= "0000" then
						if irq(0) = '1' then irq_n <= "00";
						elsif irq(1) = '1' then irq_n <= "01";
						elsif irq(2) = '1' then irq_n <= "10";
						else irq_n <= "11";
						end if;
						wait_r <= '0';
						bus_write(sp, pc(15 downto 8));
						sp <= sp + 1;
						state <= s_irq_h;
					elsif wait_r = '1' then
						state <= s_tick;				-- parked in WAI: timers keep counting
					else
						bus_read(pc, '1');
						state <= s_fetch;
					end if;

				when s_irq_h =>
					if rdy then
						bus_write(sp, pc(7 downto 0));
						sp <= sp + 1;
						state <= s_irq_l;
					end if;

				when s_irq_l =>
					if rdy then
						bus_write(sp, "000000" & iflag & zf);
						sp <= sp + 1;
						state <= s_irq_f;
					end if;

				when s_irq_f =>
					if rdy then
						iflag <= '0';
						bus_read(x"0010" + resize(irq_n & '0', 16));
						state <= s_vec_lo;
					end if;

				when s_vec_lo =>
					if rdy then
						lo <= unsigned(d_in);
						bus_read(x"0011" + resize(irq_n & '0', 16));
						state <= s_vec_hi;
					end if;

				when s_vec_hi =>
					if rdy then
						pc <= unsigned(d_in) & lo;
						bus_read(unsigned(d_in) & lo, '1');
						state <= s_fetch;
					end if;

				when s_halt =>
					bus_idle;
				end case;
			end if;
		end if;
	end process;
end architecture;
