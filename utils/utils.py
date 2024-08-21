import os
import hashlib
import subprocess as sp
import re
import memory_tempfile

from pyorthanc import Orthanc, Study
from collections import defaultdict
from httpx import HTTPError
import gzip
import pydicom

dcm2niix_executable = "./dcm2niix/build/bin/dcm2niix"  
current_sequence_map_path = "/home/oleksii/projects/ohif-orthanc-postgres-docker/sequence_mapping/sequence_mapping_13681_studies_20240807.csv"


def open_zipped_dicom(file_path):
    # Check if the file exists
    if not os.path.exists(file_path):
        raise FileNotFoundError(f"The file {file_path} does not exist.")

    # Check if the file has the correct extension
    if not file_path.endswith('.dcm.gz'):
        raise ValueError("The file must have a .dcm.gz extension.")

    # Open the gzipped file and decompress it
    with gzip.open(file_path, 'rb') as gzipped_file:
        # Read the decompressed data
        decompressed_data = gzipped_file.read()

    # Use pydicom to read the DICOM data from the decompressed content
    dicom_data = pydicom.dcmread(pydicom.filebase.DicomBytesIO(decompressed_data))

    return dicom_data


def get_orthanc_client():
    # Initialize orthanc client
    orthanc = Orthanc('http://localhost:8042')
    orthanc.setup_credentials('dev-user-alta', 'SyTP&8JbKFx@a6R65^sE`Z$') 
    return orthanc


def sane_filename(filename, keepcharacters=('.','_')):
    return "".join(c for c in filename if c.isalnum() or c in keepcharacters).rstrip()
    
    
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


def get_oid_from_uid(uid, orthanc_client):
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

    
def convert_dicom(target_dir, filename, to_convert, convert_to='nifti_gz', method='dcm2niix', force=False):
    os.makedirs(target_dir, exist_ok=True)

    if convert_to == 'nrrd':
        print('Conversion from DICOM to NRRD...')
        if method=='dcm2niix':
            cmd = (f"{dcm2niix_executable} -o {target_dir} -f {filename} -w 1 -x i -y n -x i -e y {to_convert}" )
        else:
            raise Exception('Not recognized {} method to convert from DICOM to NRRD.'.format(method))
    elif convert_to == 'nifti_gz':
        print('\nConversion from DICOM to NIFTI_GZ...')
        ext = '.nii.gz'
        if method == 'dcm2niix':
            if force:
                cmd = (f"{dcm2niix_executable} -o {target_dir} -f {filename} -w 1 -x i -y n -z y -p n -m y {to_convert}")
            else:
                cmd = (f"{dcm2niix_executable} -o {target_dir} -f {filename} -w 1 -x i -y n -z y -p n {to_convert}")
        else:
            raise Exception('Not recognized {} method to convert from DICOM to NIFTI_GZ.'.format(method))
    else:
        raise NotImplementedError('The conversion from DICOM to {} has not been implemented yet.'
                                  .format(convert_to))
    try:
        print(cmd)
        sp.check_output(cmd, shell=True)
        print('Image successfully converted!\n')
        return True
    except:
        print('Conversion failed. Scan will be ignored.\n')
        
        
# Function that retrieves the referenced series of the segmentation file
def get_referenced_series(orthanc_client, dicom_dataset, return_series_identifier_only=True):
    patientID = dicom_dataset[(0x0010, 0x0020)].value
    seriesInstanceUID = dicom_dataset[(0x0020, 0x000d)].value
    refSeriesInstanceUID = dicom_dataset[(0x0008,0x1115)][0][(0x0020, 0x000e)].value
    series_identifier = get_orthanc_series_id(patientID, seriesInstanceUID, refSeriesInstanceUID)
    
    if return_series_identifier_only:
        return series_identifier, None, None
    
    try: 
        series_info = orthanc_client.get_series_id(series_identifier)
        referenced_instances = series_info['Instances']
        files = [orthanc_client.get_instances_id_file(instance_id) for instance_id in referenced_instances]
        
    except HTTPError as err:
#         if err == 404:
        print(f"could not retrieve the referenced dicoms {series_identifier}")
        return None, None, None                   
        
    print(f"Retrieved {len(files)} istances..")
    return series_identifier, referenced_instances, files


def get_nrrd_from_instances_list(orthanc_client, referenced_instances, target_dir, orthanc_series_id, modality_suff):
    try: 
        instances = [orthanc_client.get_instances_id_file(instance.id_) for instance in referenced_instances]
        # print(f"Retrieved {len(instances)} instances...")
    
    except HTTPError as err:
        print(f"could not retrieve the referenced dicoms {orthanc_series_id}, {err}")
    
    with memory_tempfile.MemoryTempfile().TemporaryDirectory() as tmpdirname:
        # print('created temporary directory', tmpdirname)
        for instance_bytes, instance in zip(instances, referenced_instances):
            with open(os.path.join(tmpdirname, instance.id_), 'wb') as f: 
                f.write(instance_bytes)
    
        convert_dicom(target_dir=target_dir, filename=sane_filename(f"{orthanc_series_id}-{modality_suff}"), to_convert=tmpdirname, convert_to="nrrd")
