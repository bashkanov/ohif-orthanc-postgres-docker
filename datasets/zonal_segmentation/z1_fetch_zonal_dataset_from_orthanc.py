############################################################
##
##  This code provides the scripts for an orginized 
##  dataset generation for DICOM data from orthanc server. 
##
############################################################

import os
import hashlib
import re
import glob
import pydicom
import pydicom_seg
import pyorthanc
import tempfile
import shutil
import pandas as pd
import SimpleITK as sitk 
import subprocess as sp
import httpx

from tqdm import tqdm
from pyorthanc import Orthanc, Study

from httpx import HTTPError
from datetime import datetime
from pyorthanc import Orthanc
from collections import defaultdict
from pyorthanc import Orthanc, Study, Series
import memory_tempfile

from utils.utils import get_orthanc_client, convert_dicom, open_zipped_dicom, get_orthanc_series_id, get_referenced_series, get_nrrd_from_instances_list, current_sequence_map_path
current_sequence_map = pd.read_csv(current_sequence_map_path, sep=";")
                        
def group_dwi_by_bval(instances):
    dwi_instances = defaultdict(list)
    for instance in instances:

        b_val = 'none'
        # siemens            
        if '0018,0024' in instance.tags:
            b_val = instance.tags['0018,0024']['Value']
        
        # phillips  (if b value is still none)
        if '0018,9087' in instance.tags and b_val in ['none', ''] :
            b_val = instance.tags['0018,9087']['Value']

        b_val_matches = re.findall(r'\d+', b_val)
        if len(b_val_matches) == 1: 
            b_val = b_val_matches[0]
        else:
            b_val = 'none'
        
        dwi_instances[b_val].append(instance)
        
    return dwi_instances


def retrieve_study_from_othanc(row, target_dir_root, use_ref_t2w=False, include_segmentation=False):
    target_dir = os.path.join(target_dir_root, row['study_orthanc_id'])
    os.makedirs(target_dir, exist_ok=True)
    
    if use_ref_t2w:
        t2w_oid = row['t2w_ref_oid']
    else:
        t2w_oid = row['t2w_tra_id']
        
    t2w_series = pyorthanc.Series(t2w_oid, orthanc_client)
    get_nrrd_from_instances_list(orthanc_client, t2w_series.instances, target_dir, t2w_oid, "tw2_tra")
    
    if not pd.isna(row['adc_tra_id']):
        adc_series = pyorthanc.Series(row['adc_tra_id'], orthanc_client)
        get_nrrd_from_instances_list(orthanc_client, adc_series.instances, target_dir, row['adc_tra_id'], "adc_tra")
    
    # it handles both cases: 1. where all b-value dwi are under same Series and 
    # 2. where differnt b-value corresponds to different Series.
    if not pd.isna(row['dwi_tra_id']):
        for dwi_oid in row[ 'dwi_tra_id'].split(','):
            dwi_series = pyorthanc.Series(dwi_oid, orthanc_client)
            dwi_instances_grouped = group_dwi_by_bval(dwi_series.instances)
            for dwi_key, dwi_instances_bval in dwi_instances_grouped.items():
                get_nrrd_from_instances_list(orthanc_client,  dwi_instances_bval, target_dir, dwi_oid, f"dwi_tra_bval_{dwi_key}")
                
    return True  # Indicate that the function has completed its execution


def retrieve_zonal_dataset_multimodal(dicom_segm_path):
    print("retrieve zonal dataset (IDs) from dicom segmentations...")
    records = [] 
    some_missing = []
    segmentations = glob.glob(os.path.join(dicom_segm_path, "*/seg.dcm.gz"))
    for seg_path in tqdm(segmentations[:]):

        dataset = open_zipped_dicom(seg_path)
        orthanc_series_t2w_ref, _, _ = get_referenced_series(orthanc_client, dataset)
        try:
            series = Series(orthanc_series_t2w_ref, orthanc_client)
            study = series.parent_study
            main_info = study.get_main_information()
            study_date = main_info['MainDicomTags']['StudyDate']
            study_UID = main_info['MainDicomTags']['StudyInstanceUID']
            patient_id = main_info['PatientMainDicomTags']['PatientID']
            
            d = {
                'study_date': study_date, 
                'patient_id': patient_id,
                'StudyInstanceUID': study_UID,
                'study_orthanc_id': study.id_,
                't2w_ref_oid': orthanc_series_t2w_ref
            }

            records.append(d)
        except httpx.HTTPError as e:
            print(f'A HTTPError was thrown: {e} ')
            some_missing.append(orthanc_series_t2w_ref)
    
    metadata_zone = pd.DataFrame(records)
    merged = pd.merge(metadata_zone, current_sequence_map, on='study_orthanc_id', how='left')
    if some_missing:
        print("some_missing", some_missing)
    return merged
       
        
def convert_dicom_zonal_segmentations(orthanc_client, target_dir, dicom_segm_path):
    print(f"Converting dcm segms into nrrd... {target_dir}")    
    segmentations = glob.glob(os.path.join(dicom_segm_path, "*/seg.dcm.gz"))
    for seg_path in tqdm(segmentations[:]):

        dataset = open_zipped_dicom(seg_path)
        orthanc_series_t2w_ref, _, _ = get_referenced_series(orthanc_client, dataset)
        if orthanc_series_t2w_ref is None:
            print(f"series_id was empty!")
            continue 
        
        series = Series(orthanc_series_t2w_ref, orthanc_client)
        study = series.parent_study
        study_orthanc_id = study.id_
        
        target_dir_tmp = os.path.join(target_dir, study_orthanc_id)
        os.makedirs(target_dir_tmp, exist_ok=True)

        reader = pydicom_seg.MultiClassReader()
        result = reader.read(dataset)
        image = result.image  # lazy construction
        sitk.WriteImage(image, os.path.join(target_dir_tmp, 'Segmentation-label-altaai.seg.nrrd'), True)


if __name__=='__main__':
    # test conntection
    orthanc_client = get_orthanc_client()
    patient_ids = orthanc_client.get_patients()
    len(patient_ids)
    
    exported_dcm_segs = "/data/oleksii/Prostate-ZONE-Datasets-NRRDS/export-zone.alta-ai.com-2024-08-07/prostate_zone/ProcessingState.PERFECT"
    target_dir_seg = "/data/oleksii/Prostate-ZONE-Datasets-NRRDS/ALTA-Zone-Dataset-zone.alta-ai.com-seg/"
    target_dir_img = "/data/oleksii/Prostate-ZONE-Datasets-NRRDS/ALTA-Zone-Dataset-zone.alta-ai.com-img/"
    df = retrieve_zonal_dataset_multimodal(exported_dcm_segs)
    # convert_dicom_zonal_segmentations(orthanc_client, target_dir_seg, exported_dcm_segs)
    
    for i, (_, row) in enumerate(df.iterrows()):  
        print(f"processing {i}/{len(df)}...")
        retrieve_study_from_othanc(row, target_dir_img)
    