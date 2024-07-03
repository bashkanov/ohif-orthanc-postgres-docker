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

from pyorthanc import Orthanc, Study

from httpx import HTTPError
from datetime import datetime
from pyorthanc import Orthanc
from collections import defaultdict
from pyorthanc import Orthanc, Study, Series

from utils.utils import sane_filename

dcm2niix_executable = "./dcm2niix/build/bin/dcm2niix"  
current_sequence_map = pd.read_csv("meta_data_lesion/sequence_mapping_13056_studies_20240124.csv", sep=';')

                        
def get_oid_from_uid(uid):
    study_candidates = orthanc_client.post_tools_lookup(data=uid)
    for i in study_candidates:
        if i['Type'] == 'Study':
            return i['ID']
    return None
                        

def get_orthanc_client():
    # Initialize orthanc client
    orthanc_client = Orthanc('http://localhost:8042')
    orthanc_client.setup_credentials('dev-user-alta', 'SyTP&8JbKFx@a6R65^sE`Z$') 
    return orthanc_client


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
        

def get_nrrd_from_instances_list(orthanc_client, 
                                 referenced_instances, 
                                 target_dir, 
                                 orthanc_series_id, 
                                 modality_suff, 
                                 skip_existing=True):
    try: 
        instances = [orthanc_client.get_instances_id_file(instance.id_) for instance in referenced_instances]
        # print(f"Retrieved {len(instances)} instances...")

    except HTTPError as err:
        print(f"could not retrieve the referenced dicoms {orthanc_series_id}, {err}")
    
    if skip_existing and os.path.exists(os.path.join(target_dir, sane_filename(f"{orthanc_series_id}-{modality_suff}.nrrd"))) :
        print("Skipping, already exists...")
        return
    
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

                    
def retrieve_studies_from_orthanc(df, target_dir_root, use_ref_t2w=False, include_segmentation=False):
   
    # Iterate over available segmentations   
    for i, (_, row) in enumerate(df[386:].iterrows()):    
        print(f"processing {i}/{len(df)}...")
        target_dir = os.path.join(target_dir_root, row['study_orthanc_id'])
        os.makedirs(target_dir, exist_ok=True)
        
        # in case when sequence mapping fails
        if pd.isna(row['t2w_tra_id']):
            t2w_oid = row["t2w_series_oid"]
        else:
            t2w_oid = row['t2w_tra_id']
        
        t2w_series = pyorthanc.Series(t2w_oid, orthanc_client)
        get_nrrd_from_instances_list(orthanc_client, t2w_series.instances, target_dir, t2w_oid, "tw2_tra")
        
        if not pd.isna(row['adc_tra_id']):
            adc_series = pyorthanc.Series(row['adc_tra_id'], orthanc_client)
            get_nrrd_from_instances_list(orthanc_client, adc_series.instances, target_dir, row['adc_tra_id'], "adc_tra")
        
        # # it handles both cases: 1. where all b-value dwi are under same Series and 
        # # 2. where differnt b-value corresponds to different Series.
        # if not pd.isna(row['dwi_tra_id']):
        #     for dwi_oid in row['dwi_tra_id'].split(','):
        #         dwi_series = pyorthanc.Series(dwi_oid, orthanc_client)
        #         dwi_instances_grouped = group_dwi_by_bval(dwi_series.instances)
        #         for dwi_key, dwi_instances_bval in dwi_instances_grouped.items():
        #             get_nrrd_from_instances_list(orthanc_client,  dwi_instances_bval, target_dir, dwi_oid, f"dwi_tra_bval_{dwi_key}")


# ------ 

def retrieve_neg_cases():
    seq_map_neg = pd.read_csv("meta_data_lesion/seq_map_neg.csv", sep=';')
    target_dir_root = "/data/oleksii/Prostate-Lesion-Datasets-NRRDS/ALTA-Lesion-Dataset-negative-final/"    
    retrieve_studies_from_orthanc(df=seq_map_neg, target_dir_root=target_dir_root)


def retrieve_zonal_dataset_multumodal():
    target_dir_root = "/data/oleksii/Prostate-ZONE-Datasets-NRRDS/ALTA-Zone-Dataset-multimodal/"
    zonal_cases = glob.glob("/data/oleksii/Prostate-ZONE-Datasets-NRRDS/ALTA-Zone-Dataset/*/Segmentation-label.seg.nrrd")
    
    # get study ids from t2w series ids
    seg_oid = [i.split("/")[-2] for i in zonal_cases]
    some_missing = []
    records = [] 
    for soid in seg_oid:
        d = {}

        try:
            series = Series(soid, orthanc_client)
            study = series.parent_study
            # study = Study(series.study_identifier, orthanc_client)
            main_info = study.get_main_information()
            study_date = main_info['MainDicomTags']['StudyDate']
            study_UID = main_info['MainDicomTags']['StudyInstanceUID']
            patient_id = main_info['PatientMainDicomTags']['PatientID']
            
            d['study_date'] = study_date
            d['patient_id'] = patient_id
            d['StudyInstanceUID'] = study_UID
            d['study_orthanc_id'] = study.id_
            d['t2w_series_oid'] = soid

            records.append(d)

        except httpx.HTTPError as e:
    #         print(f'A HTTPError was thrown: {e} ')
            some_missing.append(soid)
    
    metadata_zone = pd.DataFrame(records)
    merged = pd.merge(metadata_zone, current_sequence_map, on='study_orthanc_id', how='left')
    # merged[merged['adc_tra_id'].isna()]
    
    retrieve_studies_from_orthanc(df=merged, target_dir_root=target_dir_root)




if __name__=='__main__':
    # test conntection
    orthanc_client = get_orthanc_client()
    patient_ids = orthanc_client.get_patients()
    len(patient_ids)
    retrieve_zonal_dataset_multumodal()
    # retrieve_exitsting_cases()
    # retrieve_missing_cases_from_first_batch()
    # retrieve_neg_cases()
    # retrieve_alta_ai_segmetnation_cases()
    
    # seg_path = glob.glob("/data/oleksii/Prostate-Lesion-Datasets-NRRDS/ALTA-Lesion-Dataset-fist-batch-external-seg/0f3b3042-cfef7f84-dda03ae9-4a8ed643-6bcccb9d/*seg.nrrd")
    # seg = sitk.ReadImage(seg_path[0])
    # print(seg.GetNumberOfComponentsPerPixel())
    # # print()