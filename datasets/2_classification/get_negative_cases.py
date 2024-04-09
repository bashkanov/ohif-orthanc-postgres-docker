#  Retrieve data with "healthy patients"

# - 1. Based on the KlassenListe extract lesion free cases
# - 2. Go to orthanc and find the corresponding study 
# - 3. Take cases from the external clinics 


import pandas as pd
from pyorthanc import Patient
from datetime import datetime
from utils import get_orthanc_client

if __name__=="__main__":
    orthanc_client = get_orthanc_client()

    class_list_big = pd.read_excel('/hdd/drive1/oleksii/Klassenliste für Oleksii.xlsx')
    class_list_big_fremd = pd.read_excel('/hdd/drive1/oleksii/Klassenliste für Oleksii.xlsx', 'Fremd MRTs mit Biopsie')

    negative_cases_lesion_segs = class_list_big[class_list_big['Klasse'].isin(['Tumorfrei', 'Tumorfrei (ohne Bopsie)']) & (class_list_big['Verwenden?'] == 'ja') ]
    negative_cases_lesion_segs_external = class_list_big_fremd[class_list_big_fremd['Klasse'].isin(['Tumorfrei', 'Tumorfrei (ohne Bopsie)'])  & (class_list_big_fremd['Verwenden?'] == 'ja')]

    lesion_free_studies = []

    for index, row in negative_cases_lesion_segs.iterrows():
        patient_candidates = orthanc_client.post_tools_lookup(data=str(row['ALTA ID']))
        # find patient in orthanc database     
        if len(patient_candidates) != 0:
            if patient_candidates[0]['Type'] == 'Patient': 
                patient = Patient(patient_candidates[0]['ID'], orthanc_client)
                if len(patient.studies) != 0:
                    for study in patient.studies:
                        study_time_orthanc = datetime.strptime(study.get_main_information()['MainDicomTags']['StudyDate'], '%Y%m%d')
                        study_time_record = row['Study Date']
                        diff = study_time_orthanc - study_time_record
                        if abs(diff.days) < 30:
                            lesion_free_studies.append(study.id_)


    lesion_free_studies_external = []

    for index, row in negative_cases_lesion_segs_external.iterrows():
        patient_candidates = orthanc_client.post_tools_lookup(data=str(row['Pat_ID']))
        # find patient in orthanc database     
        if len(patient_candidates) != 0:
            if patient_candidates[0]['Type'] == 'Patient': 
                patient = Patient(patient_candidates[0]['ID'], orthanc_client)
                if len(patient.studies) != 0:
                    for study in patient.studies:
                        study_time_orthanc = datetime.strptime(study.get_main_information()['MainDicomTags']['StudyDate'], '%Y%m%d')
                        study_time_record = row['StudyDate']
                        diff = study_time_orthanc - study_time_record
                        if abs(diff.days) < 30:
                            lesion_free_studies_external.append(study.id_)
        else:
            patient_candidates = orthanc_client.post_tools_lookup(data=str(row['ALTA ID']))
            # second attempt find patient in orthanc database     
            if len(patient_candidates) != 0:
                if patient_candidates[0]['Type'] == 'Patient': 
                    patient = Patient(patient_candidates[0]['ID'], orthanc_client)
                    if len(patient.studies) != 0:
                        for study in patient.studies:
                            study_time_orthanc = datetime.strptime(study.get_main_information()['MainDicomTags']['StudyDate'], '%Y%m%d')
                            study_time_record = row['StudyDate']
                            diff = study_time_orthanc - study_time_record
                            if abs(diff.days) < 30:
                                lesion_free_studies_external.append(study.id_)


    lesion_free_studies_final = lesion_free_studies + lesion_free_studies_external
    # remove duplicates
    lesion_free_studies_final = set(lesion_free_studies_final)

    # select data based on sequence mapping
    seq_map = pd.read_csv('meta_data_lesion/sequence_mapping_13056_studies_20240124.csv', sep=';')
    seq_map_neg = seq_map[seq_map['study_orthanc_id'].isin(lesion_free_studies_final)]
    seq_map_neg = seq_map_neg[~(seq_map_neg['t2w_tra_id'].isna())]
    seq_map_neg.to_csv("meta_data_lesion/seq_map_neg.csv", sep=';', index=False)