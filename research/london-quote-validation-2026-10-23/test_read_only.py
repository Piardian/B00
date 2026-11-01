import ast
from pathlib import Path
import pandas as pd
from collect_mt5 import schedule,SYMBOLS

def test_collector_has_no_order_login_or_account_mutation_calls():
    source=Path(__file__).with_name('collect_mt5.py').read_text()
    tree=ast.parse(source)
    calls={n.func.attr for n in ast.walk(tree) if isinstance(n,ast.Call) and isinstance(n.func,ast.Attribute) and isinstance(n.func.value,ast.Name) and n.func.value.id=='mt5'}
    assert calls<= {'initialize','account_info','symbol_info','copy_ticks_range','last_error','shutdown'}
    assert 'copy_ticks_range' in calls

def test_locked_periods_and_fourteen_warmup_days():
    plan=schedule();warm=[d for d,w in plan if w];evaluation=[d for d,w in plan if not w]
    assert len(warm)==14 and len(evaluation)==41 and len(SYMBOLS)==6
    assert all(d[:7] in ['2025-02','2025-03'] for d in evaluation)
    assert max(warm)<min(evaluation)
