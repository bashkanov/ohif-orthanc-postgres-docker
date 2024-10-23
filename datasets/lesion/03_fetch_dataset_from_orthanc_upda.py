############################################################
##
##  This code provides the scripts for an orginized 
##  dataset generation for DICOM data from orthanc server. 
##
############################################################

import os
import pyorthanc
import tempfile
import pandas as pd

from httpx import HTTPError
from utils.utils import get_orthanc_client,  sane_filename, convert_dicom, group_dwi_by_bval


dcm2niix_executable = "./dcm2niix/build/bin/dcm2niix"  
current_sequence_map = pd.read_csv("/home/oleksii/projects/ohif-orthanc-postgres-docker/sequence_mapping/sequence_mapping_13681_studies_20240807.csv", sep=';')

orthanc_client = get_orthanc_client()                   


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
    target_dir_root = "/data/oleksii/Prostate-Classification-Datasets-NRRDS/ALTA-Classification-Dataset-orient/"    
    sequence_selected_path = "/home/oleksii/projects/ohif-orthanc-postgres-docker/datasets/2_classification/clinical_metainfo/sequence_map_classicifation_20240410.csv"
    sequence_selected = pd.read_csv(sequence_selected_path, sep=';')
    retrieve_studies_from_othanc(sequence_selected, target_dir_root)


if __name__=='__main__':
    retrieve_exitsting_cases()
