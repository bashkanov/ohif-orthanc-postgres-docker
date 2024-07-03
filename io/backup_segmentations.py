# pylint: disable=redefined-outer-name,no-member

"""
    For Debugging
    1: start container:
    docker container run -dit --network host -v /home/oleksii:/home/oleksii -v /data/oleksii:/data/oleksii alta/backend:dev
    
    2: modify launch.json:

        {
            "name": "Backup segmentations",
            "type": "python",
            "request": "launch",
            "program": "${workspaceFolder}/scripts/export/backup_segmentations.py",
            "args": [
              "--path",
              "/data/oleksii/alta-ai-orthanc-backup/2023_07_26_",
              "--segmentation_types",
              "lesion",
              "--processing_state",
              "unsure",
              "--export",
              "dcm"
            ],
            "envFile": "${workspaceFolder}/.envlocal",
            "env": {
              "PYTHONPATH": "${workspaceFolder}"
            },
            "justMyCode": false
        }
    
    To execute run the following command:    
    
    docker container run --network host -v /home/oleksii:/home/oleksii -v /data/oleksii:/data/oleksii alta/backend:dev /bin/bash -c \
        "cd /home/oleksii/projects/alta-backend/ ; 
        export PYTHONPATH=${PYTHONPATH}:/home/oleksii/projects/alta-backend ; 
        set -a; source .envlocal; set +a; 
        python /home/oleksii/projects/alta-backend/scripts/export/backup_segmentations.py \
        --path /data/oleksii/alta-ai-orthanc-backup/2023_07_26_full \
        --segmentation_types lesion \
        --processing_state unsure \
        --export dcm"
    
        --processing_state processed unsure \
        --segmentation_types zone lesion \
"""
from argparse import ArgumentDefaultsHelpFormatter, ArgumentParser
from functools import reduce
import gzip
import os
from typing import Callable, List
import json
import shutil

import pydicom
from tqdm import tqdm
from mongoengine import connect, Q
from pyorthanc import util
from pydicom import Dataset, dcmwrite

from lib.constants import *
from lib.orm.models import Segmentation
from lib.constants import SegmentationType, ProcessingState
from lib.dicom_segmentation import DicomSegmentation
from lib.clients.orthanc_client import get_orthanc_id
from lib.clients import DicomWebClient


from scripts.utils import get_orthanc_client


PACS_HOST = "http://127.0.0.1:8042"
PACS_USERNAME = os.getenv("ORTHANC_USERNAME")
PACS_PASSWORD = os.getenv("ORTHANC_PASSWORD")
MONGO_HOST = os.getenv("MONGO_DB_HOST")
MONGO_PORT = int(os.getenv("MONGO_DB_PORT"))
MONGO_USERNAME = os.getenv("MONGO_INITDB_USERNAME")
MONGO_PASSWORD = os.getenv("MONGO_INITDB_PASSWORD")


def mongo_db_conn():
    connect(
        db="aggregatedData",
        alias="data",
        username=os.getenv("MONGO_INITDB_USERNAME"),
        password=os.getenv("MONGO_INITDB_PASSWORD"),
        host=os.getenv("MONGO_DB_HOST"),
        port=int(os.getenv("MONGO_DB_PORT")),
    )


def cases_zone_processed_multiple(
    processing_states: List[ProcessingState], segmentation_types: List[SegmentationType]
):
    # this function can handle the query with multiple processing states and and segmentation types
    segmentation_types_q = [Q(segment_type=st.value) for st in segmentation_types]
    processing_states_q = [
        Q(editing_info__confidence_level=ps.value) for ps in processing_states
    ]

    segmentations = Segmentation.objects(
        reduce(lambda a, b: a & b, segmentation_types_q + processing_states_q)
        & Q(editable=True)
    )

    return segmentations


def cases_zone_processed(
    processing_state: ProcessingState, segmentation_type: SegmentationType
):
    segmentations = Segmentation.objects(
        Q(segment_type=processing_state.value)
        & Q(editing_info__confidence_level=segmentation_type.value)
    )
    return segmentations


def save_dcm_segmentation_as_nrrd(segmentation: Dataset, path: str) -> None:
    """Create nrrd format from dicom

    Included metadata: spacing, origin, studyInstanceUID, seriesInstanceUID, numberOfSegments, segmentUIDs
    """
    raise NotImplementedError


