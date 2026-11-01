import pandas as pd
from native_volume_audit import native_opening
def test_native_volume_counts_bid_updates_not_ask_only():
    f=pd.DataFrame(dict(time=pd.to_datetime(['2025-02-03 08:00Z','2025-02-03 08:01Z','2025-02-03 08:02Z']),bid=[1.,1.,1.01],ask=[1.001,1.002,1.011],flags=[2,4,6]))
    native=native_opening(f,'2025-02-03')
    assert native['volume']==2 and native['direction']==1
