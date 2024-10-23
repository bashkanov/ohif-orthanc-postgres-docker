import os
import glob
import pandas as pd
from datetime import datetime
from pyorthanc import Orthanc, Study
import tqdm

from sequence_map_algorithm import process_dicom_meta_info

def check_presence_of_key(series_dict, instance_tags, key):
    series_dict[key] = instance_tags[key] if key in i_tags else None
                        
if __name__=="__main__":
    
    # Initialize orthanc client
    orthanc_client = Orthanc('http://localhost:8042', **{'timeout': 10.0})
    orthanc_client.setup_credentials('dev-user-alta', 'SyTP&8JbKFx@a6R65^sE`Z$') 

    # test conntection
    patient_ids = orthanc_client.get_patients()
    print(len(patient_ids))
    all_studies = orthanc_client.get_studies()
    print(len(all_studies))
    today = datetime.today().strftime('%Y%m%d')
    print(today)
    
    # make a sequence mapping on that studies  
    studied_to_map = all_studies

    d = []
    for study_id in tqdm.tqdm(studied_to_map):
        study = Study(study_id, orthanc_client)
        
        series_meta = []
        series = study.series[len(study.series)//2]
        series_d = {}
        series_d['series_orthanc_id'] = series.id_
        
        # sample some instance 
        instance = series.instances[len(series.instances)//2]
        i_tags = instance.simplified_tags
        
        check_presence_of_key(series_d, i_tags, "PatientID")
        check_presence_of_key(series_d, i_tags, "Manufacturer")
        check_presence_of_key(series_d, i_tags, "ManufacturerModelName")
        check_presence_of_key(series_d, i_tags, "SoftwareVersions")
        check_presence_of_key(series_d, i_tags, "DeviceSerialNumber")

        check_presence_of_key(series_d, i_tags, "InstitutionName")
        check_presence_of_key(series_d, i_tags, "InstitutionAddress")
        check_presence_of_key(series_d, i_tags, "StationName")
        check_presence_of_key(series_d, i_tags, "InstitutionalDepartmentName")
        check_presence_of_key(series_d, i_tags, "DeviceTimeOfLastCalibration")
        check_presence_of_key(series_d, i_tags, "DateOfLastCalibration")
        # series_meta.append(series_d)
        # series_meta_df = pd.DataFrame.from_dict(series_meta)
        
        # selected_series = process_dicom_meta_info(series_meta_df)
        series_d["study_orthanc_id"] = study.id_
        study_main_info = study.get_main_information()
        series_d["PatientID"] = study_main_info['PatientMainDicomTags']['PatientID']
        series_d["StudyDate"] = study_main_info['MainDicomTags']['StudyDate']
        d.append(series_d)
        
    dataset = pd.DataFrame.from_dict(d)
    dataset.to_csv(f"device_mapping_{len(studied_to_map)}_studies_{today}_ext.csv", sep=";", index=False)
    print(dataset)