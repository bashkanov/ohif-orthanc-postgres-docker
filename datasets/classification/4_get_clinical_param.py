import datetime
import pandas as pd
import numpy as np
from utils.utils import get_orthanc_client




if __name__=="__main__":

    # Retrieve class information for these cases
    fetched_data = pd.read_csv('/home/oleksii/projects/ohif-orthanc-postgres-docker/datasets/2_classification/clinical_metainfo/sequence_map_classicifation_20240410.csv', sep=';')
    fetched_data = fetched_data[['study_orthanc_id', 'PatientID']]
    class_list_22_23 = pd.read_excel("/home/oleksii/projects/ohif-orthanc-postgres-docker/datasets/2_classification/clinical_metainfo/PACS Magdeburg mit Klassen 2022 und 2023.xlsx")
    class_list_22_23.rename(columns={'Gleason': 'GS', 'Klasse': 'class'}, inplace=True)
    
    class_list_09_21 = pd.read_csv("/home/oleksii/projects/ohif-orthanc-postgres-docker/datasets/2_classification/klassenliste_matched_with_pacs_20240411.csv", sep=";")
    
    class_list = pd.concat([class_list_09_21, class_list_22_23])
    class_list = class_list[['study_orthanc_id', 'class', 'GS']]
    
    fetched_data_m = pd.merge(
        fetched_data,
        class_list,
        how="left",
        on='study_orthanc_id',
    )
    # fixing some missing values manually  
    fetched_data_m.loc[(fetched_data_m['PatientID'] == '8370') & fetched_data_m['class'].isna() & fetched_data_m['GS'].isna(), 'class'] = 'Tumorfrei'
    fetched_data_m.loc[(fetched_data_m['PatientID'] == '11115') & fetched_data_m['class'].isna() & fetched_data_m['GS'].isna(), 'class'] = 'Prostatitis'
    fetched_data_m.loc[(fetched_data_m['PatientID'] == '23494') & fetched_data_m['class'].isna() & fetched_data_m['GS'].isna(), 'class'] = 'Prostatitis'
    
    # cleaning classes up
    fetched_data_m.loc[(fetched_data_m['GS'] == 'Gleason 10'), 'GS'] = '10'
    fetched_data_m.loc[(fetched_data_m['GS'] == 'Gleason 9'), 'GS'] = '9'
    fetched_data_m.loc[(fetched_data_m['GS'] == 'Gleason 8'), 'GS'] = '8'
    fetched_data_m.loc[(fetched_data_m['GS'] == 'Gleason 7b'), 'GS'] = '7b'
    fetched_data_m.loc[(fetched_data_m['GS'] == 'Gleason 7a'), 'GS'] = '7a'
    fetched_data_m.loc[(fetched_data_m['GS'] == 'Gleason 7'), 'GS'] = '7a'
    fetched_data_m.loc[(fetched_data_m['GS'] == 'Gleason 6'), 'GS'] = '6'
    fetched_data_m.loc[(fetched_data_m['GS'] == '3'), 'GS'] = '6'
    fetched_data_m.loc[(fetched_data_m['GS'] == '5'), 'GS'] = '6'
    fetched_data_m.loc[(fetched_data_m['GS'] == '-'), 'GS'] = None
    fetched_data_m.loc[(fetched_data_m['GS'].isna()), 'GS'] = None
    fetched_data_m = fetched_data_m[~(fetched_data_m['GS'] == 'Gleason nicht möglich')]
    
    fetched_data_m.loc[(fetched_data_m['class'] == 'Karzinom + chronische Entzündung + High Grade Pin'), 'class'] = 'Cancer+CI+HGP'
    fetched_data_m.loc[(fetched_data_m['class'] == 'Karzinom + chronische Entzündung'), 'class'] = 'Cancer+CI'
    fetched_data_m.loc[(fetched_data_m['class'] == 'Karzinom'), 'class'] = 'Cancer'
    fetched_data_m.loc[(fetched_data_m['class'] == 'Karzinom + High Grade Pin'), 'class'] = 'Cancer+HGP'
    fetched_data_m.loc[(fetched_data_m['class'] == 'chronische Entzündung'), 'class'] = 'CI'
    fetched_data_m.loc[(fetched_data_m['class'] == 'chronische Entzündung (Verdacht)'), 'class'] = 'CI'
    fetched_data_m.loc[(fetched_data_m['class'] == 'chronische Entzündung + High Grade Pin'), 'class'] = 'CI+HGP'
    fetched_data_m.loc[(fetched_data_m['class'] == 'Prostatitis'), 'class'] = 'CI'
    fetched_data_m.loc[(fetched_data_m['class'] == 'Prostatitis + Cancer'), 'class'] = 'Cancer+CI'
    fetched_data_m.loc[(fetched_data_m['class'] == 'Tumorfrei'), 'class'] = 'tumor_free'
    fetched_data_m.loc[(fetched_data_m['class'] == 'Tumorfrei (ohne Bopsie)'), 'class'] = 'tumor_free_no_biopsy'
    fetched_data_m.loc[(fetched_data_m['class'].isna() & ~fetched_data_m['GS'].isna()), 'class'] = 'Cancer'
    
    fetched_data_m['csPCa'] = np.where(fetched_data_m['GS'].isin(['7a', '7b', '8', '9', '10']), True, False)
    
    # Adding ordinal attribute to the class label
    fetched_data_m.loc[(fetched_data_m['GS'] == '10'), 'GS_order'] = 7
    fetched_data_m.loc[(fetched_data_m['GS'] == '9'), 'GS_order'] = 6
    fetched_data_m.loc[(fetched_data_m['GS'] == '8'), 'GS_order'] = 5
    fetched_data_m.loc[(fetched_data_m['GS'] == '7b'), 'GS_order'] = 4
    fetched_data_m.loc[(fetched_data_m['GS'] == '7a'), 'GS_order'] = 3
    fetched_data_m.loc[(fetched_data_m['GS'] == '7'), 'GS_order'] = 2
    fetched_data_m.loc[(fetched_data_m['GS'] == '6'), 'GS_order'] = 1
    fetched_data_m.loc[(fetched_data_m['GS'].isna()), 'GS_order'] = 0
    
    fetched_data_m.loc[fetched_data_m['class'] == 'tumor_free', 'class_order'] = 0
    fetched_data_m.loc[fetched_data_m['class'] == 'tumor_free_no_biopsy', 'class_order'] = 1
    fetched_data_m.loc[fetched_data_m['class'] == 'High Grade Pin', 'class_order'] = 2
    fetched_data_m.loc[fetched_data_m['class'] == 'CI', 'class_order'] = 3
    fetched_data_m.loc[fetched_data_m['class'] == 'Cancer', 'class_order'] = 4
    fetched_data_m.loc[fetched_data_m['class'] == 'Cancer+HGP', 'class_order'] = 5
    fetched_data_m.loc[fetched_data_m['class'] == 'Cancer+CI', 'class_order'] = 6
    fetched_data_m.loc[fetched_data_m['class'] == 'Cancer+CI+HGP', 'class_order'] = 7
    
    
    # Fetch demographic information     
    pacs_meta_data = pd.read_csv('/home/oleksii/projects/ohif-orthanc-postgres-docker/metadata/meta_pacs_13056_20240126.csv', sep=';')    
    pacs_meta_data = pacs_meta_data[["PatientBirthDate", "PatientSize", "PatientWeight", "StudyDate", "study_orthanc_id"]]
    
    fetched_data_demography = pd.merge(
        fetched_data_m,
        pacs_meta_data,
        how="left",
        on='study_orthanc_id',
    )
    
    # Convert the date columns to datetime objects
    fetched_data_demography['PatientBirthDate'] = pd.to_datetime(fetched_data_demography['PatientBirthDate'], format='%Y%m%d')
    fetched_data_demography['StudyDate'] = pd.to_datetime(fetched_data_demography['StudyDate'], format='%Y%m%d')
    # Calculate the difference in years
    fetched_data_demography['PatientAgeAtStudy'] = (fetched_data_demography['StudyDate'] - fetched_data_demography['PatientBirthDate']).dt.days / 365.25
    fetched_data_demography['PatientAgeAtStudy'] = fetched_data_demography['PatientAgeAtStudy'].round(2)   
        
    # BMI Liste is not really helpful 
    # bmi_liste = pd.read_excel("/home/oleksii/projects/ohif-orthanc-postgres-docker/datasets/2_classification/clinical_metainfo/BMI Liste.xlsx")    
    # fetched_data_demography_noheight = fetched_data_demography[fetched_data_demography['PatientSize'].isna()]
    # how_much = fetched_data_demography_noheight[fetched_data_demography_noheight['PatientID'].isin(bmi_liste['PatientID'])]
            
    # Get ALTA IDs from another table and match them with DICOM PatientIDs for better patient grouping
    alta_patient_ids = pd.read_excel("/home/oleksii/projects/ohif-orthanc-postgres-docker/datasets/2_classification/clinical_metainfo/PACS Magdeburg mit ALTA IDs.xlsx")
    alta_patient_ids.rename(columns={'ALTA_Pat-ID': 'ALTAPatientID'}, inplace=True)
    alta_patient_ids = alta_patient_ids[['ALTAPatientID', 'study_orthanc_id']]
    fetched_data_demography_alta_id = pd.merge(
        fetched_data_demography,
        alta_patient_ids,
        how="left",
        on='study_orthanc_id',
    )


    # Deal with duplicates    
    # 1. Remove the global duplicates
    fetched_data_demography_alta_id = fetched_data_demography_alta_id.drop_duplicates(keep="first")

    # 2. Resolve possible typo errors in PatientID (ALTA ID) 
    duplicates = fetched_data_demography_alta_id[fetched_data_demography_alta_id.duplicated(subset=['study_orthanc_id', 'class', 'GS'], keep=False)]
    duplicates['ALTAPatientID'] =  duplicates['PatientID']
    duplicates = duplicates.drop_duplicates(keep="first")
    # remove duplicated cases and append resolved one
    fetched_data_demography_alta_id = fetched_data_demography_alta_id[~fetched_data_demography_alta_id['study_orthanc_id'].isin(duplicates['study_orthanc_id'])]
    fetched_data_demography_alta_id = pd.concat([fetched_data_demography_alta_id, duplicates])
    
    # 3. Pick the biggest class 
    fetched_data_demography_alta_id = fetched_data_demography_alta_id.sort_values(['GS_order', 'class_order'], ascending=False)
    fetched_data_demography_alta_id = fetched_data_demography_alta_id.drop_duplicates(subset=['study_orthanc_id'], keep='first')
    fetched_data_demography_alta_id['ALTAPatientID'] = fetched_data_demography_alta_id['ALTAPatientID'].fillna(fetched_data_demography_alta_id['PatientID'])
    fetched_data_demography_alta_id['ALTAPatientID'] = fetched_data_demography_alta_id['ALTAPatientID'].astype(int).astype(str)

    fetched_data_demography_alta_id.to_csv("/home/oleksii/projects/ohif-orthanc-postgres-docker/datasets/2_classification/prostate_class_dataset_demography_final.csv", sep=";", index=None)