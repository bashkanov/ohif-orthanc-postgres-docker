import os
import hashlib
import subprocess as sp
import re
from pyorthanc import Orthanc, Study
from collections import defaultdict

dcm2niix_executable = "./dcm2niix/build/bin/dcm2niix"  


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
    except:
        print('Conversion failed. Scan will be ignored.\n')