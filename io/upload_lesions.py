import httpx
import json
import logging
import numpy as np
import pandas as pd
import os
import requests
import time
import memory_tempfile
import datetime

from base64 import b64encode
from glob import glob
from pydicom.filebase import DicomBytesIO
from pydicom.filewriter import write_data_element, write_dataset
from pyorthanc import Orthanc, Instance, Patient, Study
from requests.exceptions import HTTPError, Timeout, ConnectionError, RequestException
from tqdm import tqdm
from typing import List, Optional, Any
from urllib3.exceptions import ProtocolError, MaxRetryError


from utils.utils import get_orthanc_client, sane_filename

class PrefixFilter(logging.Filter):
    def filter(self, record):
        # Return False to ignore the log message
        return not record.getMessage().startswith("INFO:httpx:HTTP")

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Create a console handler
console_handler = logging.StreamHandler()
console_handler.setLevel(logging.DEBUG) 

    
# Add the prefix filter to the console handler
prefix_filter = PrefixFilter()
console_handler.addFilter(prefix_filter)

# Create a formatter and set it for the console handler
formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
console_handler.setFormatter(formatter)

# Add the handler to the logger
logger.addHandler(console_handler)


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


# def fetch_url(url: str, data: Optional[dict] = None, headers: Optional[dict] = None, retries: int = 3, backoff_factor: float = 0.3) -> Any:    
        
#     for attempt in range(retries):
#         try:
#             response = requests.post(
#                 url=url,
#                 data=data,
#                 headers=headers,
#             )
#             response.raise_for_status()  # Raise an exception for HTTP error responses
#         except (Timeout, ConnectionError, ConnectionResetError) as trans_err:
#             logger.error(f"Transient error occurred: {trans_err}.")
#             if trans_err.response is not None:
#                 logger.error(f"Status code: {trans_err.response.status_code}")
#             wait_time = backoff_factor * (2 ** attempt)  # Exponential backoff
#             logger.info(f"Retrying in {wait_time} seconds...")
#             time.sleep(wait_time)
#         except HTTPError as http_err:
#             logger.error(f"HTTP error occurred: {http_err}")
#             # Handle specific status codes if needed
#             if http_err.response is not None:
#                 if http_err.response.status_code == 404:
#                     logger.error("Resource not found.")
#                     break
#                 if http_err.response.status_code in [401, 403]:
#                     logger.error("Authorization Error. Please check the given credentials.")
#                     break
#                 elif http_err.response.status_code == 500:
#                     logger.error("Server error.")
#                     break
#         except RequestException as req_err:
#             logger.error(f"An error occurred: {req_err}")
#             break
#         else:
#             # logger.info(f"Seems okay. ")
#             # If no exceptions were raised, return the response
#             return "Ok"
#     return None   


def fetch_url(url: str, data: Optional[dict] = None, headers: Optional[dict] = None, retries: int = 3, backoff_factor: float = 0.3) -> Any:
    client = httpx.Client()
    
    try:
        for attempt in range(retries):
            try:
                response = client.post(
                    url=url,
                    data=data,
                    headers=headers,
                )
                response.raise_for_status()  # Raise an exception for HTTP error responses
                return "Ok"  # If no exceptions were raised, return "Ok"
            except (httpx.TimeoutException, httpx.ConnectError, httpx.NetworkError, httpx.RemoteProtocolError) as trans_err:
                logger.error(f"Transient error occurred: {trans_err}.")
                if attempt < retries - 1:  # Don't sleep on the last attempt
                    wait_time = backoff_factor * (2 ** attempt)  # Exponential backoff
                    logger.info(f"Retrying in {wait_time} seconds...")
                    time.sleep(wait_time)
                else:
                    logger.error("Max retries reached. Giving up.")
            except httpx.HTTPStatusError as http_err:
                logger.error(f"HTTP error occurred: {http_err}")
                # Handle specific status codes if needed
                if http_err.response.status_code == 404:
                    logger.error("Resource not found.")
                elif http_err.response.status_code in [401, 403]:
                    logger.error("Authorization Error. Please check the given credentials.")
                elif http_err.response.status_code == 500:
                    logger.error("Server error.")
                break  # Exit the retry loop for HTTP errors
            except httpx.RequestError as req_err:
                logger.error(f"An error occurred: {req_err}")
                break  # Exit the retry loop for general request errors
    finally:
        client.close()
    
    return None  # If we've exhausted all retries or encountered a non-retryable error

