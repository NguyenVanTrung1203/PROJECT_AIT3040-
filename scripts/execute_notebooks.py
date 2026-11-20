import datetime
import importlib.metadata as md
import json
import os
import sys
import tempfile
from pathlib import Path

import nbformat
from nbclient import NotebookClient

root = Path(__file__).resolve().parents[1]
paths = ['notebooks/01_dataset_overview.ipynb','notebooks/02_feature_tensor_analysis.ipynb']
reports = []
with tempfile.TemporaryDirectory(prefix='ait3040_kernel_') as temp:
    kernel = Path(temp) / 'kernels' / 'ait3040-temporary'
    kernel.mkdir(parents=True)
    (kernel / 'kernel.json').write_text(json.dumps({'argv':[sys.executable,'-m','ipykernel_launcher','-f','{connection_file}'],'display_name':'temporary','language':'python'}), encoding='utf-8')
    os.environ['JUPYTER_PATH'] = temp + os.pathsep + os.environ.get('JUPYTER_PATH','')
    for name in paths:
        path = root/name
        nb = nbformat.read(path, as_version=4)
        NotebookClient(nb, kernel_name='ait3040-temporary', timeout=300, resources={'metadata':{'path':str(root)}}).execute()
        nb.metadata.kernelspec = {'display_name':'Python 3 (ipykernel)','language':'python','name':'python3'}
        nbformat.write(nb,path)
        errors = sum(1 for cell in nb.cells for output in cell.get('outputs',[]) if output.output_type == 'error')
        assert errors == 0
        reports.append({'path':name,'status':'PASS','cells':len(nb.cells),'code_cells':sum(c.cell_type=='code' for c in nb.cells),'execution_errors':errors,'bytes':path.stat().st_size})
        print(name, 'PASS', path.stat().st_size, 'bytes')
report = {'notebooks':reports,'executed_at_utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),'python':'.'.join(map(str,sys.version_info[:3])), 'dependencies':{p:md.version(p) for p in ('jupyterlab','ipykernel','nbformat','nbclient')}}
(root/'results/s1_t01/notebook_execution_report.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
