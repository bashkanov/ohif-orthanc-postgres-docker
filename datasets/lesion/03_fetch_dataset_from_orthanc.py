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


from typing import List
from httpx import HTTPError
from datetime import datetime
from pyorthanc import Orthanc, Study
from collections import defaultdict

from utils.utils import sane_filename, convert_dicom, get_orthanc_client



dcm2niix_executable = "./dcm2niix/build/bin/dcm2niix"  

# current_sequence_map = pd.read_csv("meta_data_lesion/sequence_mapping_13056_studies_20240124.csv", sep=';')
current_sequence_map = pd.read_csv("/home/oleksii/projects/ohif-orthanc-postgres-docker/sequence_mapping/sequence_mapping_13681_studies_20240807.csv",
                                   sep=';')
                        
def get_oid_from_uid(uid):
    study_candidates = orthanc_client.post_tools_lookup(data=uid)
    for i in study_candidates:
        if i['Type'] == 'Study':
            return i['ID']
    return None
                        

# def get_orthanc_client():
#     # Initialize orthanc client
#     orthanc_client = Orthanc('http://localhost:8042')
#     orthanc_client.setup_credentials('dev-user-alta', 'SyTP&8JbKFx@a6R65^sE`Z$') 
#     return orthanc_client


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


def get_alta_lesion_ids():
    dicom_meta_data_alta_merged = get_meta_with_correct_alta_ids()
    
    path = "/data/oleksii/datasets/ALTA-Lesions-Dataset/segmentation/segmentations"
    seg_cases = glob.glob(os.path.join(path, "*/*/*/Segmentation-label-tra-final.seg.nrrd"))
    # retrieve corresponding orthanc studies
    d = {}
    for _, case in enumerate(seg_cases):
        # populate None by default 
        d[case] = None
        
        patient_id, study_date = case.split("/")[-4:-2]
        # find patient in orthanc database     
        patient = dicom_meta_data_alta_merged[dicom_meta_data_alta_merged['ALTA ID str'] == patient_id]
        studies_ids = patient[['StudyInstanceUID', 'StudyDate']].to_dict(orient='records')
        if studies_ids:
            # iterate over the studies of the patients
            for study_row in studies_ids: 
                study_oid = get_oid_from_uid(study_row['StudyInstanceUID'])            
                if study_oid is not None: 
                    study = Study(study_oid, orthanc_client)
                    study_time_orthanc = datetime.strptime(study.get_main_information()['MainDicomTags']['StudyDate'], '%Y%m%d')
                    study_time_seg = datetime.strptime(study_date, '%Y%m%d')
                    diff = study_time_orthanc - study_time_seg
                    if diff.days == 0:
                        d[case] = study_oid

    # Excluding the missing images dataset and sending it to Lucas
    alta_lesion_df = pd.DataFrame.from_dict(d, orient='index').reset_index()
    alta_lesion_df.columns = ['seg_path', 'study_orthanc_id']   
    
    return alta_lesion_df


def dicom_seg_to_nrrd(df, target_dir_root):
    # applicacle to alta-ai generated segmentations
    target_dir_root_split = target_dir_root.split('/')
    if not target_dir_root_split[-1]:
        target_dir_root_split = target_dir_root_split[:-1] # trunkate '/' if available
    target_dir_root_seg = '/'.join([*target_dir_root_split[:-1], f'{target_dir_root_split[-1]}-seg'])
    
    for i, (_, row) in enumerate(df.iterrows()):    

        target_dir_seg = os.path.join(target_dir_root_seg, row['study_orthanc_id'])
        os.makedirs(target_dir_seg, exist_ok=True)
        print(i, target_dir_seg)
        dataset = pydicom.dcmread(row['dicom_seg_path'])
        # shutil.copyfile(row[dicom_seg_path], os.path.join(target_dir, os.path.basename(seg_path)))     
        reader = pydicom_seg.MultiClassReader()
        result = reader.read(dataset)
        # image_data = result.data  # directly available
        image = result.image  # lazy construction
        sitk.WriteImage(image, os.path.join(target_dir_seg, f'Segmentation-label-altaai.seg.nrrd'), True)

        # meta data about lesion from dicom tags is unreliable, therefore ignore this block for now
        # case_segment_info = {}
        # for k in result.segment_infos.keys():
        #     case_segment_info[k] = json.loads(result.segment_infos[k][(0x0062, 0x0006)].value)
        #     if 'Class' not in y:
        #         raise ValueError("No Class avaialbe for the segmentation")
        # with open(os.path.join(target_dir, f'{orthanc_series_seg_id}-segmentation-meta.json'), 'w', encoding='utf-8') as f:
        #     json.dump(case_segment_info, f, ensure_ascii=False, indent=4)

                    
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

