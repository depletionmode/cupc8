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
			
			-- testing
			o: 			out std_logic;
         seg7_val:	out std_logic_vector(3 downto 0)
		);
end entity;

architecture behavioural of cpu is
signal			alu_en:		std_logic;
signal			alu_ra:		unsigned(7 downto 0);
signal			alu_rb:		unsigned(7 downto 0);
signal			alu_res:		unsigned(7 downto 0);
signal			alu_zf:		unsigned(0 downto 0);
component alu
   port(
			n_en:		in std_logic;
			op:		in std_logic_vector(3 downto 0);
			a, b:		in unsigned(7 downto 0);
			r:			out unsigned(7 downto 0);
			zf:		out unsigned(0 downto 0)
		);
end component;

signal r0, r1:	unsigned(7 downto 0);
signal pc:	std_logic_vector(15 downto 0) := x"0000";
signal sp:	unsigned(15 downto 0) := x"0000";
signal f: unsigned(3 downto 0) := x"0";
signal ins: unsigned(7 downto 0);
signal imm_value: unsigned(7 downto 0);
signal addr_value: unsigned(15 downto 0);
type stages is (fetch, decode, execute, writeback, reset, fetch_imm, fetch_addr, fetch_addr2, fetch2, waitonram);
signal stage, stage_nxt: stages := reset;
signal data: unsigned(7 downto 0) := "10000000";
signal imm_fetched: std_logic;

begin
alu0: alu port map(alu_en, std_logic_vector(ins(6 downto 3)), alu_ra, alu_rb, alu_res, alu_zf);

f <= "000" & alu_zf;
		
process(clk, n_hrst)
variable addr2_fetched: bit;
variable rtmp: unsigned(7 downto 0);
variable ra, rb: unsigned(7 downto 0);
variable sp_next: unsigned(15 downto 0);
variable tmp16: unsigned (15 downto 0);
variable tmp16_2: unsigned (15 downto 0);
variable ram_delay: integer range 0 to 10 := 0;
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
					seg7_val <= "0001";
					mem_n_we <= '1';
					mem_addr <= std_logic_vector(pc);
					stage <= fetch2;
				when fetch2 => -- dirty dirty hack!
					seg7_val <= "0010";
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
					seg7_val <= "0011";
					pc <= std_logic_vector(unsigned(pc) + 1);
					
					-- fetch imm
					if(ins(2) = '1' and ins(1) = '0' and imm_fetched = '0') then
						-- fetch imm
						imm_fetched <= '1';
						stage <= fetch_imm;
					else
						-- register decode
						if ins(0) = '0' then ra := r0; else ra := r1; end if;
						if ins(2) = '1' and ins(1) = '1' then
							-- use pc
							if ins(0) = '0' then
								tmp16 := unsigned(pc) + 5; -- offset 5 ops
								rb := tmp16(15 downto 8);
							else
								tmp16 := unsigned(pc) + 4; -- offset 4 ops
								rb := tmp16(7 downto 0);
							end if;
						elsif ins(1) = '0' then
							rb := r0;
						else
							rb := r1;
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
										addr_value <= unsigned(mem_data) & addr_value(7 downto 0);
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
							when "0010"|"1100"|"1101" => -- PUSH|PUSH.PC1|PUSH.PC2
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
								if f(0) = '1' then
									pc <= std_logic_vector(addr_value);
								end if;
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
							alu_en <= '1';
							rtmp := alu_res;
							-- write back into register
							if(ins(0) = '0') then
								r0 <= rtmp;
							else
								r1 <= rtmp;
							end if;
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
							if ins(2) = '0' then
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
					
					if ram_st = '1' then
						stage <= waitonram;
					else
						stage <= fetch;
					end if;
				when waitonram =>
					-- mem delay > 70ns
					-- 4 cycles should be sufficient (80ns)
					-- one added for good measure
					if ram_delay < 3 then 
						ram_delay := ram_delay + 1;
					else
						ram_delay := 0;
						if ram_ld ='1' then
							stage <= writeback;
							ram_ld := '0';
						else 
							stage <= fetch;
							ram_st := '0';
						end if;
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
					stage <= fetch;
				when others => stage <= reset;
			end case;
		end if;
	end if;
end process;

end architecture;
