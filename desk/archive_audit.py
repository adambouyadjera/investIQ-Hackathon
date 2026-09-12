"""Cross-check a development month against Binance's separately published archive."""
import subprocess,zipfile,io,csv,hashlib,json
from pathlib import Path
from .market import normalize
ROOT=Path(__file__).resolve().parents[1]
def fetch(url):
    r=subprocess.run(['curl','--fail','--silent','--show-error','--max-time','30',url],capture_output=True,check=True)
    return r.stdout
base='https://data.binance.vision/data/spot/monthly/klines/BTCUSDT/1h/BTCUSDT-1h-2024-01.zip'
def main():
    raw=fetch(base);expected=fetch(base+'.CHECKSUM').decode().split()[0];actual=hashlib.sha256(raw).hexdigest()
    if actual!=expected:raise RuntimeError('Archive checksum mismatch')
    z=zipfile.ZipFile(io.BytesIO(raw));rows=list(csv.reader(io.StringIO(z.read(z.namelist()[0]).decode())))
    clean=normalize(rows,9999999999999)
    with (ROOT/'data/btcusdt_1h.csv').open() as f:local={int(r['time']):r for r in csv.DictReader(f)}
    disagreements=[]
    for r in clean:
        if r['time'] not in local:disagreements.append({'time':r['time'],'error':'missing from API snapshot'});continue
        for k in ['open','high','low','close','volume']:
            if abs(r[k]-float(local[r['time']][k]))>1e-7:disagreements.append({'time':r['time'],'field':k})
    out={'month':'2024-01','url':base,'sha256':actual,'checksum_verified':True,'bars_compared':len(clean),'disagreements':disagreements,'same_exchange_independent_publication':True,'holdout_accessed':False}
    (ROOT/'reports/archive-audit.json').write_text(json.dumps(out,indent=2));print(json.dumps(out,indent=2))
if __name__=='__main__':main()
