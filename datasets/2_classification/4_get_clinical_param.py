
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
    
    fetched_data_m['csPCa'] = np.where(fetched_data_m['GS'].isin(['7a', '7b', '6', '9', '8', '10']), True, False)
    
    
    pacs_meta_data = pd.read_csv('/home/oleksii/projects/ohif-orthanc-postgres-docker/metadata/meta_pacs_13056_20240126.csv', sep=';')    
    print('fake')