//#define __AVR_ATxmega16C4__
#define F_CPU 2000000

#include <avr/io.h>
#include <util/delay.h>

inline uint8_t nvm_exec()
{
    void *z = (void *)&NVM_CTRLA;

    __asm__ volatile("out %[ccp], %[ioreg]"  "\n\t"
                     "st z, %[cmdex]"
                     :
                     : [ccp] "I" (_SFR_IO_ADDR(CCP)),
                     [ioreg] "d" (CCP_IOREG_gc),
                     [cmdex] "r" (NVM_CMDEX_bm),
                     [z] "z" (z)
                    );
}

inline void nvm_eeprom_wait()
{
    while ((NVM.STATUS & NVM_NVMBUSY_bm) == NVM_NVMBUSY_bm);
}

uint8_t nvm_eeprom_read(uint16_t addr)
{
    nvm_eeprom_wait();

    NVM.ADDR2 = 0;
    NVM.ADDR1 = (addr >> 8) & 0x1f;
    NVM.ADDR0 = addr & 0xff;
    NVM.CMD = NVM_CMD_READ_EEPROM_gc;

    nvm_exec();

    return NVM.DATA0;
}

void nvm_eeprom_write(uint16_t addr, uint8_t val)
{
    nvm_eeprom_wait();

    if ((NVM.STATUS & NVM_EELOAD_bm) != 0) {
        NVM.CMD = NVM_CMD_ERASE_EEPROM_BUFFER_gc;
        nvm_exec();
    }
    
    NVM.CMD = NVM_CMD_LOAD_EEPROM_BUFFER_gc;
    NVM.ADDR0 = addr & 0xff;
    NVM.ADDR1 = (addr >> 8) & 0x1f;
    NVM.ADDR2 = 0x00;

    NVM.DATA0 = val;

    NVM.CMD = NVM_CMD_ERASE_WRITE_EEPROM_PAGE_gc;
    nvm_exec();
}

void init_ram()
{
    PORTA.DIR = 0xff;
    PORTB.DIR |= 0xf;
    PORTC.DIR = 0xff;
    PORTD.DIR |= 0xf0;
    PORTE.DIRSET = PIN2_bm;

#define PINCFG PORT_OPC_WIREDANDPULL_gc

    PORTA.PIN0CTRL = PINCFG;
    PORTA.PIN1CTRL = PINCFG;
    PORTA.PIN2CTRL = PINCFG;
    PORTA.PIN3CTRL = PINCFG;
    PORTA.PIN4CTRL = PINCFG;
    PORTA.PIN5CTRL = PINCFG;
    PORTA.PIN6CTRL = PINCFG;
    PORTA.PIN7CTRL = PINCFG;

    PORTB.PIN0CTRL = PINCFG;
    PORTB.PIN1CTRL = PINCFG;
    PORTB.PIN2CTRL = PINCFG;
    PORTB.PIN3CTRL = PINCFG;

    PORTC.PIN0CTRL = PINCFG;
    PORTC.PIN1CTRL = PINCFG;
    PORTC.PIN2CTRL = PINCFG;
    PORTC.PIN3CTRL = PINCFG;
    PORTC.PIN4CTRL = PINCFG;
    PORTC.PIN5CTRL = PINCFG;
    PORTC.PIN6CTRL = PINCFG;
    PORTC.PIN7CTRL = PINCFG;
 
    PORTD.PIN4CTRL = PINCFG;
    PORTD.PIN5CTRL = PINCFG;
    PORTD.PIN6CTRL = PINCFG;
    PORTD.PIN7CTRL = PINCFG;

    PORTE.PIN2CTRL = PINCFG;
    PORTE.OUTSET = PIN2_bm;
    _delay_ms(100);
}

void go_hiz()
{
    PORTA.DIR = 0;
    PORTB.DIR &= 0xf0;
    PORTC.DIR = 0;
    PORTD.DIR &= 0xf;
}

void write(int addr, int val)
{
    /* switch A10 and A11 because of board error */
    addr = (addr & 0xf3ff) | (addr & 0x0800) >> 1 | (addr & 0x0400) << 1;

    PORTA.OUT = val & 0xff;
    PORTB.OUT = PORTB.IN & 0xf0 | addr & 0x0f;
    PORTD.OUT = addr & 0xf0 | PORTD.IN & 0x0f;
    PORTC.OUT = (addr >> 8) & 0xff;

    PORTE.OUTCLR = PIN2_bm;
    PORTE.OUTSET = PIN2_bm;
}


int main(void)
{
    PORTD.DIRSET = PIN0_bm;
    PORTD.DIRSET = PIN1_bm;

    PORTD.OUTCLR = PIN0_bm;

    /* disable jtag */
    CCP = CCP_IOREG_gc;
    MCU.MCUCR = 0b00000001;

    init_ram();
    
    /* test data */
    /*
    int i;
    for (i=0; i<16; i++) {
    //    nvm_eeprom_write(i, i);
        write(1<<i, nvm_eeprom_read(i));
    }
    */
 
    go_hiz();

    PORTD.OUTCLR = PIN1_bm;

    _delay_ms(30000);

    SLEEP.CTRL  = (SLEEP_SMODE_PSAVE_gc|SLEEP_SEN_bm);
/*
    while (1) {
        PORTD.OUTTGL = PIN0_bm;
        PORTD.OUTTGL = PIN1_bm;
        _delay_ms(500);
    }
*/

   while(1); 
}
