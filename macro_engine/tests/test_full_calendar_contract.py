import datetime as dt
import pandas as pd
import pytest
from calibration.full_system_reconstruction import calendar_for
from data_quality import DataUnavailableError


def test_historical_calendar_does_not_add_actuals_absent_from_live_feed(tmp_path):
    rows=[{'DateTime':t,'Currency':'USD','Impact':impact,'Event':'Non-Farm Employment Change',
           'Actual':'256K','Forecast':'164K','Previous':'212K'} for t,impact in [
               ('2025-01-05T00:00Z','Low'),('2025-01-06T09:00Z','High'),('2025-01-11T23:59Z','Low')]]
    path=tmp_path/'calendar.csv';pd.DataFrame(rows).to_csv(path,index=False)
    result=calendar_for(dt.datetime(2025,1,6,10,tzinfo=dt.timezone.utc),path)
    assert len(result)==1
    assert set(result[0])=={'title','country','impact','date','forecast','previous'}
    assert 'actual' not in result[0]


def test_missing_month_cannot_be_treated_as_no_events(tmp_path):
    path=tmp_path/'calendar.csv'
    pd.DataFrame([dict(DateTime='2025-01-01T00:00Z',Currency='USD',Impact='High',Event='CPI',Actual='0.3%',Forecast='0.2%',Previous='0.2%')]).to_csv(path,index=False)
    with pytest.raises(DataUnavailableError):
        calendar_for(dt.datetime(2025,6,6,tzinfo=dt.timezone.utc),path)
