"""Read one unscaled vessel history and anchor-relative future at a time."""
import numpy as np
import torch
from torch.utils.data import Dataset


class VesselDataset(Dataset):
    def __init__(self, split):
        self.split = split

    def __len__(self):
        return len(self.split.X)

    def __getitem__(self, index):
        if not 0 <= index < len(self):
            raise IndexError(index)
        row = self.split.vessels.iloc[index]
        return {'X': torch.from_numpy(np.array(self.split.X[index], dtype=np.float32, copy=True)),
                'Y': torch.from_numpy(np.array(self.split.displacement[index], dtype=np.float32, copy=True)),
                'encounter_id': str(row.encounter_id), 'vessel': str(row.vessel),
                'vessel_id': str(row.vessel_id), 'X_row': int(row.X_row)}
