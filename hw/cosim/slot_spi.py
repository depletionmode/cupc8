"""Pin-exact fitted slot networks and binary DC continuity, not analogue SI.

Passives preserve the functional DC level; TI125 stages are non-inverting
when their actual OE/VCC/GND legs are connected. Every fitted capacitor leg
is required for strict coverage, even though its transient is qualified by SI.
"""
from pathlib import Path


def network(c, kind):
    legs = []
    signals = {}
    nets = set()

    def pin(ref, p, net):
        if c.net(ref, str(p)) != '/' + net:
            raise ValueError(f'{kind}:{ref}.{p}: expected /{net}')
        nets.add(net)
        return ref, str(p)

    def part(ref, value, source):
        if c.components.get(ref) != (value, source):
            raise ValueError(f'{kind}:{ref}: expected {value} {source}')

    def leg(group, net, a, b, *, dc=True):
        pin(*a, net); pin(*b, net)
        legs.append((group, net, a, b, dc))

    def resistor(ref, a, b):
        part(ref, '220', ('Device', 'R')); pin(ref, 1, a); pin(ref, 2, b)

    def cap(group, ref, value, net, anchor, ground):
        part(ref, value, ('Device', 'C'))
        leg(group, net, anchor, (ref, '1'),dc=False)
        leg(group, 'GND', (ref, '2'), ground,dc=False)

    def buffer(ref, a, y, oe):
        part(ref, 'SN74LVC1G125DCKR', ('74xGxx', '74LVC1G125'))
        for p,n in ((1,oe),(2,a),(3,'GND'),(4,y),(5,'3V3')):pin(ref,p,n)

    def mcu(net):
        found=[(r,p)for(r,p),n in c.pins.items()if r=='U1' and n=='/'+net]
        if len(found)!=1:raise ValueError(f'{kind}:{net}: expected one MCU GPIO')
        return found[0]

    grounds=[(r,p)for(r,p),n in c.pins.items()if r=='U1' and n=='/GND'
             and (kind=='wifi' or p=='57')]
    if not grounds:raise ValueError(f'{kind}: actual MCU ground absent')
    ground=grounds[0]
    rail=mcu('3V3') if kind=='wifi' else ('U1','1')
    pin(*rail,'3V3')
    configs=(('cs','CS_n','A14','U4','R62','R63','C60','C61','C62','10p'),
             ('sck','SCK','B13','U5','R64','R65','C63','C64','C65','5.6p'),
             ('mosi','MOSI','B15','U6','R66','R67','C66','C67','C68','4.7p'))
    if kind=='wifi':
        branch_refs={'R69','R70'}
        fitted_branches=branch_refs.intersection(c.components)
        if fitted_branches and fitted_branches != branch_refs:
            raise ValueError('wifi: incomplete exact output-cap series branches')
        for group,raw,contact,u,rin,rout,cin,cout,bypass,val in configs:
            a,y,pad=('WIFI_'+raw+s for s in ('_A','_Y','_PAD'))
            buffer(u,a,y,'GND');resistor(rin,raw,a)
            if rout in ('R63','R65'):
                part(rout,'270',('Device','R'))
                if (c.lcsc or {}).get(rout)!='C25099':
                    raise ValueError(f'wifi:{rout}: expected exact C25099 identity')
                pin(rout,1,y);pin(rout,2,pad)
            else:
                resistor(rout,y,pad)
            target=mcu(pad);signals[group]=target
            leg(group,raw,('J1',contact),(rin,'1'))
            leg(group,a,(rin,'2'),(u,'2'))
            leg(group,y,(u,'4'),(rout,'1'))
            leg(group,pad,(rout,'2'),target)
            leg(group,'GND',(u,'1'),ground);leg(group,'GND',(u,'3'),ground)
            leg(group,'3V3',(u,'5'),rail)
            cap(group,cin,val,a,(u,'2'),ground)
            if fitted_branches and group in ('cs','sck'):
                branch='R69' if group=='cs' else 'R70'
                capnet=pad+'_CAP'
                part(branch,'15',('Device','R'))
                expected_identity='C25083'
                if (c.lcsc or {}).get(branch)!=expected_identity:
                    raise ValueError(f'wifi:{branch}: expected exact {expected_identity} identity')
                pin(branch,1,pad);pin(branch,2,capnet)
                leg(group,pad,target,(branch,'1'),dc=False)
                cap(group,cout,'10p',capnet,(branch,'2'),ground)
            else:
                cap(group,cout,'10p',pad,target,ground)
            cap(group,bypass,'100n','3V3',(u,'5'),ground)
    else:
        for group,raw,contact,r,capref in (('sck','SCK','B13','R62','C60'),
                ('mosi','MOSI','B15','R63','C61'),('cs','CS_n','A14','R64','C62')):
            filt=raw+'_MCU';resistor(r,raw,filt);target=mcu(filt);signals[group]=target
            leg(group,raw,('J1',contact),(r,'1'))
            leg(group,filt,(r,'2'),target)
            cap(group,capref,'10p',filt,target,ground)
    signals['irq']=mcu('IRQ_n');leg('irq','IRQ_n',('J1','B10'),signals['irq'])
    u='U3' if kind=='wifi' else 'U4'
    internal='MISO_INT' if kind=='wifi' else 'MISO_OUT'
    signals['miso']=mcu(internal)
    buffer(u,internal,'MISO_SRC','CS_OE')
    resistor('R60','MISO_SRC','MISO')
    part('R61','47k',('Device','R'));pin('R61',1,'MISO');pin('R61',2,'GND')
    oe='R68' if kind=='wifi' else 'R65';oc='C69' if kind=='wifi' else 'C63'
    resistor(oe,'CS_n','CS_OE')
    leg('enable','CS_n',('J1','A14'),(oe,'1'))
    leg('enable','CS_OE',(oe,'2'),(u,'1'))
    cap('enable',oc,'10p','CS_OE',(u,'1'),ground)
    leg('miso',internal,signals['miso'],(u,'2'))
    leg('miso','MISO_SRC',(u,'4'),('R60','1'))
    leg('miso','MISO',('R60','2'),('J1','B16'))
    leg('miso_pulldown','MISO',('R61','1'),('J1','B16'))
    leg('miso_pulldown','GND',('R61','2'),ground)
    leg('miso','GND',(u,'3'),ground);leg('miso','3V3',(u,'5'),rail)
    return {'signals':signals,'legs':legs,'nets':sorted(nets)}


