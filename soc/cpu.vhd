library ieee;
use ieee.std_logic_1164.all;
use ieee.numeric_std.all;

entity cpu is
	port(
			clk: 			in std_logic;
			n_hrst:		in std_logic;
			halt:			out std_logic;
			
			mem_addr:	out std_logic_vector(15 downto 0);
			mem_data:	inout std_logic_vector(7 downto 0);
			mem_n_we:	out std_logic;

			irq:			in std_logic_vector(3 downto 0) := "0000";
			tmr0_irq:	out std_logic;
			tmr1_irq:	out std_logic;
			
			-- testing
			seg7_val:	out std_logic_vector(3 downto 0)
		);
end entity;

architecture behavioural of cpu is
signal			alu_en:		std_logic := '0';
signal			alu_ra:		unsigned(7 downto 0);
signal			alu_rb:		unsigned(7 downto 0);
signal			alu_res:		unsigned(7 downto 0);
signal			alu_zf:		unsigned(0 downto 0) := "0";
component alu
   port(
			clk:		in std_logic;
			n_en:		in std_logic;
			op:		in std_logic_vector(3 downto 0);
			a, b:		in unsigned(7 downto 0);
			r:			out unsigned(7 downto 0);
			zf:		out unsigned(0 downto 0)
		);
end component;

signal r0, r1:	unsigned(7 downto 0) := x"00";
signal pc:	std_logic_vector(15 downto 0) := x"0000";
signal sp:	unsigned(15 downto 0) := x"0000";
signal f: unsigned(3 downto 0) := x"0";
signal ins: unsigned(7 downto 0) := x"00";
signal imm_value: unsigned(7 downto 0) := x"00";
signal addr_value: unsigned(15 downto 0) := x"0000";
type stages is (fetch, decode, execute, writeback, reset, fetch_imm, fetch_addr, fetch_addr2, fetch2, waitonram,
	check_irq, irq_push_h, irq_push_l, irq_push_f, irq_vec, irq_vec2, irq_vec3, halt_st, wai_st);
signal stage, stage_nxt: stages := reset;
signal i_flag: std_logic := '0';
signal z_flag: std_logic := '0';
signal waiting: std_logic := '0';
signal tmr0_cnt: unsigned(7 downto 0) := x"00";
signal tmr1_cnt: unsigned(7 downto 0) := x"00";
signal tmr0_irq_r: std_logic := '0';
signal tmr1_irq_r: std_logic := '0';
signal irq_n: integer range 0 to 3 := 0;
signal data: unsigned(7 downto 0) := "10000000";
signal imm_fetched: std_logic := '0';
signal addr_reg_offset: std_logic := '0';

begin
alu0: alu port map(clk, alu_en, std_logic_vector(ins(6 downto 3)), alu_ra, alu_rb, alu_res, alu_zf);

f <= "00" & i_flag & z_flag;
tmr0_irq <= tmr0_irq_r;
tmr1_irq <= tmr1_irq_r;

process(clk, n_hrst)
variable addr2_fetched: bit;
variable rtmp: unsigned(7 downto 0);
variable ra, rb: unsigned(7 downto 0);
variable sp_next: unsigned(15 downto 0);
variable tmp16: unsigned (15 downto 0);
variable tmp16_2: unsigned (15 downto 0);
variable ram_delay: integer range 0 to 1000 := 0;
variable ram_ld, ram_st: bit := '0';
begin
	halt <= n_hrst;
   if (rising_edge(clk)) then
		if n_hrst = '0' then
			stage <= reset;
		--elsif but_de ='0' then
		else
			case stage is
				when fetch =>
					mem_data <= (others => 'Z');
					seg7_val <= x"1";
					mem_n_we <= '1';
					mem_addr <= std_logic_vector(pc);
					stage <= fetch2;
				when fetch2 => -- dirty dirty hack!
					seg7_val <= x"2";
					mem_n_we <= '1';
					ins <= unsigned(mem_data);
					stage <= decode;
				when fetch_imm =>
					seg7_val <= x"6";
					mem_addr <= std_logic_vector(pc);
					stage <= decode;
				when fetch_addr =>
					seg7_val <= x"7";
					mem_addr <= std_logic_vector(pc);
					pc <= std_logic_vector(unsigned(pc) + 1);
					stage <= fetch_addr2;
				when fetch_addr2 =>
					seg7_val <= x"8";
					mem_addr <= std_logic_vector(pc);
					addr_value <= x"00" & unsigned(mem_data);
					addr2_fetched := '1';
					stage <= decode;
				when decode =>	
					seg7_val <= x"3";
					pc <= std_logic_vector(unsigned(pc) + 1);
					
					
					-- addressed instructions can have register value offsets		
					-- this is marked by bit2 set
					case ins(6 downto 3) is
						when "0100"|"0101" => -- LD|ST
							if ins(2) = '1' then
								addr_reg_offset <= '1';
							else
								addr_reg_offset <= '0';
							end if;
						when others => addr_reg_offset <='0';
					end case;
							
					-- fetch imm
					if addr_reg_offset = '0' and ins(2 downto 1) = "10" and imm_fetched = '0' then
						-- fetch imm
						imm_fetched <= '1';
						stage <= fetch_imm;
					else
						-- register decode
						if ins(0) = '0' then ra := r0; else ra := r1; end if;
						if ins(1) = '0' then rb := r0; else rb := r1; end if;
						if ins(2) = '1' and ins(1) = '1' and addr_reg_offset = '0' then
							-- use pc
							if ins(0) = '0' then
								tmp16 := unsigned(pc) + 5; -- offset 5 ops
								rb := tmp16(15 downto 8);
							else
								tmp16 := unsigned(pc) + 4; -- offset 4 ops
								rb := tmp16(7 downto 0);
							end if;