def upload_dicom_segmentaton(file_path: str, studyInstanceUID: str, segmentationType: str = "zone") -> None:
    assert segmentationType in ['zone', 'lesion']
    dicom_url = f"https://alta-ai.com/server/external/uploadSegmentation?studyInstanceUID={studyInstanceUID}&compressed=false&segmentationType={segmentationType}&algorithmType=automatic"
    response = fetch_url(dicom_url, read_file(file_path), headers={"Authorization": auth()})
    return response


def upload_heatmap(file_path: str, studyInstanceUID: str):
    dicom_url = f"https://alta-ai.com/server/external/uploadHeatmap?studyInstanceUID={studyInstanceUID}&compressed=false"

    body_struct = {
        "type": "Lesion",
        "details": { 
            "series_description": "Heatmap Lesion", 
            }
        }
    
    body_struct = json.dumps(body_struct).encode('utf-8')
    
    sep = b"^_^\x00^_^"
    heatmap_bytes = read_file(file_path)
    request_bytes = b"".join([body_struct, sep, heatmap_bytes])
    response = fetch_url(dicom_url, request_bytes, headers={"Authorization": auth()})
    return response


def upload_dicom_file(data: bytes):
    dicom_url = "https://alta-ai.com/server/external/uploadDicom?compressed=false"
    response = fetch_url(dicom_url, data, headers={"Authorization": auth()})
    return response


def upload_dicoms(sequence_map, orthanc_client):
    # os.makedirs(target_dir, exist_ok=True)
    l = []
    for row in tqdm(sequence_map.to_dict('records')[214+57:]):
        try:
            study_info = orthanc_client.get_studies_id(row['study_orthanc_id'])
            study_instanceUID = study_info['MainDicomTags']['StudyInstanceUID']
            
            study_orthanc_id = row['study_orthanc_id']
            d = {
                "study_orthanc_id": study_orthanc_id, 
                "StudyInstanceUID": study_instanceUID,
            }
            l.append(d)
            print("study:", study_instanceUID)
            
            with memory_tempfile.MemoryTempfile().TemporaryDirectory() as temp_dir:
                for seq in ['t2w_tra_id', 't2w_sag_id', 'dwi_tra_id', 'adc_tra_id']:
                # for seq in ['t2w_tra_id', 't2w_sag_id', 'adc_tr/a_id']:
                    series_oid = row[seq]
                    # print("Writing: ", series_oid)
                    if not isinstance(series_oid, float):
                        if "," in series_oid:
                            series_oids = series_oid.split(",")
                        else:
                            series_oids = [series_oid]
                        for series_oid in series_oids:
                            try:
                                instances = orthanc_client.get_series_id(series_oid)['Instances']
                                instances_bar = tqdm(instances)
                                for instance_id in instances_bar:
                                    try:
                                        # print(instance_id, flush=True)
                                        dicom = Instance(instance_id, orthanc_client).get_pydicom()
                                        ds = anonymize_single_dicom(dicom)
                                        #  Create some temporary filename
                                        filename = os.path.join(temp_dir, f"{instance_id}.dcm")
                                        ds.save_as(filename)
                                        upload_dicom_file(read_file(filename))
                                    except Exception as e:
                                        print(f"Error processing instance {instance_id}: {str(e)}")
                            except Exception as e:
                                    print(f"Error processing series {series_oid}: {str(e)}")
        except Exception as e:
            print(f"Error processing study {row['study_orthanc_id']}: {str(e)}")


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


def get_segmentations_with_softmax(path):
    l = []
    for study_orthanc_id in os.listdir(path):
        dir_name = os.path.join(path, study_orthanc_id)
        softmax = glob(os.path.join(dir_name, "*AI_softmax_0_lesion.nrrd"))
        lesion = glob(os.path.join(dir_name, "*SegmentationAI_lesion.seg.nrrd"))
        zone = glob(os.path.join(dir_name, "*SegmentationAI_zone.seg.nrrd"))
        
        l.append({
            "study_orthanc_id": study_orthanc_id, 
            "softmax": softmax[0] if softmax else None,
            "lesion": lesion[0] if lesion else None,
            "zone": zone[0] if zone else None,
        })
    
    df = pd.DataFrame(l)
    return df


