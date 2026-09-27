"""Deterministic post-route eFuse relocation and 5V_SYS copper reinforcement.

The saved salt-1 route retains its signal geometry. This replaces only the local
input/eFuse control escape and reinforces the copper bus to the buck. Exact
old-copper guards stop the build if the imported route changes.
"""


def reinforce_5v_sys(board):
    import pcbnew
    b = board
    mm, to = pcbnew.FromMM, pcbnew.ToMM
    f=b.FindFootprintByReference('U2');f.SetPosition(pcbnew.VECTOR2I(mm(11),mm(156)))
    c15=b.FindFootprintByReference('C15');c15.SetPosition(pcbnew.VECTOR2I(mm(15.2),mm(153.5)))
    b.FindFootprintByReference('C3').Reference().SetPosition(pcbnew.VECTOR2I(mm(13.5),mm(161.5)))
    n=b.FindNet('/5V_SYS')
    old={
     ('/5V_SYS',(18.26,160.0,18.26,162.0)),
     ('/5V_SYS',(11.0,162.0,34.0,162.0)),
     ('/VBUS_F',(17.77,160.0,17.77,158.0)),
     ('/VBUS_F',(17.77,158.0,21.675,158.0)),
     ('/GND',(11.0,159.05,11.0,157.75)),
     ('/GND',(14.775,155.0,15.775,155.0)),
     ('/EFUSE_DVDT',(13.225,155.0,13.225,156.9207)),
     ('/PWR_EN',(17.09,159.1,15.99,159.1)),
     ('/PWR_EN',(15.7372,159.3528,15.99,159.1)),
     ('/PWR_EN',(15.7372,160.2652,15.7372,159.3528)),
     ('/EFUSE_ILM',(18.91,159.77,19.4367,159.77)),
     ('/EFUSE_ILM',(19.4367,159.77,19.4367,159.7428)),
     ('/EFUSE_ILM',(19.4367,159.7428,19.9298,159.2497)),
     ('/EFUSE_DVDT',(21.2099,160.9,18.91,160.9)),
     ('/EFUSE_DVDT',(22.29,159.8199,21.2099,160.9)),
     ('/EFUSE_OVLO',(17.09,159.77,16.5633,159.77)),
     ('/EFUSE_OVLO',(16.5633,159.77,16.5633,160.2729)),
     ('/EFUSE_OVLO',(16.5633,160.2729,15.9599,160.8763)),
     ('/EFUSE_OVLO',(15.9599,160.8763,15.5066,160.8763)),
     ('/EFUSE_OVLO',(15.5066,160.8763,15.1413,160.511)),
     ('/EFUSE_OVLO',(15.1413,160.511,15.1413,159.482)),
    }
    tr=b.Tracks();remove=[];found=set()
    for i in range(len(tr)):
     q=tr[i]
     if q.GetClass()!='PCB_TRACK':continue
     if q.GetNetname() in ('/EFUSE_DVDT','/EFUSE_ILM') and q.GetLayer()==pcbnew.In2_Cu:
      remove.append(q);continue
     if q.GetLayer()!=pcbnew.F_Cu:continue
     a=q.GetStart();z=q.GetEnd();xy=tuple(round(to(w),4) for w in (a.x,a.y,z.x,z.y))
     key=(q.GetNetname(),xy)
     if key in old:remove.append(q);found.add(key)
    if old - found or len(remove) != 27:
     raise RuntimeError('reinforce_5v_sys: unexpected pre-route copper: %s, %d' % (old-found,len(remove)))
    vremove=[]
    for i in range(len(tr)):
     q=tr[i]
     if q.GetClass()!='PCB_VIA':continue
     v=q.GetPosition();x,y=round(to(v.x),4),round(to(v.y),4)
     if (q.GetNetname(),x,y) in {('/GND',11.0,157.75),('/EFUSE_ILM',19.9298,159.2497),('/EFUSE_DVDT',22.29,159.8199)}:
      vremove.append(q)
    for q in remove+vremove:b.Remove(q)
    if len(vremove) != 3:
     raise RuntimeError('reinforce_5v_sys: expected 3 obsolete vias, found %d' % len(vremove))
    def p(x,y):return pcbnew.VECTOR2I(mm(x),mm(y))
    def track(a,z,w):
     t=pcbnew.PCB_TRACK(b);t.SetStart(p(*a));t.SetEnd(p(*z));t.SetWidth(mm(w));t.SetLayer(pcbnew.F_Cu);t.SetNet(n);b.Add(t)
    track((11.26,156),(11.26,153.8),.3)
    track((11.26,153.8),(9.5375,152),1.0)
    vv=pcbnew.PCB_VIA(b);vv.SetPosition(p(11.26,154.3));vv.SetWidth(mm(.6));vv.SetDrill(mm(.3));vv.SetNet(n);b.Add(vv)
    q=pcbnew.PCB_TRACK(b);q.SetStart(p(11.26,154.3));q.SetEnd(p(12.5,156.47));q.SetWidth(mm(1.0));q.SetLayer(pcbnew.In2_Cu);q.SetNet(n);b.Add(q)
    track((11.0,162.0),(20.0,162.0),1.2)
    track((20.0,162.0),(34.0,162.0),2.0)
    track((11.26,156),(11.26,157.75),.3)
    track((11.26,157.75),(12.0,157.75),.3)
    vv=pcbnew.PCB_VIA(b);vv.SetPosition(p(12.0,157.75));vv.SetWidth(mm(.6));vv.SetDrill(mm(.3));vv.SetNet(n);b.Add(vv)
    vv=pcbnew.PCB_VIA(b);vv.SetPosition(p(34.0,162.0));vv.SetWidth(mm(.6));vv.SetDrill(mm(.3));vv.SetNet(n);b.Add(vv)
    q=pcbnew.PCB_TRACK(b);q.SetStart(p(14.1,162.0));q.SetEnd(p(18.0,162.0));q.SetWidth(mm(2.4));q.SetLayer(pcbnew.B_Cu);q.SetNet(n);b.Add(q)
    q=pcbnew.PCB_TRACK(b);q.SetStart(p(18.0,162.0));q.SetEnd(p(22.0,162.0));q.SetWidth(mm(2.4));q.SetLayer(pcbnew.B_Cu);q.SetNet(n);b.Add(q)
    q=pcbnew.PCB_TRACK(b);q.SetStart(p(22.0,162.0));q.SetEnd(p(34.0,162.0));q.SetWidth(mm(3.1));q.SetLayer(pcbnew.B_Cu);q.SetNet(n);b.Add(q)
    vv=pcbnew.PCB_VIA(b);vv.SetPosition(p(33.0,162.0));vv.SetWidth(mm(.6));vv.SetDrill(mm(.3));vv.SetNet(n);b.Add(vv)
    q=pcbnew.PCB_TRACK(b);q.SetStart(p(14.1,162.0));q.SetEnd(p(18.0,162.0));q.SetWidth(mm(2.4));q.SetLayer(pcbnew.In2_Cu);q.SetNet(n);b.Add(q)
    q=pcbnew.PCB_TRACK(b);q.SetStart(p(18.0,162.0));q.SetEnd(p(22.0,162.0));q.SetWidth(mm(2.4));q.SetLayer(pcbnew.In2_Cu);q.SetNet(n);b.Add(q)
    q=pcbnew.PCB_TRACK(b);q.SetStart(p(22.0,162.0));q.SetEnd(p(33.0,162.0));q.SetWidth(mm(3.0));q.SetLayer(pcbnew.In2_Cu);q.SetNet(n);b.Add(q)
    q=pcbnew.PCB_TRACK(b);q.SetStart(p(12.0,157.75));q.SetEnd(p(12.0,160.3));q.SetWidth(mm(1.5));q.SetLayer(pcbnew.In1_Cu);q.SetNet(n);b.Add(q)
    q=pcbnew.PCB_TRACK(b);q.SetStart(p(12.0,160.3));q.SetEnd(p(14.1,162.0));q.SetWidth(mm(1.5));q.SetLayer(pcbnew.In1_Cu);q.SetNet(n);b.Add(q)
    g=b.FindNet('/GND');vb=b.FindNet('/VBUS_F');dv=b.FindNet('/EFUSE_DVDT')
    def nettrack(a,z,w,net,layer=pcbnew.F_Cu):
     q=pcbnew.PCB_TRACK(b);q.SetStart(p(*a));q.SetEnd(p(*z));q.SetWidth(mm(w));q.SetLayer(layer);q.SetNet(net);b.Add(q)
    def via(x,y,net):
     q=pcbnew.PCB_VIA(b);q.SetPosition(p(x,y));q.SetWidth(mm(.6));q.SetDrill(mm(.3));q.SetNet(net);b.Add(q)
    nettrack((11.0,159.05),(8.9,159.05),.3,g)
    via(8.9,159.05,g)
    nettrack((11.91,156.23),(15.775,156.23),.2,g)
    nettrack((15.775,156.23),(15.775,155.0),.2,g)
    nettrack((15.975,153.5),(15.775,155.0),.3,g)
    nettrack((10.77,156.0),(10.77,157.8),.3,vb)
    nettrack((10.77,157.8),(10.6,157.8),.3,vb)
    via(10.6,157.8,vb)
    nettrack((10.6,157.8),(10.6,159.8),1.0,vb,pcbnew.B_Cu)
    nettrack((10.6,159.8),(12.5,159.4),1.0,vb,pcbnew.B_Cu)
    nettrack((12.5,159.4),(18.87,158.0),1.0,vb,pcbnew.B_Cu)
    nettrack((18.87,158.0),(19.67,158.0),1.0,vb,pcbnew.B_Cu)
    nettrack((19.67,158.0),(20.47,158.0),1.0,vb,pcbnew.B_Cu)
    nettrack((18.87,158.0),(21.675,158.0),.5,vb)
    nettrack((11.91,156.9),(13.225,156.9207),.15,dv)
    via(15.0,154.8,dv)
    nettrack((14.0543,157.75),(15.0,154.8),.2,dv,pcbnew.B_Cu)
    nettrack((14.425,153.5),(15.0,154.8),.2,dv)
    en=b.FindNet('/PWR_EN');ilm=b.FindNet('/EFUSE_ILM');ovlo=b.FindNet('/EFUSE_OVLO')
    nettrack((10.09,155.1),(8.7,155.1),.2,en)
    nettrack((8.7,155.1),(8.7,155.5),.2,en)
    via(8.7,155.5,en)
    nettrack((8.7,155.5),(10.0,156.0),.2,en,pcbnew.In4_Cu)
    nettrack((10.0,156.0),(10.0,158.5),.2,en,pcbnew.In4_Cu)
    nettrack((10.0,158.5),(13.0,158.5),.2,en,pcbnew.In4_Cu)
    nettrack((13.0,158.5),(15.7372,160.2652),.2,en,pcbnew.In4_Cu)
    nettrack((11.91,155.77),(12.5,155.77),.15,ilm)
    nettrack((12.5,155.77),(12.5,154.1),.15,ilm)
    via(12.5,154.1,ilm)
    nettrack((12.5,154.1),(16.4263,156.7487),.2,ilm,pcbnew.In4_Cu)
    nettrack((10.09,155.77),(9.2,155.77),.15,ovlo)
    nettrack((9.2,155.77),(9.2,156.7),.15,ovlo)
    via(9.2,156.7,ovlo)
    for a,z in zip(((9.2,156.7),(9.7,157.0),(9.7,160.8)),
                   ((9.7,157.0),(9.7,160.8),(14.2,160.3))):
     nettrack(a,z,.2,ovlo,pcbnew.B_Cu)
    via(14.2,160.3,ovlo)
    nettrack((14.2,160.3),(15.1413,159.482),.15,ovlo)

    # The buck's two VIN paths can use the open space beside its output
    # capacitor. Keep the pad-4 final segment at 0.9 mm for PG pad clearance.
    buck_widths = {
        (34.0, 163.0, 40.0, 163.0): 1.9,
        (34.0, 162.0, 34.0, 163.0): 2.0,
        (34.0, 160.775, 35.5, 160.775): 1.0,
        (35.5, 160.775, 35.5, 159.05): 1.0,
        (35.5, 159.05, 36.85, 159.05): 0.9,
        (34.0, 162.0, 34.0, 160.775): 1.0,
    }
    matched = set()
    items = b.Tracks()
    for i in range(len(items)):
        item = items[i]
        if item.GetClass() != "PCB_TRACK" or item.GetNetname() != "/5V_SYS" or item.GetLayer() != pcbnew.F_Cu:
            continue
        a, z = item.GetStart(), item.GetEnd()
        ends = tuple(round(to(v), 3) for v in (a.x, a.y, z.x, z.y))
        if ends in buck_widths:
            item.SetWidth(mm(buck_widths[ends]))
            matched.add(ends)
    if matched != set(buck_widths):
        raise RuntimeError("reinforce_5v_sys: buck VIN copper changed: %s" % (set(buck_widths) - matched,))
