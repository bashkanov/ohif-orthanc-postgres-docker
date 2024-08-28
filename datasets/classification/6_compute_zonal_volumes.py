import os 
import numpy as np
import SimpleITK as sitk
import pandas as pd
import glob 
import tqdm 
import concurrent.futures
from functools import partial


def convert_labelmap_to_binary_segments(labelmap):
    '''
    This function handles different types of segmentations and stores them into the list
    '''
        
    if isinstance(labelmap, list):
        # assuming incoming list contains sitk masks
        masks = labelmap
    else:
    
        labelmap_array = sitk.GetArrayFromImage(labelmap)  
        unique_labels = np.unique(labelmap_array)

        masks = []
        if labelmap.GetNumberOfComponentsPerPixel() > 1:
            for i in range(labelmap.GetNumberOfComponentsPerPixel()):
                masks.append(sitk.VectorIndexSelectionCast(labelmap, i))
        
        elif len(unique_labels) > 1:
            # print(labelmap.GetPixelIDTypeAsString())
            if 'vector' in labelmap.GetPixelIDTypeAsString():
                labelmap = sitk.VectorIndexSelectionCast(labelmap, 0)        
            for label in unique_labels[1:]:
                binary_segment = labelmap == label
                masks.append(binary_segment)
        else:
            masks.append(labelmap)
    
    masks = [sitk.Cast(mask, sitk.sitkUInt32) for mask in masks]
    return masks

def compose_segmentation(segmentation, multichannel_output=False):
    lesion_components = convert_labelmap_to_binary_segments(segmentation)
    lesion_components = [sitk.Cast(c, sitk.sitkUInt32) for c in lesion_components]
    lesion_components = [sitk.LabelImageToLabelMap(c) for c in lesion_components]
    
    # if no segmentation is available
    if lesion_components:
        if multichannel_output:
            lesion_components = [sitk.Cast(s, sitk.sitkUInt32) for s in lesion_components]
            # lesion_components = [sitk.VectorIndexSelectionCast(s, i) for i, s in enumerate(lesion_components)]
            merged_label = sitk.Compose(*lesion_components)
            # print("number of lesion after mutlichannel:", merged_label.GetNumberOfComponentsPerPixel())
        else:
            # https://examples.itk.org/src/filtering/labelmap/mergelabelmaps/documentation
            # PACK (2): MergeLabelMapFilter relabel all the label objects by order of processing. No conflict can occur.
            
            vectorOfImages = sitk.VectorOfImage()
            for lesion in lesion_components:
                vectorOfImages.push_back(lesion)
            merged_label = sitk.MergeLabelMap(vectorOfImages, 2)
            merged_label = sitk.Cast(merged_label, sitk.sitkUInt32)
            # print("number of lesion after:", number_of_objects(merged_label))
    else: 
        seg_arr = sitk.GetArrayFromImage(segmentation)
        seg_arr = seg_arr[..., 0] if seg_arr.ndim == 4 else seg_arr
        seg_arr_empty = np.zeros_like(seg_arr)
        merged_label  = sitk.GetImageFromArray(seg_arr_empty)
        merged_label.CopyInformation(segmentation)    
        print("detected an empty segmentation!")
    return merged_label


def segment_volume(segmentation, spacing):
    # A metric unit of volume equal to one thousandth of a liter
    # Return volume in ml or cubic centimeters cm^3
    volume = np.sum(segmentation) / 1000.0
    volume = volume * np.prod(spacing)
    return round(volume, 2)


def process_segmentation(seg):
    record = {}
    study_oid = os.path.dirname(seg).split('/')[-1]
    seg_img = sitk.ReadImage(seg)        
    
    seg_img_bin = convert_labelmap_to_binary_segments(seg_img)
    seg_img = compose_segmentation(seg_img_bin, multichannel_output=True)
    
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
    
    return record

def main():

    # found_segmentations = glob.glob("/data/oleksii/Prostate-Classification-Datasets-NRRDS/ALTA-Classification-Dataset-Segmentations/*/*-SegmentationAI.seg.nrrd")
    found_segmentations = glob.glob("/data/oleksii/Prostate-ZONE-Datasets-NRRDS/ALTA-Zone-Dataset-multimodal-seg/*/*.seg.nrrd")    
    # Create a partial function with the required dependencies
    # process_seg = partial(process_segmentation)
    records = []
    
    # Use ThreadPoolExecutor for multithreading
    with concurrent.futures.ThreadPoolExecutor() as executor:
        # Submit all tasks and get future objects
        future_to_seg = {executor.submit(process_segmentation, seg): seg for seg in found_segmentations}
        
        # Use tqdm to show progress
        for future in tqdm.tqdm(concurrent.futures.as_completed(future_to_seg), total=len(found_segmentations)):
            seg = future_to_seg[future]
            try:
                record = future.result()
                records.append(record)
            except Exception as exc:
                print(f'{seg} generated an exception: {exc}')
    
    df_volume = pd.DataFrame(records)
    df_volume.to_csv(os.path.join(os.path.dirname(__file__), "prostate_class_dataset_volumetry_zonal_dataset.csv"), index=False, sep=';')


if __name__ == "__main__":
    main()