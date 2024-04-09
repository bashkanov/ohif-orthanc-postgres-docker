import asyncio
import base64
import glob
import math
import os.path
import urllib
import zlib
import concurrent.futures
import tempfile
from pyorthanc import Orthanc
from argparse import ArgumentParser, ArgumentDefaultsHelpFormatter
from typing import List, Dict
import pydicom
import aiohttp
import numpy as np
import pandas as pd
import requests
import httpx
import time

from tqdm import tqdm
from urllib3.exceptions import ProtocolError, MaxRetryError
from pyorthanc import Orthanc, Instance, Patient, Study

from oauthlib.oauth2 import BackendApplicationClient
from requests_oauthlib import OAuth2Session
from urllib.parse import urlencode
from pydicom.filebase import DicomFileLike
from pydicom import dcmread, dcmwrite
from pydicom.filewriter import write_data_element, write_dataset
from pydicom.filebase import DicomBytesIO
from io import BytesIO


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
        insts.append(orthanc.get_series_id(si)['Instances'])
    return np.concatenate(insts).tolist()


def get_study_ids(path: str) -> List:
    dicom_meta_data = pd.read_csv(path, sep=";")
    # apply filter
    # dicom_meta_data = dicom_meta_data[~dicom_meta_data["StudyDate"].isna()]
    # dicom_meta_data["StudyDate"] = dicom_meta_data["StudyDate"].astype(int).astype(str)
    # dicom_meta_data = dicom_meta_data[dicom_meta_data["StudyDate"].str.startswith("2023")]
    
    study_ids = dicom_meta_data["StudyInstanceUID"].tolist()
    patient_id = dicom_meta_data["PatientID"].tolist()
    print(patient_id)
    print(f"to upload {len(study_ids)} cases:")
    return study_ids


def get_files(path: str) -> List:
    candidates = glob.glob(f'{path}/**', recursive=True)
    candidates = [_file for _file in candidates if os.path.isfile(_file)]
    return candidates


def upload_file(uri: str, file: bytes, headers: Dict) -> None:
    try:
        resp = requests.post(uri, data=file, headers={**headers, 'content-type': 'form-data'})

        if resp.status_code != 200:
            if resp.status_code == 401:
                print("Authorization Error. Please check the given credentials")
                return
            else:
                print("An error occurred")
                return
    except (ConnectionResetError, ProtocolError, ConnectionError) as e:
        print(f"Connection Reset: {e}")
        return
    except (MaxRetryError) as e:
        print(f"MaxRetryError: {e}")
        return
    
def retry_post_instances(client, dicom_bites, max_retries=5, retry_sleep=2):
    retries = 0
    while retries < max_retries:
        try:
            
            client.post_instances(dicom_bites)
            # response.raise_for_status()  # Check for HTTP errors
            
        except httpx.TimeoutException:
            print(f"Request timed out. Retrying ({retries + 1}/{max_retries})...")
            retries += 1
            time.sleep(retry_sleep)
    
    print("Max retries reached. Could not complete the request.")
    # return None
    
max_retries = 4
retry_sleep = 2

if __name__ == '__main__':
    parser = ArgumentParser(formatter_class=ArgumentDefaultsHelpFormatter)
    arg = parser.add_argument
    arg("--data", type=str, default="/data", help="Path to directory, that you want to upload")
    
    parser.set_defaults(async_upload=False)
    args = parser.parse_args()

    # study_ids = get_study_ids("meta_pacs_inst.csv")
    # study_ids = get_study_ids("biopsy_findings_to_segment_20230505.csv")
    study_ids = get_study_ids("upload_batch_20230727.csv")
    
    orthanc = Orthanc('http://localhost:8042')
    orthanc.setup_credentials('dev-user-alta', 'SyTP&8JbKFx@a6R65^sE`Z$')  # If needed
    
    # orthanc writer need to be mapped:
    orthanc_remote = Orthanc('http://localhost:52052')
    orthanc_remote.setup_credentials('radiology', 'm8UwpwqBSvBUszUffq88')  # If needed
    
    # upload files
    # pbar = tqdm(study_ids[:100]) 
    # TODO: pbar = tqdm(study_ids[145:200]) 
    # pbar = tqdm(study_ids[200:1100]) 
    pbar = tqdm(study_ids[430+314:1100]) 
    for study_id in pbar: 
        study = orthanc.post_tools_lookup(data=study_id)
        if len(study) > 0: 
            study_id = study[0]['ID']
            instances = get_instances_from_study(orthanc, study_id)
            instances_bar = tqdm(instances)
            for instance_id in instances_bar:
                # print(instance_id, flush=True)
                dicom = Instance(instance_id, orthanc).get_pydicom()
                ds = anonymize_single_dicom(dicom)


                with DicomBytesIO() as fp:
                    fp.is_implicit_VR = ds.is_implicit_VR
                    fp.is_little_endian = ds.is_little_endian
                    write_dataset(fp, ds)
                    dicom_bites = fp.parent.getvalue()
                    retries = 0
                    while retries < max_retries:
                        try:                    
                            # retry_post_instances(client=orthanc_remote, dicom_bites=dicom_bites)
                            orthanc_remote.post_instances(dicom_bites)
                            retries = max_retries
                            # fp.seek(0) 
                        except httpx.TimeoutException:
                            print(f"Request timed out. Retrying ({retries + 1}/{max_retries})...")
                            retries += 1
                            time.sleep(retry_sleep)
        else: 
            print(f"Nothing found for {study_id}")

