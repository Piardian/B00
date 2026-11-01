from pathlib import Path
from datetime import datetime,timezone
import hashlib,json
BASE=Path(__file__).resolve().parent;ROOT=BASE.parents[1]
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def freeze():
    files=[BASE/p for p in ['quote_engine.py','collect_mt5.py','test_quotes.py','run_validation.py','protocol.py']]
    files += [ROOT/'data/full_2025_study/broker_timezone_validation.json',BASE.parent/'london-classic-orb-2026-10-23/classic.py']
    d=dict(provider='Only The5ers FivePercentOnline-Real via explicit installed terminal; no alternate provider',
        months=['2025-02','2025-03'],symbols=['EURUSD','GBPUSD','USDJPY','USDCAD','USDCHF','NZDUSD'],
        hypotheses=['CLASSIC_RVOL_GE1(primary)','CLASSIC_ALL(control)'],
        fixed_rules='London08:00-08:15bidrange;openingcandle direction;firstbidbreak before12London;onepairday;oppositebidband structuralstop;fullTP2R;EODfirstquote>=16Londonwithin5seconds;no TP1,BE,HTF,Asiafilter or thresholdsearch',
        rvol='First15minutequote-eventcount / meanprevious14availableopeningquote-eventcounts,allfromsameThe5erssource;volumeproxy,notcentralizedFXvolume',
        execution='longbuysobservedask,exitbid;shortsellsbid,exitask;chronologicaltickorder;stopfillobservedworsequote;initialshortriskincludesentryobservedspread;brokerclockUS-DST UTC+2/3 as prior independentvalidation',
        costs='Observedbidask1x;0.1pipassumedslippageeachside;$4roundtrip/100kunitscommissionassumption,notverifiedhistoricalaccountcharges;stress1.5/2xobservedspread,fee,slippage;additional1pipspreadfloorstresspredeclaredafterrawprobehighzerospread',
        quality='NoPnLforcrossed/invalidquotes,missingopening/EOD,>60sectapegap;fullmonthreportrequiresallrequiredfilesorblockedstatus;no omittedmissingdataasflatprofit',
        inference='Different historical periods,notprospective;previousresearchmayhaveusedmarketregimes;allmodelscostsmonthsdisclosed,not guaranteeduntouchedglobalholdout;no portfolioaccountclaim',
        promotion='No live promotion; candidate only if primarybothmonthspositive,1.5/2xand1pipfloorpositive,>=100fills,and5observeddaybootstraplower>0;gateisresearchcriterion,notproof',
        files={str(p):sha(p) for p in files},read_only_market_access=True,live_orders_authorized=False)
    p=BASE/'protocol_frozen.json'
    if p.exists():
        if json.loads(p.read_text())['declaration']!=d:raise RuntimeError('Frozen validation changed')
    else:p.write_text(json.dumps(dict(frozen_utc=datetime.now(timezone.utc).isoformat(),declaration=d),indent=2),encoding='utf8')
    print('Frozen validation protocol')
if __name__=='__main__':freeze()
