############################################################
##
##  This code provides the scripts for an orginized 
##  dataset generation for DICOM data from orthanc server. 
##
############################################################

import os
import hashlib
import re
import pyorthanc
import tempfile
import pandas as pd
import subprocess as sp

from httpx import HTTPError
from collections import defaultdict
from utils.utils import get_orthanc_client,  sane_filename


dcm2niix_executable = "./dcm2niix/build/bin/dcm2niix"  
current_sequence_map = pd.read_csv("/home/oleksii/projects/ohif-orthanc-postgres-docker/sequence_mapping/sequence_mapping_13024_studies_20240115.csv", sep=';')

orthanc_client = get_orthanc_client()
                        
                        
def get_oid_from_uid(uid):
    study_candidates = orthanc_client.post_tools_lookup(data=uid)
    for i in study_candidates:
        if i['Type'] == 'Study':
            return i['ID']
    return None
                        
                        
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


def pad_string_with_dashes(string: str,
                           distance: int = 8):
    num_dashes = len(string) // distance

    if len(string) % distance == 0:
        num_dashes -= 1

    substrings = []
    for dash_id in range(num_dashes):
        substrings.append(f'{string[dash_id * 8:(dash_id + 1) * 8]}-')
    substrings.append(string[num_dashes * 8:len(string)])

    return ''.join(substrings)


def get_orthanc_series_id(patient_id: str, study_instance_uid: str, series_instance_uid: str):
    raw_identifier = f"{patient_id}|{study_instance_uid}|{series_instance_uid}"
    orthanc_id = hashlib.sha1(raw_identifier.encode('utf-8')).hexdigest()
    orthanc_id = pad_string_with_dashes(orthanc_id, distance=8)
    return orthanc_id


def get_orthanc_study_id(patient_id: str, study_instance_uid: str):
    raw_identifier = f"{patient_id}|{study_instance_uid}"
    orthanc_id = hashlib.sha1(raw_identifier.encode('utf-8')).hexdigest()
    orthanc_id = pad_string_with_dashes(orthanc_id, distance=8)
    return orthanc_id

    
def convert_dicom(target_dir, filename, to_convert, convert_to='nifti_gz', method='dcm2niix', force=False):
    os.makedirs(target_dir, exist_ok=True)

    if convert_to == 'nrrd':
        print('Conversion from DICOM to NRRD...')
        if method=='dcm2niix':
            cmd = (f"{dcm2niix_executable} -o {target_dir} -f {filename} -w 1 -e y {to_convert}")
        else:
            raise Exception('Not recognized {} method to convert from DICOM to NRRD.'.format(method))
    elif convert_to == 'nifti_gz':
        print('\nConversion from DICOM to NIFTI_GZ...')
        ext = '.nii.gz'
        if method == 'dcm2niix':
            if force:
                cmd = (f"{dcm2niix_executable} -o {target_dir} -f {filename} -w 1 -z y -p n -m y {to_convert}")
            else:
                cmd = (f"{dcm2niix_executable} -o {target_dir} -f {filename} -w 1 -z y -p n {to_convert}")
        else:
            raise Exception('Not recognized {} method to convert from DICOM to NIFTI_GZ.'.format(method))
    else:
        raise NotImplementedError('The conversion from DICOM to {} has not been implemented yet.'
                                  .format(convert_to))
    try:
        print(cmd)
        sp.check_output(cmd, shell=True)
        print('Image successfully converted!\n')
    except:
        print('Conversion failed. Scan will be ignored.\n')
        

def get_nrrd_from_instances_list(orthanc_client, referenced_instances, target_dir, orthanc_series_id, modality_suff):
    try: 
        instances = [orthanc_client.get_instances_id_file(instance.id_) for instance in referenced_instances]
        # print(f"Retrieved {len(instances)} instances...")

    except HTTPError as err:
        print(f"could not retrieve the referenced dicoms {orthanc_series_id}, {err}")
    
    with tempfile.TemporaryDirectory() as tmpdirname:
        # print('created temporary directory', tmpdirname)
        for instance_bytes, instance in zip(instances, referenced_instances):
            with open(os.path.join(tmpdirname, instance.id_), 'wb') as f: 
                f.write(instance_bytes)
    
        convert_dicom(target_dir=target_dir, filename=sane_filename(f"{orthanc_series_id}-{modality_suff}"), to_convert=tmpdirname, convert_to="nrrd")


def get_meta_with_correct_alta_ids():
    # Load current meta from PACs and match mit ALTA IDs
    dicom_meta_data = pd.read_csv("/home/oleksii/projects/ohif-orthanc-postgres-docker/meta_pacs_20230719.csv", sep=";")
    # prepare dicom_meta data
    dicom_meta_data['StudyDate'] = pd.to_datetime(dicom_meta_data['StudyDate'], format="%Y%m%d")
    dicom_meta_data_alta = pd.read_csv("/data/oleksii/datasets/ALTA-Lesions-Dataset/classification/clinical_param/meta_pacs_alta_id.csv", sep=";")
    dicom_meta_data_alta = dicom_meta_data_alta[['StudyInstanceUID', 'ALTA ID']]
    dicom_meta_data_alta_merged = pd.merge(
        dicom_meta_data,
        dicom_meta_data_alta,
        how="left",
        on='StudyInstanceUID',
    )
    cond = dicom_meta_data_alta_merged["ALTA ID"].isna() & dicom_meta_data_alta_merged["InstitutionName"].str.lower().str.contains('|'.join(["lumiani", "alta"]))
    dicom_meta_data_alta_merged.loc[cond, "ALTA ID"] = dicom_meta_data_alta_merged[cond]['PatientID']
    dicom_meta_data_alta_merged['ALTA ID str'] = dicom_meta_data_alta_merged['ALTA ID'].str.rjust(12, "0")
    dicom_meta_data_alta_merged['PatientID str'] = dicom_meta_data_alta_merged['PatientID'].str.rjust(12, "0")
    return dicom_meta_data_alta_merged            

                    
def retrieve_studies_from_othanc(df, target_dir_root, use_ref_t2w=False, include_segmentation=False):
   
    # Iterate over available segmentations   
    for i, (_, row) in enumerate(df.iterrows()):    
        print(f"processing {i}/{len(df)}...")
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
            for dwi_oid in row['dwi_tra_id'].split(','):
                dwi_series = pyorthanc.Series(dwi_oid, orthanc_client)
                dwi_instances_grouped = group_dwi_by_bval(dwi_series.instances)
                for dwi_key, dwi_instances_bval in dwi_instances_grouped.items():
                    get_nrrd_from_instances_list(orthanc_client,  dwi_instances_bval, target_dir, dwi_oid, f"dwi_tra_bval_{dwi_key}")


# ------ 
def retrieve_exitsting_cases():
    target_dir_root = "/data/oleksii/Prostate-Classification-Datasets-NRRDS/ALTA-Classification-Dataset/"    
    sequence_selected_path = "/home/oleksii/projects/ohif-orthanc-postgres-docker/datasets/2_classification/clinical_metainfo/sequence_map_classicifation_20240410.csv"
    sequence_selected = pd.read_csv(sequence_selected_path, sep=';')
    retrieve_studies_from_othanc(sequence_selected, target_dir_root)


if __name__=='__main__':
    retrieve_exitsting_cases()