if __name__ == "__main__":
    
    orthanc_client = get_orthanc_client()
    sequence_map = pd.read_csv("/home/oleksii/projects/ohif-orthanc-postgres-docker/sequence_mapping/sequence_mapping_13681_studies_20240807.csv", sep=";")        
    # predice_cases = "/data/oleksii/Prostate-Lesion-Datasets-NRRDS/ALTA-Lesion-Dataset-batch-anno-Segmentation-AI/"
    # predice_cases = "/data/oleksii/Prostate-Lesion-Datasets-NRRDS/ALTA-Lesion-Dataset-batch-anno-20240819-AI-pred/"
    predice_cases = "/data/oleksii/Prostate-Lesion-Datasets-NRRDS/ALTA-Lesion-Dataset-batch-anno-20240819-1340-AI-pred/"
    segms = get_segmentations_with_softmax(predice_cases)
    
    # upload dicoms
    sequence_map_filtered = sequence_map[sequence_map['study_orthanc_id'].isin(segms['study_orthanc_id'])]
    
    # to preserve order
    segms_tmp = pd.merge(sequence_map_filtered, segms, how="left", on='study_orthanc_id')

    # failed_cases = pd.read_csv("/home/oleksii/projects/ohif-orthanc-postgres-docker/failed_20240821114725_0.csv", sep=";")
    # # failed_cases = failed_cases[failed_cases['type'] == 'heatmap']
    # failed_cases = failed_cases[failed_cases['type'] == 'lesion']
    # segms_tmp = segms_tmp[segms_tmp['study_orthanc_id'].isin(failed_cases['study_orthanc_id'])]
    print()
    
    # upload_dicoms(sequence_map_filtered, orthanc_client)
    # segms_tmp = segms_tmp.head(214+57)
    segms_tmp = segms_tmp.tail(len(segms_tmp) - (214+57))

    failed = []
    for i, data in tqdm(segms_tmp.iterrows()):
        study_info = orthanc_client.get_studies_id(data["study_orthanc_id"])
        logging.info(f"Uploading case | {study_info['MainDicomTags']['StudyInstanceUID']} | {data['study_orthanc_id']} |")
        
        # upload segmentations  
        if data['zone']:
            time.sleep(1)
            response = upload_dicom_segmentaton(data['zone'], studyInstanceUID=study_info['MainDicomTags']['StudyInstanceUID'], segmentationType="zone")
            if response is None:
                failed.append({"StudyInstanceUID": study_info['MainDicomTags']['StudyInstanceUID'], "study_orthanc_id": data['study_orthanc_id'], "type": "zone"})
        else:
            logging.info("Skipping zone...")
        
        if data['lesion']:
            response = upload_dicom_segmentaton(data['lesion'], studyInstanceUID=study_info['MainDicomTags']['StudyInstanceUID'],  segmentationType="lesion")
            if response is None:
                failed.append({"StudyInstanceUID": study_info['MainDicomTags']['StudyInstanceUID'], "study_orthanc_id": data['study_orthanc_id'], "type": "lesion"})
            
            time.sleep(1)
        else:
            logging.info("Skipping lesion...")
        
        if data['softmax']:
            response = upload_heatmap(data['softmax'], studyInstanceUID=study_info['MainDicomTags']['StudyInstanceUID'])
            if response is None:
                failed.append({"StudyInstanceUID": study_info['MainDicomTags']['StudyInstanceUID'], "study_orthanc_id": data['study_orthanc_id'], "type": "heatmap"})
                
            time.sleep(1)
        else: 
            logging.info("Skipping softmax...")
        
    df = pd.DataFrame(failed)
    timestamp = datetime.datetime.now().strftime("%Y%m%d%H%M%S")
    df.to_csv(os.path.join(os.path.dirname(__file__), f"failed_{timestamp}.csv"), sep=';', index=False)