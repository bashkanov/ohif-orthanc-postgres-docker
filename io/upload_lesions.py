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
import numpy as np


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


def upload_dicom_segmentaton(file_path: str, studyInstanceUID: str):
    dicom_url = f"https://alta-ai.com/server/external/uploadSegmentation?studyInstanceUID={studyInstanceUID}&compressed=false&segmentationType=lesion&algorithmType=automatic"
    try:

        r_post = requests.post(
            url=dicom_url,
            data=read_file(file_path),
            headers={"Authorization": auth()},
        )
        if r_post.status_code in [401, 403]:
            print("Authorization Error. Please check the given credentials")
            return

    except (ConnectionResetError, ProtocolError, ConnectionError) as e:
        print(f"Connection Reset: {e}")
        return
    except (MaxRetryError) as e:
        print(f"MaxRetryError: {e}")
        return
    return

# def upload_heatmap(file_path: str, studyInstanceUID: str):
#     dicom_url = f"https://alta-ai.com/server/external/uploadSegmentation?studyInstanceUID={studyInstanceUID}&compressed=false&segmentationType=lesion&algorithmType=automatic"
#     try:

#         r_post = requests.post(
#             url=dicom_url,
#             data=read_file(file_path),
#             headers={"Authorization": auth()},
#         )
#         if r_post.status_code == 401:
#             print("Authorization Error. Please check the given credentials")
#             return

#     except (ConnectionResetError, ProtocolError, ConnectionError) as e:
#         print(f"Connection Reset: {e}")
#         return
#     except (MaxRetryError) as e:
#         print(f"MaxRetryError: {e}")
#         return
#     return


def upload_dicom_file(data: bytes):
    dicom_url = "https://alta-ai.com/server/external/uploadDicom?compressed=false"
    try:
        r_post = requests.post(
            url=dicom_url,
            data=data,
            headers={"Authorization": auth(), "content-type": "form-data"},
        )
        if r_post.status_code in [401, 403]:
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


def get_segmentations_to_upload():
    segmentations = glob("/data/oleksii/Prostate-Classification-Datasets-NRRDS/ALTA-Classification-Dataset-orient-Segmentations/*/*.seg.nrrd")
    study_oiud = [(seg_path.split('/')[-2], seg_path.split('/')[-1], seg_path) for seg_path in segmentations]
    study_oiud = [{"study_orthanc_id": study, "series_orthanc_id": series.replace('-SegmentationAI.seg.nrrd', ''), "seg_path": seg_path} 
                  for study, series, seg_path in study_oiud]
    return study_oiud   


def get_data_for_first_batch():
    # get first batch with non-segmented lesion cases 
    lesion_dataset = pd.read_csv("/home/oleksii/projects/ohif-orthanc-postgres-docker/datasets/lesion/annotate_batch_01_829_seq_map.csv",  sep=";")
    studies_to_upload = lesion_dataset['study_orthanc_id'].to_list()
    return studies_to_upload
    

if __name__ == "__main__":
    
    max_retries = 4
    retry_sleep = 2
    orthanc_client = get_orthanc_client()

    
    segmentations_with_series = get_data_for_first_batch()
    sequence_map = pd.read_csv("/home/oleksii/projects/ohif-orthanc-postgres-docker/sequence_mapping/sequence_mapping_13024_studies_20240115.csv", sep=";")
    
    # study_oid, series_oid, seg_path = "0a0da388-22d102ff-4fc4ae54-24e395d6-81fc2151", "65c996e0-e73a4923-4829ad80-0d923261-d7c7694c", "/data/oleksii/Prostate-Classification-Datasets-NRRDS/ALTA-Classification-Dataset-Segmentations-alt/0a0da388-22d102ff-4fc4ae54-24e395d6-81fc2151/65c996e0-e73a4923-4829ad80-0d923261-d7c7694c-SegmentationAI.seg.nrrd"
    # segmentations_with_series = get_segmentations_to_upload()
    # segmentations_with_series_df = pd.DataFrame(segmentations_with_series)
    # segmentations_with_series_df = segmentations_with_series_df[segmentations_with_series_df['study_orthanc_id'].isin(studies_first_batch)]
    
    
    study_oid = "016633aa-61193014-3381caf6-27c291af-71d991c3"
    
    seg_path = "/data/oleksii/Prostate-Lesion-Datasets-NRRDS/ALTA-Lesion-Dataset-batch-anno-Segmentation/016633aa-61193014-3381caf6-27c291af-71d991c3/182542710865c1cee6e90c50079e4cf28d2e730aSegmentationAI_lesion.seg.nrrd"
    # upload segmentations
    # for row in tqdm(segmentations_with_series_df.to_dict('records')[:]):
    # study_info = orthanc_client.get_studies_id(row['study_orthanc_id'])
    study_info = orthanc_client.get_studies_id(study_oid)
    upload_dicom_segmentaton(seg_path, studyInstanceUID=study_info['MainDicomTags']['StudyInstanceUID'])
    # print(study_info['MainDicomTags']['StudyInstanceUID'])

    
    
    # sequence_map = sequence_map[sequence_map['study_orthanc_id'].isin(segmentations_with_series)]
    # # sequence_map = sequence_map[sequence_map['study_orthanc_id'].isin([study_oid])]
    
    # for row in tqdm(sequence_map.to_dict('records')[:]):
    #     for seq in ['t2w_tra_id', 't2w_sag_id', 'dwi_tra_id', 'adc_tra_id']:
    #         series_oid = row[seq]        
    #         if not isinstance(series_oid, float):
    #             instances = orthanc_client.get_series_id(series_oid)['Instances']
    #             instances_bar = tqdm(instances)
    #             for instance_id in instances_bar:
    #                 # print(instance_id, flush=True)
    #                 dicom = Instance(instance_id, orthanc_client).get_pydicom()
    #                 ds = anonymize_single_dicom(dicom)

    #                 with DicomBytesIO() as fp:
    #                     fp.is_implicit_VR = ds.is_implicit_VR
    #                     fp.is_little_endian = ds.is_little_endian
    #                     write_dataset(fp, ds)
    #                     dicom_bites = fp.parent.getvalue()
    #                     retries = 0
    #                     while retries < max_retries:
    #                         try:                    
    #                             upload_dicom_file(dicom_bites)
    #                             retries = max_retries
    #                             # fp.seek(0) 
    #                         except httpx.TimeoutException:
    #                             print(f"Request timed out. Retrying ({retries + 1}/{max_retries})...")
    #                             retries += 1
    #                             time.sleep(retry_sleep)
    #         else:
    #             print("Skipping...")