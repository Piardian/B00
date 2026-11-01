"""Lossless storage repair on this experiment's new tapes only; no outcomes."""
from pathlib import Path
import shutil
import pandas as pd
import study as s
g=s.g

def main():
    s.verify();manifest=s.read('quote_manifest.json');old=s.BASE/'quote_manifest_before_repack.json'
    assert not old.exists();shutil.copyfile(s.BASE/'quote_manifest.json',old)
    g.save(s.BASE/'storage_repair_protocol.json',dict(rule='Reencode every new tape chronological order with delta-packed timestamp and same float64 values; exact dataframe equality before replacement. No row edits/deletions or outcome checks.',
        hashes={str(p):g.sha(p) for p in [Path(__file__),s.BASE/'resume_guard.ps1',old]},resume='Only remaining warm-cache dates, initially>=1.125GiB, unchanged internal1100MiB and external1GiB emergency guard. Resume initial threshold lower than original2GiB because remaining dates fewer than one month and caches verified; no cold download.',orders_sent=False))
    before=after=0;count=0
    for date,meta in sorted(manifest['files'].items()):
        if meta.get('reused') or meta['status']!='AVAILABLE':continue
        path=Path(meta['path']);assert path.resolve().parent==(s.BASE/'tapes').resolve()
        assert g.sha(path)==meta['sha256'];f=pd.read_parquet(path);tmp=path.with_suffix('.repack')
        f.to_parquet(tmp,compression='zstd',compression_level=9,use_dictionary=False,column_encoding={'time':'DELTA_BINARY_PACKED','bid':'BYTE_STREAM_SPLIT','ask':'BYTE_STREAM_SPLIT'})
        pd.testing.assert_frame_equal(f,pd.read_parquet(tmp),check_exact=True)
        prior=meta['sha256'];a=path.stat().st_size;b=tmp.stat().st_size
        tmp.replace(path);meta['sha256']=g.sha(path);meta['storage_history']=dict(previous_sha256=prior,exact_frame_equal=True,before_bytes=a,after_bytes=b)
        s.save('quote_manifest.json',manifest);before+=a;after+=b;count+=1
    s.save('storage_repair_result.json',dict(files=count,before_bytes=before,after_bytes=after,saved_bytes=before-after,all_frames_exact=True,free_bytes=shutil.disk_usage(s.BASE).free))
    print('LOSSLESS_REPACK',count,'savedMiB',round((before-after)/1024**2,2),'freeGiB',round(shutil.disk_usage(s.BASE).free/1024**3,2),flush=True)

if __name__=='__main__':main()
