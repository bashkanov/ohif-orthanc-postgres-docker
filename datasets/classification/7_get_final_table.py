# Match volumetric info
import os
import pandas as pd

volumes = pd.read_csv("/home/oleksii/projects/ohif-orthanc-postgres-docker/datasets/classification/prostate_class_dataset_volumetry.csv")
volumes_manual = pd.read_csv("/home/oleksii/projects/ohif-orthanc-postgres-docker/datasets/classification/prostate_class_dataset_volumetry_zonal_dataset.csv", sep=';')
merged_volumes = pd.merge(volumes, volumes_manual, on='study_oid', how='left', suffixes=('', '_manual'))
merged_volumes['volume_pz'] = merged_volumes['volume_pz_manual']
merged_volumes['volume_tz'] = merged_volumes['volume_tz_manual']

merged_volumes.rename(columns={'study_oid': 'study_orthanc_id'}, inplace=True)
merged_volumes = merged_volumes[['study_orthanc_id', 'volume_pz', 'volume_tz']]


df = pd.read_csv("/home/oleksii/projects/ohif-orthanc-postgres-docker/datasets/classification/prostate_class_dataset_demography_final_psa.csv", sep=";")

final_dataset = pd.merge(
    df,
    merged_volumes,
    how="left",
    on='study_orthanc_id',
)

data_path_preprocess = "/data/oleksii/Prostate-ZONE-Datasets-NRRDS/ALTA-Zone-Dataset-multimodal-preprocessed"

preprocessed_studies = os.listdir(path=data_path_preprocess)

final_dataset = final_dataset[final_dataset['study_orthanc_id'].isin(preprocessed_studies)]
final_dataset = final_dataset[~final_dataset['volume_pz'].isna()]
final_dataset.to_csv("/home/oleksii/projects/ohif-orthanc-postgres-docker/datasets/classification/prostate_class_dataset_demography_final_psa_vol.csv", sep=";", index=False)
