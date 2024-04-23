import pandas as pd

from base64 import b64encode
from glob import glob
import os
from typing import List
import requests
from urllib3.exceptions import ProtocolError, MaxRetryError
import numpy as np
from pydicom.filewriter import write_data_element, write_dataset
import httpx
import time


from pyorthanc import Orthanc, Instance, Patient, Study
from utils.utils import get_orthanc_client,  sane_filename
from tqdm import tqdm
from pydicom.filebase import DicomBytesIO


def anonymize_single_dicom(dicom):
    dicom.remove_private_tags()
    keys_to_anonymise = {
        (0x0010, 0x0010): "Unnamed", # patient name
        (0x07a1, 0x1071): "Unnamed",
        (0x07a3, 0x101c): "Unnamed",
        (0x07a3, 0x101d): "Unnamed", # In some cases name appear ›
        (0x0008, 0x0090): "Unnamed", # physician name
        (0x0008, 0x1050): "Unnamed", # physician name
        (0x0008, 0x1048): "Unnamed", # Physician of record
        (0x0008, 0x1070): "Unnamed", # Operators name
        (0x0008, 0x1040): "Unnamed", # Institutional Department Name
        (0x0008, 0x0081): "Nowhere", # InstitutionAddress
        (0x0008, 0x0080): "Unnamed", # Institution Name
        (0x0010, 0x0030): "19000101", # birthday
        (0x0010, 0x1010): "100 Y", # age
        (0x0010, 0x1020): "2.00", # size
        (0x0010, 0x1030): "80", # weight
    }
    for key, val_to_replace in keys_to_anonymise.items():
        if key in dicom:
            dicom[key].value = val_to_replace
    return dicom


def get_instances_from_study(orthanc_clinet, study_id):
    study_info = orthanc_clinet.get_studies_id(study_id)
    series_identifiers = study_info['Series']
    insts = []
    for si in series_identifiers:
        insts.append(orthanc_clinet.get_series_id(si)['Instances'])
    return np.concatenate(insts).tolist()


def read_file(file_path: str) -> bytes:
    with open(file_path, "rb") as file:
        return file.read()


def auth():
    auth_string = f"form-app:r%4oEdL&R$!K!Bq&EGtmir"
    credentials = b64encode(auth_string.encode()).decode("utf-8")
    return f"Basic {credentials}"


def upload_dicom_segmentation(file_path: str, studyInstanceUID: str):
    dicom_url = f"https://zone.alta-ai.com/server/external/uploadSegmentation?studyInstanceUID={studyInstanceUID}&compressed=false&segmentationType=zone&algorithmType=automatic"
    try:

        r_post = requests.post(
            url=dicom_url,
            data=read_file(file_path),
            headers={"Authorization": auth()},
        )
        if r_post.status_code == 401:
            print("Authorization Error. Please check the given credentials")
            return

    except (ConnectionResetError, ProtocolError, ConnectionError) as e:
        print(f"Connection Reset: {e}")
        return
    except (MaxRetryError) as e:
        print(f"MaxRetryError: {e}")
        return
    return


def upload_dicom_file(data: bytes):
    dicom_url = "https://zone.alta-ai.com/server/external/uploadDicom?compressed=false"
    try:
        r_post = requests.post(
            url=dicom_url,
            data=data,
            headers={"Authorization": auth(), "content-type": "form-data"},
        )
        if r_post.status_code == 401:
            print("Authorization Error. Please check the given credentials")
            return

    except (ConnectionResetError, ProtocolError, ConnectionError) as e:
        print(f"Connection Reset: {e}")
        return
    except (MaxRetryError) as e:
        print(f"MaxRetryError: {e}")
        return
    

def get_files(path: str) -> List:
    candidates = glob(f"{path}/**", recursive=True)
    candidates = [_file for _file in candidates if os.path.isfile(_file)]
    return candidates


