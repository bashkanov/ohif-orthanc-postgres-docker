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
    # df = pd.read_csv("meta_data_lesion/missing_images_to_existing_lesions_lucas_final_oid.csv", sep=";")
    # studied_to_map = df['study_orthanc_id'].tolist()
    # studied_to_map = ['c3c5dbb8-33ef5944-2f746ccd-4315c486-1d15ef41']
    # studied_to_map = ['b3117d63-547c6f5f-01bf859c-ddf4a159-535d4d2e']     # phillips case! needs to be investigated more in detail 
    # studied_to_map = ['752f842e-c7f224d4-1611d32a-33225378-b80226f0']     # external case multiple dwi
    # studied_to_map = ['a5fbdd93-94340496-663b98fb-028d8adb-1f94c594']     # external multiple slice thickness
    
    
    # studied_to_map = ['517713ea-c2f36caa-f7cd39a7-e311a844-112cf711']     # somehow missing 
    studied_to_map = ['db4b6807-2ad902ba-03e2cad6-e142e78f-dc6f2d07']     # somehow missing 
    
    d = []
    for study_id in tqdm.tqdm(studied_to_map):
        study = Study(study_id, orthanc_client)
        # print(f"Mapping {i}/{len(all_studies)}:", study_id)
        
        series_meta = []
        for series in study.series:
            series_d = {}
            series_d['FileCount'] = len(series.instances)
            series_d['series_orthanc_id'] = series.id_
            
            # sample some instance 
            instance = series.instances[len(series.instances)//2]
            i_tags = instance.simplified_tags
            
            check_presence_of_key(series_d, i_tags, "SequenceName")
            check_presence_of_key(series_d, i_tags, "ProtocolName")
            check_presence_of_key(series_d, i_tags, "SeriesDescription")
            check_presence_of_key(series_d, i_tags, "ImageType")
            check_presence_of_key(series_d, i_tags, "ImageOrientationPatient")
            check_presence_of_key(series_d, i_tags, "Manufacturer")
            check_presence_of_key(series_d, i_tags, "InstitutionName")
            check_presence_of_key(series_d, i_tags, "DiffusionBValue")
            check_presence_of_key(series_d, i_tags, "DiffusionBFactor")
            check_presence_of_key(series_d, i_tags, "SliceThickness")

            series_meta.append(series_d)
            
        series_meta_df = pd.DataFrame.from_dict(series_meta)
        
        selected_series = process_dicom_meta_info(series_meta_df)
        selected_series["study_orthanc_id"] = study.id_
        study_main_info = study.get_main_information()
        selected_series["PatientID"] = study_main_info['PatientMainDicomTags']['PatientID']
        selected_series["StudyDate"] = study_main_info['MainDicomTags']['StudyDate']
        d.append(selected_series)
        
    dataset = pd.DataFrame.from_dict(d)
    # dataset.to_csv(f"meta_data_lesion/sequence_mapping_{len(studied_to_map)}_studies_{today}.csv", sep=";", index=False)
    print(dataset)