"""Check the locked dataset; no dataset files are written or models run."""
import argparse
import json
import os
import subprocess
import sys
import tempfile
import xml.etree.ElementTree as ET
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import torch
from torch.utils.data import DataLoader
from src.data.dataset_loader import DatasetLoader
from src.data.encounter_dataset import EncounterDataset
from src.data.vessel_dataset import VesselDataset


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--dataset-root')
    args = parser.parse_args()
    loader = DatasetLoader(args.dataset_root)
    report = {'dataset_version': loader.lock['dataset_version'], 'dataset_lock_status': loader.lock['lock_status'], 'splits': {}}
    try:
        report['dataset_root'] = loader.root.relative_to(ROOT).as_posix()
    except ValueError:
        report['dataset_root'] = 'external dataset root (omitted)'
    loaded = {}
    for name in ('train','validation','test'):
        s = loader.load_split(name)
        if name != 'test':
            loaded[name] = s
        arrays = {k:{'shape':list(getattr(s,k).shape),'dtype':str(getattr(s,k).dtype)} for k in ('X','displacement','common','anchors','labels')}
        report['splits'][name] = {'encounters':len(s.encounters),'vessels':len(s.vessels),'records':s.records,'tensors':arrays}
        print(name, report['splits'][name])
    mapping = {}
    for name, s in loaded.items():
        vd, ed = VesselDataset(s), EncounterDataset(s)
        for i in (0, len(ed)//2, len(ed)-1):
            item = ed[i]; rows = s.pairs[i]
            assert s.vessels.iloc[rows].vessel.tolist() == ['A','B']
            assert item['encounter_id'] == s.encounters.iloc[i].encounter_id
            assert torch.equal(item['model_input']['X'][0], vd[int(rows[0])]['X'])
            assert torch.equal(item['model_input']['X'][1], vd[int(rows[1])]['X'])
        mapping[name] = {'status':'PASS','vessel_dataset_length':len(vd),'encounter_dataset_length':len(ed),'samples_checked':3}
    report['index_mapping'] = mapping
    dl = DataLoader(VesselDataset(loaded['train']), batch_size=256, shuffle=False, drop_last=False, num_workers=0)
    count = 0
    for batch in dl:
        b = batch['X'].shape[0]; count += b
        assert batch['X'].shape == (b,10,4) and batch['Y'].shape == (b,15,2)
        assert torch.isfinite(batch['X']).all() and torch.isfinite(batch['Y']).all()
        if count == b:
            first = {'X':list(batch['X'].shape),'Y':list(batch['Y'].shape)}
    assert count == 2880 and b == 64
    report['dataloader'] = {'first_batch_shapes':first,'final_batch_size':b,'total_vessels':count}
    with tempfile.TemporaryDirectory(prefix='dataset_tests_') as tmp:
        xml = Path(tmp) / 'pytest.xml'
        env = os.environ.copy(); env['DATASET_ROOT'] = str(loader.root)
        result = subprocess.run([sys.executable,'-m','pytest','tests/unit/test_dataset_loader.py','-q',f'--junitxml={xml}'], cwd=ROOT, env=env, text=True, capture_output=True)
        print(result.stdout, result.stderr)
        if result.returncode != 0:
            raise RuntimeError('Unit tests failed')
        suites = ET.parse(xml).getroot()
        suite = suites if suites.tag == 'testsuite' else suites.find('testsuite')
        total = int(suite.attrib['tests']); failures = int(suite.attrib['failures']); errors = int(suite.attrib['errors']); skipped = int(suite.attrib['skipped'])
        if failures or errors or skipped or not total:
            raise RuntimeError('Unit tests did not all pass')
        report['unit_tests'] = {'total':total,'passed':total-failures-errors-skipped,'failures':failures,'errors':errors,'skipped':skipped}
    report['smoke_test_status'] = 'PASS'
    report['known_limitations'] = ['Test inspected for tensor structure and index metadata only; no inference or evaluation.', 'Deep reconstruction and leakage audits deferred to step 5.', 'Dataset checksums verified separately.']
    dest = ROOT / 'results/s1_t01/dataset_loader_smoke_test.json'
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
    print('PASS: dataset read only; report:', dest.relative_to(ROOT))


if __name__ == '__main__':
    main()