def get_studies_to_upload():
    segmentations = glob("/data/oleksii/Prostate-Classification-Datasets-NRRDS/ALTA-Classification-Dataset-Segmentations/*/*.seg.nrrd")
    study_oiud = [(seg_path.split('/')[-2], seg_path.split('/')[-1], seg_path) for seg_path in segmentations]
    study_oiud = [(study, series.replace('-SegmentationAI.seg.nrrd', ''), seg_path) for study, series, seg_path in study_oiud]
    return study_oiud   


def get_data_for_first_batch():
    # get first batch with non-segmented lesion cases 
    classification_dataset = pd.read_csv("datasets/2_classification/prostate_class_dataset_demography_final_psa_vol_20240418.csv", sep=";")
    zonal_dataset = pd.read_csv("/home/oleksii/projects/ohif-orthanc-postgres-docker/datasets/1_zonal_segmentation/zone_dataset_1260_20240129.csv",  sep=";")
    lesion_dataset = pd.read_csv("/home/oleksii/projects/ohif-orthanc-postgres-docker/datasets/0_lesion/meta_data_lesion/lesion_dataset_1941_20240126_OB.csv", sep=";")
    
    never_segmented_zones = classification_dataset[~classification_dataset['study_orthanc_id'].isin(zonal_dataset['study_orthanc_id'])]
    priority_zones = never_segmented_zones[never_segmented_zones['study_orthanc_id'].isin(lesion_dataset['study_orthanc_id'])]
    studies_to_upload = priority_zones['study_orthanc_id'].to_list()
    return studies_to_upload
    

if __name__ == "__main__":
    
    max_retries = 4
    retry_sleep = 2
    orthanc_client = get_orthanc_client()

    # study_oid, series_oid, seg_path = "0a0da388-22d102ff-4fc4ae54-24e395d6-81fc2151", "65c996e0-e73a4923-4829ad80-0d923261-d7c7694c", "/data/oleksii/Prostate-Classification-Datasets-NRRDS/ALTA-Classification-Dataset-Segmentations-alt/0a0da388-22d102ff-4fc4ae54-24e395d6-81fc2151/65c996e0-e73a4923-4829ad80-0d923261-d7c7694c-SegmentationAI.seg.nrrd"
    studies = get_studies_to_upload()
    
    
    # upload dicom
    studies = get_data_for_first_batch()
    sequence_map = pd.read_csv("/home/oleksii/projects/ohif-orthanc-postgres-docker/datasets/2_classification/clinical_metainfo/sequence_map_classicifation_20240410.csv", sep=";")
    
    # for study_oid, series_oid, seg_path in tqdm(studies[:5]):
    print(len(studies))
    sequence_map = sequence_map[sequence_map['study_orthanc_id'].isin(studies)]
    
    for row in tqdm(sequence_map.to_dict('records')[:5]):
        series_oid = row['t2w_tra_id']
        
        if series_oid is not None:
            instances = orthanc_client.get_series_id(series_oid)['Instances']
            instances_bar = tqdm(instances)
            for instance_id in instances_bar:
                # print(instance_id, flush=True)
                dicom = Instance(instance_id, orthanc_client).get_pydicom()
                ds = anonymize_single_dicom(dicom)

                with DicomBytesIO() as fp:
                    fp.is_implicit_VR = ds.is_implicit_VR
                    fp.is_little_endian = ds.is_little_endian
                    write_dataset(fp, ds)
                    dicom_bites = fp.parent.getvalue()
                    retries = 0
                    while retries < max_retries:
                        try:                    

                            upload_dicom_file(dicom_bites)
                            retries = max_retries
                            # fp.seek(0) 
                        except httpx.TimeoutException:
                            print(f"Request timed out. Retrying ({retries + 1}/{max_retries})...")
                            retries += 1
                            time.sleep(retry_sleep)
            
            # study_info = orthanc_client.get_studies_id(study_oid)
            # upload_dicom_segmentation(seg_path, studyInstanceUID=study_info['MainDicomTags']['StudyInstanceUID'])