def routed(c, kind, board):
    spec=network(c,kind)
    from ibis_bus import routed_connectivity
    import pcbnew
    loaded=pcbnew.LoadBoard(str(board)) if board and Path(board).is_file() else None
    links={x:True for x in ('sck','mosi','cs','irq','miso','miso_pulldown','enable')}
    rows=[];complete={group:True for group in links}
    for group,net,a,b,dc in spec['legs']:
        ok=bool(loaded is not None and routed_connectivity(Path(board),'/'+net,a,[b],loaded_board=loaded)[f'{b[0]}.{b[1]}'])
        complete[group]&=ok
        if dc:links[group]&=ok
        rows.append({'from':f'{kind}.{a[0]}.{a[1]}','to':f'{kind}.{b[0]}.{b[1]}',
                     'net':net,'connected':ok,'runtime':f'{kind}_{group}_connected',
                     'scope':'binary native copper continuity; analogue SI separate','functional_dc_leg':dc})
    links['miso'] &= links['enable']
    links['complete']=all(complete.values())
    missing=[f'{kind}:{x}_slot_copper'for x,ok in complete.items()if not ok]
    return links,rows,missing,spec


def main_select(c,slot):
    """Only the six physically specified slot-select source branches."""
    ref=f'R{36+slot}';pin=('34','38','39','47','52','56')[slot-1]
    expected={('U7',pin):f'/SPI_nCS{slot-1}_SRC',
              (ref,'1'):f'/SPI_nCS{slot-1}_SRC',
              (ref,'2'):f'/SLOT{slot}_CS_n',
              (f'J{10+slot}','A14'):f'/SLOT{slot}_CS_n'}
    if c.components.get(ref)!=('68',('Device','R')) or any(c.net(*p)!=n for p,n in expected.items()):
        raise ValueError(f'Main slot{slot}: exact source/resistor/socket pins changed')
    resistor=c.series(('U7',pin),(f'J{10+slot}','A14'))
    if resistor is None or resistor.ref!=ref or resistor.value!='68':
        raise ValueError(f'Main slot{slot}: ambiguous or missing fitted series')
    return ref


def main_bias(c):
    expected={('R107','1'):'/+3V3',('R107','2'):'/SPI_MISO',
              ('R109','1'):'/SPI_MISO',('R109','2'):'/GND',('U7','48'):'/SPI_MISO'}
    if any(c.net(*p)!=n for p,n in expected.items()) or c.components.get('R107')!=('100k',('Device','R')) or c.components.get('R109')!=('4.7k',('Device','R')):
        raise ValueError('Main exact 100k/4.7k MISO bias changed')
    for rail,ref,value in (('/+3V3','R107','100k'),('/GND','R109','4.7k')):
        if [(r.ref,r.value)for r,n in c.pulls(rail)if n=='/SPI_MISO']!=[(ref,value)]:
            raise ValueError('Main unexpected parallel MISO bias')
    return 0
