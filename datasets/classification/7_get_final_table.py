# Match volumetric info
import os
import pandas as pd

volumes = pd.read_csv("/home/oleksii/projects/ohif-orthanc-postgres-docker/datasets/2_classification/prostate_class_dataset_volumetry.csv")

volumes.rename(columns={'study_oid': 'study_orthanc_id'}, inplace=True)
volumes = volumes[['study_orthanc_id', 'volume_pz', 'volume_tz']]

df = pd.read_csv("/home/oleksii/projects/ohif-orthanc-postgres-docker/datasets/2_classification/prostate_class_dataset_demography_final_psa.csv", sep=";")

final_dataset = pd.merge(
    df,
    volumes,
    how="left",
    on='study_orthanc_id',
)

data_path_preprocess = "/data/oleksii/Prostate-Classification-Datasets-NRRDS/ALTA-Classification-Dataset-preprocess/"

preprocessed_studies = os.listdir(path=data_path_preprocess)

final_dataset = final_dataset[final_dataset['study_orthanc_id'].isin(preprocessed_studies)]
final_dataset = final_dataset[~final_dataset['volume_pz'].isna()]


final_dataset.to_csv("/home/oleksii/projects/ohif-orthanc-postgres-docker/datasets/2_classification/prostate_class_dataset_demography_final_psa_vol.csv", sep=";", index=False)
