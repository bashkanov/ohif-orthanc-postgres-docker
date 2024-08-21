import SimpleITK as sitk
import numpy as np
import glob 
import os
import tqdm

def populate_with_empty_segmentations():
    # t2ws = glob.glob("/data/oleksii/Prostate-Lesion-Datasets-NRRDS/ALTA-Lesion-Dataset-negative-final/*/*-tw2_tra.nrrd")
    # t2ws = glob.glob("/data/oleksii/Prostate-Lesion-Datasets-NRRDS/ALTA-Lesion-Dataset-alta_ai-export20240809-healthy/*/*-tw2_tra.nrrd")
    
    t2ws = glob.glob("/data/oleksii/Prostate-Lesion-Datasets-NRRDS/ALTA-Lesion-Dataset-alta_ai-export20240809-healthy/*/*tw2_tra.nrrd")
    
    for t2w in tqdm.tqdm(t2ws):
        t2w_img = sitk.ReadImage(t2w)
        t2w_arr = sitk.GetArrayFromImage(t2w_img) 
        z = np.zeros(t2w_arr.shape, dtype=np.int8)
        seg = sitk.GetImageFromArray(z) 
        seg.CopyInformation(t2w_img)
        path_split = t2w.split('/')
        
        new_path = '/'.join([*path_split[:-1], f"Segmentation-label-no-lesion.seg.nrrd"])
        new_path = new_path.replace(path_split[-3], path_split[-3]+'-seg')
        
        print(new_path)
        os.makedirs(os.path.dirname(new_path), exist_ok=True)
        sitk.WriteImage(seg, new_path, True)


if __name__=="__main__":
    populate_with_empty_segmentations()
        
        