def save_dcm_segmentation_as_dcm(segmentation: Dataset, path: str) -> None:
    """Saves a pydicom dataset as dcm"""
    dcmwrite(path, segmentation)


def get_writer(export_type: str) -> Callable:
    if export_type == "dcm":
        return save_dcm_segmentation_as_dcm
    elif export_type == "nrrd":
        return save_dcm_segmentation_as_nrrd


def merge_dataset(dataset: pydicom.Dataset) -> pydicom.Dataset:
    """Merge dataset with interal infos"""
    segmentation: Segmentation = Segmentation.find(
        study_uid=dataset.StudyInstanceUID, series_uid=dataset.SeriesInstanceUID
    ).first()

    for _seg_seq in dataset.SegmentSequence:
        segment = segmentation.get_segment(tracking_uid=_seg_seq.TrackingUID)
        metainfo = {
            "lastEditor": segmentation.dicom_info.assigned_user,
            **dict(segment.general_info.to_mongo()),
            **segment.detail_info,
        }
        _seg_seq.SegmentDescription = json.dumps(metainfo)

    dataset.ContentDescription = segmentation.inference_data

    return dataset


def gzip_dicom(input_path, output_path):
    with open(input_path, "rb") as f_in, gzip.open(output_path, "wb") as f_out:
        shutil.copyfileobj(f_in, f_out)

    os.remove(input_path)


def export_segmentations_from_orthanc(
    path: str,
    writer: Callable,
    dicomweb_client: DicomWebClient,
    processing_states: ProcessingState,
    segmentation_types: SegmentationType,
    compression: Callable = gzip_dicom,
) -> None:
    for _st in segmentation_types:
        for _ps in processing_states:
            segmentations = cases_zone_processed_multiple(
                processing_states=[_ps],
                segmentation_types=[_st],
            )

            for _seg in tqdm(segmentations):
                try:
                    orthanc_id = get_orthanc_id(
                        _seg.dicom_info.patient_id, _seg.study_uid, _seg.series_uid
                    )
                    dicom_segmentation = None
                    series_info = dicomweb_client.get_series_id(orthanc_id)

                    if series_info["MainDicomTags"]["Modality"] == "SEG":
                        if len(series_info["Instances"]) > 1:
                            raise ValueError("TODO!")
                        dicom_segmentation = DicomSegmentation(
                            util.get_pydicom(
                                dicomweb_client, series_info["Instances"][0]
                            )
                        )

                    if dicom_segmentation is not None:
                        file_path = f"{path}/prostate_{_st.value}/{_ps}/{orthanc_id}"
                        os.makedirs(file_path, exist_ok=True)

                        # merge pyidcom dataset with our information
                        final_dataset = merge_dataset(dicom_segmentation.dataset)

                        writer(final_dataset, f"{file_path}/seg.dcm")

                        if compression:
                            compression(
                                input_path=f"{file_path}/seg.dcm",
                                output_path=f"{file_path}/seg.dcm.gz",
                            )

                except Exception as e:
                    print(f"Failed to export segmentations of study due to {e}")


if __name__ == "__main__":
    parser = ArgumentParser(formatter_class=ArgumentDefaultsHelpFormatter)
    parser.add_argument(
        "--path",
        type=str,
        required=True,
        help="Path where the exported data will be stored",
    )
    parser.add_argument(
        "--segmentation_types",
        type=SegmentationType,
        choices=[
            SegmentationType.LESION,
            SegmentationType.ZONE,
        ],
        nargs="+",
        required=True,
        help="Which type of segmentations shall be exported",
    )
    parser.add_argument(
        "--processing_state",
        type=ProcessingState,
        choices=[
            ProcessingState.PROCESSED,
            ProcessingState.UNPROCESSED,
            ProcessingState.UNSURE,
        ],
        nargs="+",
        required=True,
        help="Processing state of the segmentations to download",
    )
    parser.add_argument("--export", required=True, type=str, choices=["dcm", "nrrd"])

    args = parser.parse_args()

    path = args.path
    export_type = args.export
    segmentation_types = args.segmentation_types
    processing_states = args.processing_state

    mongo_db_conn()
    orthanc_client = get_orthanc_client()
    writer = get_writer(export_type)

    export_segmentations_from_orthanc(
        path=path,
        writer=writer,
        dicomweb_client=orthanc_client,
        processing_states=processing_states,
        segmentation_types=segmentation_types,
    )
