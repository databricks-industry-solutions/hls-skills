#!/usr/bin/env python3
"""
Synthetic data generator for the accelerators skill evaluation.

Creates small, fully synthetic inputs so the steering tasks reference real files:
  1. dicom/   3 CT studies x 2 series x 3 instances (pydicom, no patient data)  (acc-001)
  2. outputs/ empty folder where Genie Code saves its final answers

No accelerator needs to be installed. The tasks score whether Genie Code steers
to the right accelerator and gives a precise next step, not whether it runs it.

Usage:
    pip install pydicom numpy
    python3 generate_data.py

Output volume (override via SKILL_EVAL_DATA_DIR):
    /Volumes/hls_amer_catalog/vital_skills/eval/accelerators/
"""

import os

import numpy as np
import pydicom
from pydicom.dataset import FileDataset, FileMetaDataset
from pydicom.uid import CTImageStorage, ExplicitVRLittleEndian, generate_uid

OUT_DIR = os.environ.get("SKILL_EVAL_DATA_DIR", "/Volumes/hls_amer_catalog/vital_skills/eval/accelerators")
RNG = np.random.default_rng(42)


def write_dicom(path: str, patient_id: str, study_uid: str, series_uid: str, series_no: int, instance_no: int) -> None:
    meta = FileMetaDataset()
    meta.MediaStorageSOPClassUID = CTImageStorage
    meta.MediaStorageSOPInstanceUID = generate_uid()
    meta.TransferSyntaxUID = ExplicitVRLittleEndian

    ds = FileDataset(path, {}, file_meta=meta, preamble=b"\0" * 128)
    ds.SOPClassUID = CTImageStorage
    ds.SOPInstanceUID = meta.MediaStorageSOPInstanceUID
    ds.PatientID = patient_id
    ds.PatientName = f"SYNTHETIC^{patient_id}"
    ds.StudyInstanceUID = study_uid
    ds.SeriesInstanceUID = series_uid
    ds.StudyDate = "20260101"
    ds.Modality = "CT"
    ds.BodyPartExamined = "CHEST"
    ds.SeriesNumber = series_no
    ds.InstanceNumber = instance_no
    ds.Rows = ds.Columns = 32
    ds.SamplesPerPixel = 1
    ds.PhotometricInterpretation = "MONOCHROME2"
    ds.BitsAllocated = ds.BitsStored = 16
    ds.HighBit = 15
    ds.PixelRepresentation = 1
    ds.PixelData = RNG.integers(-1000, 1000, (32, 32), dtype=np.int16).tobytes()
    ds.save_as(path, enforce_file_format=True)


def make_dicom(out: str) -> int:
    os.makedirs(out, exist_ok=True)
    n = 0
    for p in range(1, 4):
        patient_id = f"EVAL{p:03d}"
        study_uid = generate_uid()
        for s in range(1, 3):
            series_uid = generate_uid()
            for i in range(1, 4):
                write_dicom(f"{out}/{patient_id}_s{s}_i{i}.dcm", patient_id, study_uid, series_uid, s, i)
                n += 1
    return n



if __name__ == "__main__":
    n_dcm = make_dicom(f"{OUT_DIR}/dicom")
    os.makedirs(f"{OUT_DIR}/outputs", exist_ok=True)
    print(f"Wrote {n_dcm} DICOM files under {OUT_DIR}")
