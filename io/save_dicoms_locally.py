
from pyorthanc import Orthanc, Instance, Patient, Study


from utils.utils import get_orthanc_client,  sane_filename


orthanc_client = get_orthanc_client()

study = "0a0da388-22d102ff-4fc4ae54-24e395d6-81fc2151"
series_oid = "65c996e0-e73a4923-4829ad80-0d923261-d7c7694c"

instances = orthanc_client.get_series_id(series_oid)['Instances']


for i, instance in enumerate(instances):
    dicom = Instance(instance, orthanc_client).get_pydicom()
    filename = f"/home/oleksii/projects/ohif-orthanc-postgres-docker/tmp_dicom_data/000_{i}.dcm"
    dicom.save_as(filename)
