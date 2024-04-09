import re
from typing import Union

import pandas as pd
import numpy as np
from pandas import DataFrame

pd.options.mode.chained_assignment = None  # default='warn'

def is_unique(s):
    a = s.to_numpy() # s.values (pandas<0.24)
    return (a[0] == a).all()

def replace_decapitalized_descriptions(df: DataFrame) -> DataFrame:
    relevant_fields = ['t2w_tra', 't2w_sag', 't2w_cor',
                       'adc_tra', 'adc_sag', 'adc_cor',
                       'dwi_tra', 'dwi_sag', 'dwi_cor']

    series_desc = list(df['SeriesDescription'])
    old_series_desc = list(df['OldSeriesDescription'])

    def replace_decap_description(description: Union[str, None]) -> Union[str, None]:
        if description is None:
            return None
        return old_series_desc[series_desc.index(description)]

    for _field in relevant_fields:
        field_list = list(df[_field])
        field_list = [replace_decap_description(_desc) for _desc in field_list]
        df[_field] = field_list

    return df


def _parse_orientation(orientation: str):
    if orientation is None: 
        return
    orientation = orientation.split('\\')
    orientation_template = {'[1, 0, 0, 0, 0, -1]': 'cor',
                            '[0, 1, 0, 0, 0, -1]': 'sag',
                            '[1, 0, 0, 0, 1, 0]': 'tra'}

    rounded_orientation = str([round(float(x)) for x in orientation])
    if rounded_orientation not in orientation_template.keys():
        return

    return orientation_template[rounded_orientation]


def clean_alt_list(list_):
    list_ = list_.replace('(', '[')
    list_ = list_.replace(')', ']')
    list_ = list_.replace('nan', 'None')
    list_ = list_.replace('none', 'None')
    return list_


def strlist_to_objlist(df, column_name):
    df[column_name] = df[column_name].astype(str)
    df[column_name] = df[column_name].str.lower()
    df[column_name] = df[column_name].apply(clean_alt_list)
    return df

    
def get_series_itemised_data(x, name):
    if x is not None:
        if type(x[name]) == pd.core.series.Series:
            return ','.join(x[name].to_list())
        else:
            return x[name]
    else:
        return None
            

