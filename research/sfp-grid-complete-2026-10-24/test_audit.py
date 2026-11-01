import ast,copy
import pandas as pd
import complete as s
from collect import clock_qa
from funnel import instrument,STAGES

def sample():
    at=pd.Timestamp('2025-02-03 08:00',tz='UTC')
    starts=pd.date_range(at,periods=12,freq='15min')
    reference=pd.DataFrame(dict(datetime=starts,close=[1.1+i*.0001 for i in range(12)]))
    tape=pd.DataFrame(dict(time=starts+pd.Timedelta(minutes=14,seconds=59),bid=reference.close))
    return at,reference,tape

def test_quote_to_native_clock_alignment_passes():
    at,ref,f=sample()
    assert clock_qa(f,ref,at,at+pd.Timedelta(hours=3),.00001)['passed']

def test_wrong_hour_alignment_fails():
    at,ref,f=sample();f.time+=pd.Timedelta(hours=1)
    assert not clock_qa(f,ref,at,at+pd.Timedelta(hours=4),.00001)['passed']

def test_too_little_reference_does_not_get_clock_certificate():
    at,ref,f=sample()
    assert not clock_qa(f.iloc[:4],ref,at,at+pd.Timedelta(hours=3),.00001)['passed']

def test_instrumentation_removes_to_exact_original_ast():
    m=s.measure();c,d,e=m.engine()
    fn,tags=instrument(d,lambda stage:None)
    assert set(tags)==set(STAGES)-{'CALL'}
    text=(s.HERE/'frozen_engine/sfp_detector.py').read_text(encoding='utf8')
    tree=ast.parse(text);cls=next(n for n in tree.body if isinstance(n,ast.ClassDef) and n.name=='SFPDetector')
    original=next(n for n in cls.body if isinstance(n,ast.FunctionDef) and n.name=='_detect_confirmed_sfp')
    from funnel import Insert,event
    modified=Insert().visit(copy.deepcopy(original));modified.body.insert(0,event('CALL'))
    class Strip(ast.NodeTransformer):
        def visit_Expr(self,node):
            if isinstance(node.value,ast.Call) and isinstance(node.value.func,ast.Name) and node.value.func.id=='_audit_stage':return None
            return self.generic_visit(node)
    assert ast.dump(Strip().visit(modified),include_attributes=False)==ast.dump(original,include_attributes=False)