def retrieve_neg_cases():
    seq_map_neg = pd.read_csv("meta_data_lesion/seq_map_neg.csv", sep=';')
    target_dir_root = "/data/oleksii/Prostate-Lesion-Datasets-NRRDS/ALTA-Lesion-Dataset-negative-final/"    
    retrieve_studies_from_othanc(df=seq_map_neg, target_dir_root=target_dir_root)


def retrieve_exitsting_cases():
    target_dir_root = "/data/oleksii/Prostate-Lesion-Datasets-NRRDS/ALTA-Lesion-Dataset-fist-batch-final/"    

    # converting old dataset into the new structure 
    alta_lesion_batch = get_alta_lesion_ids()
    alta_lesion_batch = alta_lesion_batch[~alta_lesion_batch['study_orthanc_id'].isna()]
    # alta_lesion_batch = pd.read_csv("alta_lesion_df_final_small.csv", sep=';')
    
    # exclude cased from 
    cases_avail = pd.read_csv('meta_data_lesion/missing_images_to_existing_lesions_lucas_final_oid.csv', sep=';')
    alta_lesion_batch_final = alta_lesion_batch[~alta_lesion_batch['seg_path'].isin(cases_avail['seg_path'])]
    
    alta_lesion_batch_merged = pd.merge(alta_lesion_batch_final, current_sequence_map, on='study_orthanc_id', how='left')
    alta_lesion_batch_merged = alta_lesion_batch_merged[~(alta_lesion_batch_merged['t2w_tra_id'].isna())]
    
    # copy segmentations
    target_dir_root_split = target_dir_root.split('/')
    if not target_dir_root_split[-1]:
        target_dir_root_split = target_dir_root_split[:-1] # truncate '/' if available
    target_dir_root_seg = '/'.join([*target_dir_root_split[:-1], f'{target_dir_root_split[-1]}-seg'])
    for i, (_, row) in enumerate(alta_lesion_batch_merged.iterrows()):    
        seg_dir = os.path.join(target_dir_root_seg, row['study_orthanc_id'])
        print(seg_dir)
        os.makedirs(seg_dir, exist_ok=True)
        shutil.copyfile(row['seg_path'], os.path.join(seg_dir, os.path.basename(row['seg_path'])))

    retrieve_studies_from_othanc(alta_lesion_batch_merged, target_dir_root)


def retrieve_missing_cases_from_first_batch():
    cases_avail = pd.read_csv('meta_data_lesion/missing_images_to_existing_lesions_lucas_final_oid.csv', sep=';')
    cases_merged = pd.merge(cases_avail, current_sequence_map, on='study_orthanc_id', how='left')
    
    # get_cases where something is missing again 
    target_dir_root = "/data/oleksii/Prostate-Lesion-Datasets-NRRDS/ALTA-Lesion-Dataset-fist-batch-external"    
    cases_merged_all = cases_merged[~(cases_merged['t2w_tra_id'].isna())]
    # retrieve_studies_from_othanc(cases_merged_all, target_dir_root)

    target_dir_root_split = target_dir_root.split('/')
    if not target_dir_root_split[-1]:
        target_dir_root_split = target_dir_root_split[:-1] # truncate '/' if available
    target_dir_root_seg = '/'.join([*target_dir_root_split[:-1], f'{target_dir_root_split[-1]}-seg'])
    # copy segmentation
    for i, (_, row) in enumerate(cases_merged_all.iterrows()):    
        seg_dir = os.path.join(target_dir_root_seg, row['study_orthanc_id'])
        print(seg_dir)
        os.makedirs(seg_dir, exist_ok=True)
        shutil.copyfile(row['seg_path'], os.path.join(seg_dir, os.path.basename(row['seg_path'])))  


