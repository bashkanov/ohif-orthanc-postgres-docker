############
# Here, the available psa values are being matched with MRI studies by ALTA ID. PSAs done after studydate are being ignored
############

import pandas as pd

df = pd.read_csv("/home/oleksii/projects/ohif-orthanc-postgres-docker/datasets/2_classification/prostate_class_dataset_demography_final.csv", sep=";")
psa = pd.read_excel("/home/oleksii/projects/ohif-orthanc-postgres-docker/datasets/2_classification/clinical_metainfo/PSA-Werte.xlsx")
psa.rename(columns={'Pat-ID': 'ALTAPatientID', 'PSA-Datum': 'StudyDate'}, inplace=True)

def group_psa_data(patient_id, study_date, psa_table):
    filtered_psa = psa_table[psa_table['ALTAPatientID'] == patient_id]
    filtered_psa = filtered_psa[filtered_psa['StudyDate'] <= study_date]
    PSA = filtered_psa['PSA'].astype(str).str.cat(sep=',')
    freePSA = filtered_psa['freePSA'].astype(str).str.cat(sep=',')
    ratioPSA = filtered_psa['ratioPSA'].astype(str).str.cat(sep=',')
    CRP = filtered_psa['CRP'].astype(str).str.cat(sep=',')
    censitiveCRP = filtered_psa['sensitiveCRP'].astype(str).str.cat(sep=',')
    psaDate = filtered_psa['StudyDate'].astype(str).str.cat(sep=',')
    return pd.Series([PSA, freePSA, ratioPSA, CRP, censitiveCRP, psaDate])

df[['psa', 'freePSA', 'ratioPSA', 'CRP', 'censitiveCRP', 'psaDate']] = df.apply(lambda row: group_psa_data(row['ALTAPatientID'], row['StudyDate'], psa), axis=1)

df.to_csv("/home/oleksii/projects/ohif-orthanc-postgres-docker/datasets/2_classification/prostate_class_dataset_demography_final_psa.csv", sep=";", index=False)

