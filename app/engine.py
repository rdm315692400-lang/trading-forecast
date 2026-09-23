def forecast(ticker,x):
    if x.empty: raise ValueError("אין נתונים")
    reg=x[(x.minute>=570)&(x.minute<=960)]
    days=[]
    for _,g in reg.groupby("day"):
        if len(g)<100: continue
        o=float(g.iloc[0].open)
        days.append(((float(g.high.max())/o-1)*100,(float(g.low.min())/o-1)*100,int(g.loc[g.high.idxmax()].minute),int(g.loc[g.low.idxmin()].minute)))
    if len(days)<5: raise ValueError("אין מספיק היסטוריית דקות")
    import pandas as pd
    z=pd.DataFrame(days,columns=["up","down","ht","lt"]); ref=float(x.close.iloc[-1]); buy=float(x.close.iloc[-1]-x.open.iloc[-1])>=0
    ph=ref*(1+z.up.tail(20).quantile(.70)/100); pl=ref*(1+z.down.tail(20).quantile(.30)/100)
    fmt=lambda m:f"{int(m)//60:02d}:{int(m)%60:02d} ET"
    return {"ticker":ticker,"action":"קנייה" if buy else "מכירה","entry_price":round(ref,3),"exit_price":round(ph*.997 if buy else pl*1.003,3),"entry_time":fmt(z.lt.tail(20).median() if buy else z.ht.tail(20).median()),"exit_time":fmt(z.ht.tail(20).median() if buy else z.lt.tail(20).median()),"potential":round(abs((ph/ref-1 if buy else pl/ref-1))*100,2)}