def retrieve_alta_ai_segmetnation_cases():
    # segments_info = pd.read_csv("/data/oleksii/alta-ai-orthanc-backup/2023_08_15_full/segments.csv")
    target_dir_root = "/data/oleksii/Prostate-Lesion-Datasets-NRRDS/ALTA-Lesion-Dataset-alta_ai-export20240814-seg-IDS-fresh/"
    # lesions = glob.glob("/data/oleksii/alta-ai.com/alta-ai-orthanc-backup/2023_08_15_full/prostate_lesion/ProcessingState.PROCESSED/*/seg.dcm")
    # lesions = glob.glob("/data/oleksii/alta-ai.com/alta-ai-orthanc-backup/export20240809/prostate_lesion/ProcessingState.PERFECT/*/seg.dcm")
    lesions = glob.glob("/data/oleksii/alta-ai.com/alta-ai-orthanc-backup/export20240814/prostate_lesion/ProcessingState.PERFECT/*/seg.dcm")
    lesions_exported = glob.glob("/data/oleksii/alta-ai.com/alta-ai-orthanc-backup/export20240809/prostate_lesion/ProcessingState.PERFECT/*/seg.dcm")
    

    def get_diff_paths(list1: List[str], list2: List[str]) -> List[str]:
        # Extract directory names from the full paths
        dirs1 = set(os.path.basename(os.path.dirname(path)) for path in list1)
        dirs2 = set(os.path.basename(os.path.dirname(path)) for path in list2)

        # Find directories that are in list1 but not in list2
        diff_dirs = dirs1 - dirs2

        # Filter the original list1 to only include paths from the diff directories
        diff_paths = [path for path in list1 if os.path.basename(os.path.dirname(path)) in diff_dirs]

        return diff_paths
    
    lesions = get_diff_paths(lesions, lesions_exported)
    
    # df_optional_study_components = pd.read_csv("/data/oleksii/alta-ai.com/alta-ai-orthanc-backup/export20240809/mongo_csv_dump/aggregatedData/optional_study_components.csv")
    df_segmentation = pd.read_csv("/data/oleksii/alta-ai.com/alta-ai-orthanc-backup/export20240814/mongo_csv_dump/aggregatedData/segmentation.csv")
    df_study = pd.read_csv("/data/oleksii/alta-ai.com/alta-ai-orthanc-backup/export20240814/mongo_csv_dump/aggregatedData/study.csv")
    healthy = df_study[df_study['diagnoses'] == "{'prostateCancer': {'diagnosis': 'healthy'}}"]
    
    # get the StudyInstanceUID from dicom segmemtatinos
    meta_info = []
    for seg in lesions:
        orthancID = seg.split("/")[-2]
        dataset = pydicom.dcmread(seg)
        
        patientID = dataset[(0x0010, 0x0020)].value
        studyInstanceUID = dataset[(0x0020, 0x000d)].value
        # seriesInstanceUID = dataset[(0x0020, 0x000e)].value

        # get referenced T2W image
        refSeriesInstanceUID = dataset[(0x0008,0x1115)][0][(0x0020, 0x000e)].value 
        orthanc_series_t2w_ref = get_orthanc_series_id(patientID, studyInstanceUID, refSeriesInstanceUID)       
        
        meta_info.append({'dicom_oid': orthancID, 
                          'StudyInstanceUID': dataset[(0x0020, 0x000d)].value, 
                          'dicom_seg_path': seg, 
                          't2w_ref_oid': orthanc_series_t2w_ref, 
                          'patient_id': patientID,
                          })
        
    alta_ai_lesions = pd.DataFrame(meta_info)
    # alta_ai_lesions = alta_ai_lesions[~alta_ai_lesions["StudyInstanceUID"].isin(healthy['studyInstanceUID'])]
    # alta_ai_lesions = alta_ai_lesions[alta_ai_lesions["StudyInstanceUID"].isin(healthy['studyInstanceUID'])]
    
    for i, row in alta_ai_lesions.iterrows():
        oid = get_oid_from_uid(row['StudyInstanceUID'])
        # print(oid, row['StudyInstanceUID'])
        alta_ai_lesions.loc[i, 'study_orthanc_id'] = oid
    
    alta_ai_lesions_seq = pd.merge(alta_ai_lesions, current_sequence_map, on='study_orthanc_id', how='left')
    # skip check missing t2w modalities
    retrieve_studies_from_othanc(df=alta_ai_lesions_seq, target_dir_root=target_dir_root, use_ref_t2w=True, include_segmentation=True)
    dicom_seg_to_nrrd(df=alta_ai_lesions_seq, target_dir_root=target_dir_root)
    alta_ai_lesions_seq.to_csv("/data/oleksii/Prostate-Lesion-Datasets-NRRDS/ALTA-Lesion-Dataset-alta_ai-export20240814-seg-IDS-fresh.csv", sep=";", index=False)
    

if __name__=='__main__':
    # test conntection
    orthanc_client = get_orthanc_client()
    # patient_ids = orthanc_client.get_patients()
    # len(patient_ids)
    # retrieve_exitsting_cases()
    # retrieve_missing_cases_from_first_batch()
    # retrieve_neg_cases()
    
    # use "gunzip */*/*.gz" command 
    retrieve_alta_ai_segmetnation_cases()
    
    # seg_path = glob.glob("/data/oleksii/Prostate-Lesion-Datasets-NRRDS/ALTA-Lesion-Dataset-fist-batch-external-seg/0f3b3042-cfef7f84-dda03ae9-4a8ed643-6bcccb9d/*seg.nrrd")
    # seg = sitk.ReadImage(seg_path[0])
    # print(seg.GetNumberOfComponentsPerPixel())
    # print()