import os 
import numpy as np
import SimpleITK as sitk
import pandas as pd
import glob 
import tqdm 


def segment_volume(segmentation, spacing):
    # A metric unit of volume equal to one thousandth of a liter
    # Return volume in ml or cubic centimeters cm^3
    volume = np.sum(segmentation) / 1000.0
    volume = volume * np.prod(spacing)
    return round(volume, 2)

if __name__=="__main__":
    
    found_segmentations = glob.glob("/data/oleksii/Prostate-Classification-Datasets-NRRDS/ALTA-Classification-Dataset-Segmentations/*/*-SegmentationAI.seg.nrrd")
    records = []
    for seg in tqdm.tqdm(found_segmentations[:]):
        record = {}
        study_oid = os.path.dirname(seg).split('/')[-1]
        seg_img = sitk.ReadImage(seg)        
        seg_arr = sitk.GetArrayFromImage(seg_img)
        seg_arr = seg_arr.astype(int)
        spacing = seg_img.GetSpacing()
        seg_pz = seg_arr[..., 0]
        seg_tz = seg_arr[..., 1]
        
        volume_pz = segment_volume(seg_pz, spacing=spacing)
        volume_tz = segment_volume(seg_tz, spacing=spacing)
        
        record["study_oid"] = study_oid
        record["spacing"] = spacing
        record["volume_pz"] = volume_pz
        record["volume_tz"] = volume_tz
        
        records.append(record)
        
    df_volume = pd.DataFrame(records)
    df_volume.to_csv("/home/oleksii/projects/ohif-orthanc-postgres-docker/datasets/2_classification/prostate_class_dataset_volumetry.csv", index=False, sep=';')
    