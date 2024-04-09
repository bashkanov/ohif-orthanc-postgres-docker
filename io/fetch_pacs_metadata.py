import pandas as pd
from datetime import datetime
from pyorthanc import Orthanc, Study, Patient
import tqdm


if __name__ == "__main__":
    orthanc_client = Orthanc('http://localhost:8042', **{'timeout': 10.0})
    orthanc_client.setup_credentials('dev-user-alta', 'SyTP&8JbKFx@a6R65^sE`Z$') 

    # To get patients identifier and main information
    patients_identifiers = orthanc_client.get_patients()
    study_identifiers = orthanc_client.get_studies()

    tags = [
        "StudyDate",
        "PatientID",
        "PatientName",
        "PatientAge",
        "PatientBirthDate",
        "PatientSize",
        "PatientWeight",
        "InstitutionName",
        "StudyInstanceUID"
    ]

    requested_tags = ";".join(tags)
    metadata = []

    tags = [
        "StudyDate",
        "PatientID",
        "PatientName",
        "PatientAge",
        "PatientBirthDate",
        "PatientSize",
        "PatientWeight",
        "InstitutionName",
        "StudyInstanceUID"
    ]

    requested_tags = ";".join(tags)
    metadata = []
    for study_identifier in tqdm.tqdm(study_identifiers[:]):
        s = {}
        # if i % 500 == 0: 
        #     print(f"{i}/{len(study_identifiers)} cases..")
        study_info = orthanc_client.get_studies_id(study_identifier)
        series_info = orthanc_client.get_series_id(study_info['Series'][0])
        instance_info = orthanc_client.get_instances_id(series_info['Instances'][len(series_info['Instances'])//2],
                                                        params=f'requestedTags={requested_tags}')
        s.update(instance_info['RequestedTags'])
        s['study_orthanc_id'] = study_info['ID']
        metadata.append(s)


    metadata_df = pd.DataFrame(metadata)
    now = datetime.now().strftime("%Y%m%d")
    metadata_df.to_csv(f'pacs_metadata/meta_pacs_{len(study_identifiers)}_{now}.csv', index=False, sep=";")
