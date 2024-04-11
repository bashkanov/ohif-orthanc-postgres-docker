############################################################
##
##  This code combines metainformation (age hight weight)
##  with fetched data and assigns a class to them 
##
############################################################

import pandas as pd
from datetime import datetime

today = datetime.today().strftime('%Y%m%d')


if __name__=="__main__":
    class_list_22_23 = pd.read_excel("/home/oleksii/projects/ohif-orthanc-postgres-docker/datasets/2_classification/clinical_metainfo/PACS Magdeburg mit Klassen 2022 und 2023.xlsx")
    class_list_09_21 = pd.read_csv("/home/oleksii/projects/ohif-orthanc-postgres-docker/datasets/2_classification/klassenliste_matched_with_pacs_20240410.csv", sep=";")

    studies_for_classification = class_list_22_23["study_orthanc_id"].tolist() + class_list_09_21["study_oid"].tolist()
    # studies_for_classification = class_list_22_23["study_orthanc_id"].tolist()
    # select data based on sequence mapping
    seq_map = pd.read_csv('/home/oleksii/projects/ohif-orthanc-postgres-docker/sequence_mapping/sequence_mapping_13024_studies_20240115.csv', sep=';')

    # remove duplicates
    studies_for_classification = set(studies_for_classification)
    seq_map_sel = seq_map[seq_map['study_orthanc_id'].isin(studies_for_classification)]
    seq_map_sel_ = seq_map_sel[~(seq_map_sel['t2w_tra_id'].isna())]   
    seq_map_sel_na = seq_map_sel[seq_map_sel['t2w_tra_id'].isna()]   

    seq_map_sel_.to_csv(f"./datasets/2_classification/clinical_metainfo/sequence_map_classicifation_{today}.csv", sep=";")
    seq_map_sel_na.to_csv(f"./datasets/2_classification/clinical_metainfo/sequence_map_classicifation_{today}_not2w.csv", sep=";")
