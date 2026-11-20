"""Verify contract and persist a compact report; nonzero exit means failure."""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from src.data.tensor_verification import verify

if __name__ == '__main__':
    result = verify()
    output = ROOT / 'results/s1_t01/tensor_contract_verification.json'
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(result, indent=2))
