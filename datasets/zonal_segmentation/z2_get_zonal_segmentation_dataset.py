import os
import httpx
import pandas as pd

from tqdm import tqdm
from datetime import datetime 
from pyorthanc import Series, Study
from utils.utils import get_orthanc_client

# Zonen info
def main(dataset_location, ):
    orthanc_client = get_orthanc_client()
    seg_oid = os.listdir(dataset_location)
    some_missing = []
    records = []

    for series_oid in tqdm(seg_oid):
        d = {}

        try:
            # series = Series(soid, orthanc_client)
            study = Study(series_oid, orthanc_client)
            main_info = study.get_main_information()
            study_date = main_info['MainDicomTags']['StudyDate']
            study_UID = main_info['MainDicomTags']['StudyInstanceUID']
            patient_id = main_info['PatientMainDicomTags']['PatientID']
            
            d['study_date'] = study_date
            d['patient_id'] = patient_id
            d['StudyInstanceUID'] = study_UID
            d['study_orthanc_id'] = study.id_
            
            records.append(d)

        except httpx.HTTPError as e:
            some_missing.append(series_oid)
        
    metadata_zone = pd.DataFrame(records)
    today = datetime.today().strftime('%Y%m%d')
    metadata_zone.to_csv(f'datasets/zonal_segmentation/zone_dataset_{len(metadata_zone)}_{today}.csv', sep=';', index=False)


if __name__=="__main__":
    # dataset = "/data/oleksii/Prostate-ZONE-Datasets-NRRDS/ALTA-Zone-Dataset"
    dataset = "/data/oleksii/Prostate-ZONE-Datasets-NRRDS/ALTA-Zone-Dataset-multimodal-img"
    main(dataset)