--						elsif ins(1) = '0' then
--							rb := r0;
--						else
--							rb := r1;
						end if;
						--ra := r0 when ins(0)='0' else r1;
						
						if(ins(7) = '0') then
							-- alu setup
							alu_ra <= ra;
							if imm_fetched = '1' then alu_rb <= unsigned(mem_data); else alu_rb <= rb; end if;
							stage <= execute;
						else
							-- handle addressed instructions		
							case ins(6 downto 3) is
								when "0100"|"0101"|"0110"|"0111" => -- LD|ST|B|BNE
									if addr2_fetched = '0' then
										stage <= fetch_addr;
									else
										if addr_reg_offset = '1' then
											if ins(6 downto 3) = "0100" then	-- LD
												rtmp := rb;
											else
												rtmp := ra;
											end if;
										else
												rtmp := to_unsigned(0, rtmp'length);
										end if;
										addr_value <= unsigned(mem_data) & addr_value(7 downto 0) + rtmp;
										stage <= execute;
									end if;
								when others => stage <= execute;
							end case;
						end if;
					end if;
				when execute =>
					seg7_val <= x"4";
					
					if(imm_fetched = '1') then
						rtmp := unsigned(mem_data);
					else
						rtmp := rb;
					end if;
					
					if(ins(7) = '0') then	
						-- exec alu
						alu_en <= '0';
					else
						case ins(6 downto 3) is
							when "0010" => -- PUSH
								mem_addr <= std_logic_vector(sp);
								sp_next := sp + 1;
							when "0011" => -- POP
								mem_addr <= std_logic_vector(sp - 1);
								sp_next := sp - 1;
								ram_ld := '1';
							when "0100" => -- LD
								mem_addr <= std_logic_vector(addr_value);
								ram_ld := '1';
							when "0101" => -- ST
								mem_addr <= std_logic_vector(addr_value);
							when "0110" => -- B
								pc <= std_logic_vector(addr_value);
							when "0111" => -- BNE
								if z_flag = '1' then
									pc <= std_logic_vector(addr_value);
								end if;
							when "1000" => -- CLI
								null;
							when "1001" => -- STI
								null;
							when "1100"|"1101" => -- TMR0|TMR1
								null;
							when "1110" => -- WAI
								null;
							when "1111" => -- HALT
								null;
							when others => NULL;
						end case;
					end if;
					
					if ram_ld = '1' then
						stage <= waitonram;
					else
						stage <= writeback;
					end if;
				when writeback =>
				
					seg7_val <= x"5";
					-- get result from alu
					if(ins(7)='0') then
							rtmp := alu_res;
							-- write back into register
							if(ins(0) = '0') then
								r0 <= rtmp;
							else
								r1 <= rtmp;
							end if;
							alu_en <= '1';
							case ins(6 downto 3) is
								when "0000"|"0001"|"0010" => -- EQ|GT|LT
									z_flag <= alu_zf(0);
								when others => null;
							end case;
					end if;
					
					case ins(6 downto 3) is
						when "0001" => -- MOV
							-- write back into register
							if(ins(0) = '0') then
								r0 <= rtmp;
							else
								r1 <= rtmp;
							end if;
						when "0010" => -- PUSH
							-- write back into memory
							mem_data <= std_logic_vector(rtmp);	
							mem_n_we <= '0';
							ram_st := '1';
						when "0011" => -- POP
							if ins(2 downto 0) = "100" then -- pop f
								z_flag <= mem_data(0);
								i_flag <= mem_data(1);
							elsif ins(2) = '0' then
								-- write back into register
								if ins(0) = '0' then
									r0 <= unsigned(mem_data);
								else
									r1 <= unsigned(mem_data);
								end if;
							else -- pc
								if ins(0) = '0' then
									tmp16_2 := x"00" & unsigned(mem_data);
								else
									tmp16_2 := unsigned(mem_data) & tmp16_2(7 downto 0);
									pc <= std_logic_vector(tmp16_2);
								end if;
							end if;
						when "1000" => -- CLI
							i_flag <= '0';
						when "1001" => -- STI
							i_flag <= '1';
						when "1100" => -- TMR0
							tmr0_cnt <= rtmp;
						when "1101" => -- TMR1
							tmr1_cnt <= rtmp;
						when "1110" => -- WAI
							if i_flag = '1' then
								waiting <= '1';
							end if;
						when "1111" => -- HALT
							null;
						when "0100" => -- LD
							-- write back into register
							if(ins(0) = '0') then
								r0 <= unsigned(mem_data);
							else
								r1 <= unsigned(mem_data);
							end if;
						when "0101" => -- ST
							-- write back into memory
							mem_data <= std_logic_vector(rtmp);
							mem_n_we <= '0';
							ram_st := '1';
						when others => NULL;
					end case;
					
					-- make sp change if necessary
					sp <= sp_next;
					
					-- clear up
					imm_fetched <= '0';
					addr2_fetched := '0';
					
					if ins(7 downto 3) = "11111" then -- HALT
						stage <= halt_st;
					elsif ram_st = '1' then
						stage <= waitonram;
					else
						stage <= check_irq;
					end if;
				when waitonram =>
					-- mem delay > 70ns
					-- 4 cycles should be sufficient (80ns)
					-- one added for good measure
					if ram_delay < 4 then 
						ram_delay := ram_delay + 1;
					else
						ram_delay := 0;
						if ram_ld ='1' then
							stage <= writeback;
							ram_ld := '0';
						else 
							stage <= check_irq;
							ram_st := '0';
						end if;
					end if;
				when check_irq =>
					mem_n_we <= '1';
					mem_data <= (others => 'Z');
					tmr0_irq_r <= '0';
					tmr1_irq_r <= '0';
					if tmr0_cnt > 0 then
						if tmr0_cnt = 1 then
							tmr0_irq_r <= '1';
						end if;
						tmr0_cnt <= tmr0_cnt - 1;
					end if;
					if tmr1_cnt > 0 then
						if tmr1_cnt = 1 then
							tmr1_irq_r <= '1';
						end if;
						tmr1_cnt <= tmr1_cnt - 1;
					end if;
					if i_flag = '1' and irq /= "0000" then
						waiting <= '0';
						if irq(0) = '1' then
							irq_n <= 0;
						elsif irq(1) = '1' then
							irq_n <= 1;
						elsif irq(2) = '1' then
							irq_n <= 2;
						else
							irq_n <= 3;
						end if;
						stage <= irq_push_h;
					elsif waiting = '1' then
						stage <= wai_st;
					else
						stage <= fetch;
					end if;
				when irq_push_h =>
					mem_addr <= std_logic_vector(sp);
					mem_data <= pc(15 downto 8);
					mem_n_we <= '0';
					sp <= sp + 1;
					sp_next := sp + 1;
					stage <= irq_push_l;
				when irq_push_l =>
					mem_addr <= std_logic_vector(sp);
					mem_data <= pc(7 downto 0);
					mem_n_we <= '0';
					sp <= sp + 1;
					sp_next := sp + 1;
					stage <= irq_push_f;
				when irq_push_f =>
					mem_addr <= std_logic_vector(sp);
					mem_data <= "000000" & i_flag & z_flag;
					mem_n_we <= '0';
					sp <= sp + 1;
					sp_next := sp + 1;
					i_flag <= '0';
					stage <= irq_vec;
				when irq_vec =>
					mem_n_we <= '1';
					mem_data <= (others => 'Z');
					mem_addr <= std_logic_vector(to_unsigned(16#0010# + irq_n * 2, 16));
					stage <= irq_vec2;
				when irq_vec2 =>
					addr_value <= x"00" & unsigned(mem_data);
					mem_addr <= std_logic_vector(to_unsigned(16#0011# + irq_n * 2, 16));
					stage <= irq_vec3;
				when irq_vec3 =>
					pc <= mem_data & std_logic_vector(addr_value(7 downto 0));
					stage <= fetch;
				when halt_st =>
					mem_n_we <= '1';
					stage <= halt_st;
				when wai_st =>
					mem_n_we <= '1';
					if i_flag = '1' and irq /= "0000" then
						waiting <= '0';
						if irq(0) = '1' then
							irq_n <= 0;
						elsif irq(1) = '1' then
							irq_n <= 1;
						elsif irq(2) = '1' then
							irq_n <= 2;
						else
							irq_n <= 3;
						end if;
						stage <= irq_push_h;
					else
						stage <= wai_st;
					end if;
				when reset =>
					seg7_val <= "0000";
					r0 <= x"00";
					r1 <= x"00";
					sp <= x"0100";
					sp_next := x"0100";
					pc <= x"e000";
					mem_n_we <= '1';
					mem_addr <= x"ffff";
					imm_fetched <= '0';
					addr2_fetched := '0';
					i_flag <= '0';
					z_flag <= '0';
					waiting <= '0';
					tmr0_cnt <= x"00";
					tmr1_cnt <= x"00";
					tmr0_irq_r <= '0';
					tmr1_irq_r <= '0';
					stage <= fetch;
				when others => stage <= reset;
			end case;
		end if;
	end if;
end process;

end architecture;