def process_dicom_meta_info(dicom_findings: DataFrame):
    
    dicom_findings['ImageOrientationPatientStr'] = dicom_findings['ImageOrientationPatient'].apply(_parse_orientation)
    dicom_findings = dicom_findings.apply(lambda x: x.astype(str).str.lower())
    dicom_findings['SliceThickness'] = pd.to_numeric(dicom_findings['SliceThickness'], errors='coerce')
    dicom_findings['FileCount'] = pd.to_numeric(dicom_findings['FileCount'], downcast='integer', errors='coerce')
        
    def find_valid_t2w(x, manufacturer=None):
  
        def get_all_candidates_t2w(series_description, image_type):
            series_description = series_description.lower() if series_description is not None else series_description
            image_type = image_type.lower() if image_type is not None else ''
            
            # should we use t2_trufi_tra_3mm as well?
            if series_description is not None:
                if re.search(r"t2.*tse|t2tse|t2.*space", series_description) and not bool(re.search(r"fs|spc", series_description)):
                    return True            
            return False
        

        def get_candidate_for_orientation(x, orient):
            x_orient = x[x['ImageOrientationPatientStr'] == orient]
            
            if len(x_orient) == 0:
                return None
            
            if len(x_orient) == 1:
                candidate_id = x_orient.iloc[0]
            else:
                x_orient.loc[:, 'contains_orient'] = x_orient.apply(lambda x: x['ImageType'] == f't2_tse_{orient}', axis=1)
                if len(x_orient[x_orient['contains_orient']]) == 1:
                    candidate_id = x_orient[x_orient['contains_orient']].iloc[0]
                elif is_unique(x_orient['SliceThickness']):   
                    # fallback to the mminimum smaller slice thickness 
                    candidate_id = x_orient.loc[x_orient['SliceThickness'].idxmax()]
                else: 
                    # fallback to the max number of instances
                    candidate_id = x_orient.loc[x_orient['FileCount'].idxmax()]
            
            return candidate_id
        
        x['pre_match'] = x.apply(lambda x: get_all_candidates_t2w(x['SeriesDescription'], x['ImageType']), axis=1)
        x = x[x['pre_match']]
        
        tra = get_candidate_for_orientation(x, 'tra')
        sag = get_candidate_for_orientation(x, 'sag')
        cor = get_candidate_for_orientation(x, 'cor')
        
        return {
            "t2w_tra_id": tra['series_orthanc_id'] if tra is not None else None,
            "t2w_tra_sd": tra['SeriesDescription'] if tra is not None else None,
            "t2w_sag_id": sag['series_orthanc_id'] if sag is not None else None,
            "t2w_sag_sd": sag['SeriesDescription'] if sag is not None else None,
            "t2w_cor_id": cor['series_orthanc_id'] if cor is not None else None,
            "t2w_cor_sd": cor['SeriesDescription'] if cor is not None else None,
        }

    def find_valid_dwis(x, manufacturer=None):
            
        def get_all_candidates_siemens(series):
            if series['SeriesDescription'] is not None:
                if re.search('|'.join(['ep2d', 'diff', 'tracew', 'tracerw', 'zoomit_epi']), series['SeriesDescription']) and \
                    not re.search('|'.join(['t1', 'spc', 'adc', 'calc', 'vibe', 'vii']), series['SeriesDescription']) and \
                        not re.search('|'.join(['secondary', 'adc', 'spc', 'adc', 'calc', 'vibe', 'vii']), series['ImageType']):
                    
                    return True
            
            return False
        
        def get_all_candidates_philips(series):
            if series['SeriesDescription'] is not None:
                if re.search('|'.join(['dwi']), series['SeriesDescription']):
                    return True
            
            return False
        
        def get_candidate_for_orientation_siemens(x, orient):
            x_orient = x[x['ImageOrientationPatientStr'] == orient]
            if len(x_orient) == 0:
                return None
            
            x_orient.loc[:, 'no_becken'] = x_orient.apply(lambda x: bool(re.search(r"^((?!becken).)*$", x['SeriesDescription'])), axis=1)           
            
            if len(x_orient) == 1:
                candidate_id = x_orient.iloc[0]
            elif len(x_orient[x_orient['no_becken']]) == 1:
                # exclude with becken first 
                candidate_id = x_orient[x_orient['no_becken']].iloc[0]
            elif is_unique(x_orient['SliceThickness']):
                # covers the case where DWIs are presented as multiple series with different b-values
                # if there is a series wich consists of all separate cases, then take it, and ignore others
                if is_unique(x_orient['FileCount']) and not is_unique(x_orient['SequenceName']):
                    candidate_id = x_orient
                else: 
                    unique = x_orient['FileCount'].unique()
                    x_orient_itemised = x_orient[x_orient['FileCount'] == unique.min()]
                    if unique.max() // unique.min()  == len(x_orient_itemised):
                        candidate_id = x_orient[x_orient['FileCount'] == unique.max()]
                    else: 
                        candidate_id = x_orient_itemised
            elif not is_unique(x_orient['SliceThickness']):                
                # fallback to the mminimum smaller slice thickness 
                candidate_id = x_orient.loc[x_orient['SliceThickness'].idxmax()]
            else:
                candidate_id = x_orient
                # fallback to the max number of instances
                # candidate_id = x_orient.loc[x_orient['FileCount'].idxmax()]
            
            return candidate_id
        
        def get_candidate_for_orientation_philips(x, orient):
            x_orient = x[x['ImageOrientationPatientStr'] == orient]
            if len(x_orient) == 0:
                return None
            # simple rule for phillips so far
            x_orient.loc[:, 'no_becken'] = x_orient.apply(lambda x: bool(re.search(r"^((?!becken).)*$", x['SeriesDescription'])), axis=1)           
            candidate_ids = x_orient[x_orient['FileCount'] > 2]
            return candidate_ids
        
        if manufacturer == 'philips':
            get_all_candidates = get_all_candidates_philips
            get_candidate_for_orientation = get_candidate_for_orientation_philips
        else:
            get_all_candidates = get_all_candidates_siemens
            get_candidate_for_orientation = get_candidate_for_orientation_siemens
            
        # maybe better use protocol name?
        x.loc[:, "dwi_pre_match"] = x.apply(lambda x: get_all_candidates(x.astype(str).str.lower()), axis=1)
        x = x[x["dwi_pre_match"]]
        
        tra = get_candidate_for_orientation(x, 'tra')
        sag = get_candidate_for_orientation(x, 'sag')
        cor = get_candidate_for_orientation(x, 'cor')
            
        return {
            "dwi_tra_id": get_series_itemised_data(tra, 'series_orthanc_id'),
            "dwi_tra_sd": get_series_itemised_data(tra, 'SeriesDescription'),
            "dwi_sag_id": get_series_itemised_data(sag, 'series_orthanc_id'),
            "dwi_sag_sd": get_series_itemised_data(sag, 'SeriesDescription'),
            "dwi_cor_id": get_series_itemised_data(cor, 'series_orthanc_id'),
            "dwi_cor_sd": get_series_itemised_data(cor, 'SeriesDescription'),
        }

        
    def find_valid_adc(x, manufacturer=None):
                        
        def get_all_candidates_adc(series_description, image_type):
            series_description = series_description.lower() if series_description is not None else series_description
            image_type = image_type.lower() if image_type is not None else ''
            
            if series_description is not None:
                if re.search(r"adc|.adc.", series_description) and \
                'projection image' not in image_type and \
                'secondary' not in image_type:
                    return True
            
            return False

        def get_candidate_for_orienttation(x, orient):
            x_orient = x[x['ImageOrientationPatientStr'] == orient]
            
            if len(x_orient) == 0:
                return None
            
            if len(x_orient) == 1:
                candidate_id = x_orient.iloc[0]
            else:

                x_orient.loc[:, 'ep2d'] = x_orient.apply(lambda x: bool(re.search(r"ep2d|ep.2d", x['SeriesDescription'])), axis=1)
                x_orient.loc[:, 'NO_NORM'] = x_orient.apply(lambda x: bool(re.search(r"^((?!norm).)*$", x['ImageType'])) 
                                                     if(np.all(pd.notnull(x['ImageType']))) else True, axis=1)
                x_orient.loc[:, 'becken'] = x_orient.apply(lambda x: bool(re.search(r"^((?!becken).)*$", x['SeriesDescription'])), axis=1)

                # reduce based on these criterias
                x_orient_all_ok = x_orient[x_orient['ep2d'] & x_orient['NO_NORM'] & x_orient['becken']]
                if len(x_orient_all_ok) == 1:
                    candidate_id = x_orient_all_ok.iloc[0]
                else: 
                    # fallback to the mminimum number of instances
                    candidate_id = x_orient.loc[x_orient['FileCount'].idxmin()]
            
            return candidate_id
        
        x['adc_pre_match'] = x.apply(lambda x: get_all_candidates_adc(x['SeriesDescription'], x['ImageType']), axis=1)
        x = x[x['adc_pre_match']]
        
        tra = get_candidate_for_orienttation(x, 'tra')
        sag = get_candidate_for_orienttation(x, 'sag')
        cor = get_candidate_for_orienttation(x, 'cor')
            
        return {
            "adc_tra_id": get_series_itemised_data(tra, 'series_orthanc_id'),
            "adc_tra_sd": get_series_itemised_data(tra, 'SeriesDescription'),
            "adc_sag_id": get_series_itemised_data(sag, 'series_orthanc_id'),
            "adc_sag_sd": get_series_itemised_data(sag, 'SeriesDescription'),
            "adc_cor_id": get_series_itemised_data(cor, 'series_orthanc_id'),
            "adc_cor_sd": get_series_itemised_data(cor, 'SeriesDescription'),
        }

    def identify_manufacturer(x):
        x = x[~x['Manufacturer'].isna()]
        if len(x) == 0:
            return {'Manufacturer': 'unavailable'}
        elif x['Manufacturer'][0] in ('siemens', 'siemens healthineers', 'ge medical system', 'hitachi', 'philips', 'toshiba'):
            return {'Manufacturer': x['Manufacturer'][0]}
        else: 
            return {'Manufacturer': 'unknown'}
        
    dicom_findings_m = identify_manufacturer(dicom_findings)
    dicom_findings_t2w = find_valid_t2w(dicom_findings, manufacturer=dicom_findings_m['Manufacturer'])
    dicom_findings_adc = find_valid_adc(dicom_findings, manufacturer=dicom_findings_m['Manufacturer'])
    dicom_findings_dwi = find_valid_dwis(dicom_findings, manufacturer=dicom_findings_m['Manufacturer'])

    
    return dict(**dicom_findings_t2w, **dicom_findings_adc, **dicom_findings_dwi, **dicom_findings_m)