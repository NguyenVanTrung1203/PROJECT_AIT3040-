"""Keep forecast inputs separate from future outcomes and evaluation metadata."""
import numpy as np
import torch
from torch.utils.data import Dataset


def _tensor(value):
    return torch.from_numpy(np.array(value, dtype=np.float32, copy=True))


class EncounterDataset(Dataset):
    def __init__(self, split):
        self.split = split

    def __len__(self):
        return len(self.split.encounters)

    def __getitem__(self, index):
        if not 0 <= index < len(self):
            raise IndexError(index)
        s = self.split
        rows = s.pairs[index]
        meta = s.metadata.iloc[index]
        return {'encounter_id': str(s.encounters.iloc[index].encounter_id),
                'vessel_ids': [str(s.vessels.iloc[int(i)].vessel_id) for i in rows],
                'model_input': {'X': _tensor(s.X[rows]), 'anchors_EN_nm': torch.from_numpy(np.array(s.anchors[index], copy=True))},
                'ground_truth': {'target_EN_nm': _tensor(s.common[index]), 'label': int(s.labels[index])},
                'metadata': {k: None if meta[k] is None or (isinstance(meta[k], float) and np.isnan(meta[k])) else str(meta[k])
                             for k in ('data_source','scenario','difficulty','method') if k in meta.index}}
