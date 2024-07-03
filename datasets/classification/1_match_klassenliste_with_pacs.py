import pandas as pd
from pyorthanc import Patient
from datetime import datetime
import tqdm 
from utils.utils import get_orthanc_client


def get_othanc_study_ids(df, orthanc_client):
        
    def get_oid_from_patient(patient_candidates):
        studies_of_patient = []
        if len(patient_candidates) != 0:
            if patient_candidates[0]['Type'] == 'Patient': 
                patient = Patient(patient_candidates[0]['ID'], orthanc_client)
                if len(patient.studies) != 0:
                    for study in patient.studies:
                        study_time_orthanc = datetime.strptime(study.get_main_information()['MainDicomTags']['StudyDate'], '%Y%m%d')
                        study_time_record = row['StudyDate']
                        diff = study_time_orthanc - study_time_record
                        if abs(diff.days) < 30:
                            studies_of_patient.append({
                                "study_orthanc_id": study.id_,
                                "dicom_patient_id": patient.patient_id,
                                "study_time_orthanc": study_time_orthanc, 
                                "study_time_record": study_time_record
                                })
        return studies_of_patient

    matched_study_ids = []
    for index, row in tqdm.tqdm(df.iterrows()):
        # find patient in orthanc database     
        patient_candidates = orthanc_client.post_tools_lookup(data=str(row['Pat_ID']))
        patient_id = str(row['Pat_ID'])
        row_type = 'Pat_ID'
        if len(patient_candidates) == 0:
            patient_candidates = orthanc_client.post_tools_lookup(data=str(row['ALTA ID']))
            patient_id = str(row['ALTA ID'])
            row_type = 'ALTA ID'
            # second attempt find patient in orthanc database     
        
        studies_of_patient = get_oid_from_patient(patient_candidates)
        for item in studies_of_patient:
            item['patient_id'] = patient_id
            item['row_type'] = row_type
            
            item['GS'] = row['Gleason']
            item['class'] = row['Klasse']
        matched_study_ids.extend(studies_of_patient)
                                            
    return matched_study_ids


if __name__=="__main__":
    orthanc_client = get_orthanc_client()

    # class_list_big_fremd = pd.read_excel('/hdd/drive1/oleksii/Klassenliste für Oleksii.xlsx', 'Fremd MRTs mit Biopsie')
    class_list_0921 = pd.read_excel('/home/oleksii/projects/ohif-orthanc-postgres-docker/metadata/Klassenliste für Oleksii 2009-2021.xlsx')
    class_list_0921.rename(columns={'Study Date': 'StudyDate'}, inplace=True)
    
    class_list_0921_ext = pd.read_excel('/home/oleksii/projects/ohif-orthanc-postgres-docker/metadata/Klassenliste für Oleksii 2009-2021.xlsx',  'Fremd MRTs mit Biopsie')
    class_list_0921_ext.rename(columns={'GS': 'Gleason'}, inplace=True)
    
    class_list_0921_to_use = class_list_0921[class_list_0921['Verwenden?'] == 'ja']
    class_list_0921_ext_to_use = class_list_0921_ext[class_list_0921_ext['Verwenden?'] == 'ja']
    df = pd.concat([class_list_0921_to_use, class_list_0921_ext_to_use], axis=0)
    # df = df.head(10)
    
    final_study_orthanc_ids = get_othanc_study_ids(df, orthanc_client)
    
    # remove duplicates
    final_study_orthanc_ids_final = [dict(t) for t in {tuple(sorted(d.items())) for d in final_study_orthanc_ids}]

    matched_with_pacs = pd.DataFrame(final_study_orthanc_ids_final)
    today = datetime.today().strftime('%Y%m%d')

    matched_with_pacs.to_csv(f'klassenliste_matched_with_pacs_{today}.csv', sep=';')
